package vn.io.huuhungn.affiliatereport;

import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.URLUtil;
import android.widget.Toast;

import androidx.activity.OnBackPressedCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.core.content.FileProvider;

import com.getcapacitor.BridgeActivity;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends BridgeActivity {
    private static final int API_PORT = 8765;
    private static final String APP_URL = "http://127.0.0.1:8765/";
    private static final String LOCAL_TOKEN_COOKIE = "android_local_token";
    private static final String APK_MIME_TYPE = "application/vnd.android.package-archive";
    private static final String STATE_DOWNLOAD_URL = "affiliate_report_download_url";
    private static final String STATE_INSTALL_FILE = "affiliate_report_install_file";
    private static final String STATE_INSTALL_VERSION = "affiliate_report_install_version";
    private static final String STATE_INSTALL_SIZE = "affiliate_report_install_size";
    private static final String STATE_INSTALL_SHA256 = "affiliate_report_install_sha256";
    private final ExecutorService fileExecutor = Executors.newSingleThreadExecutor();
    private String pendingDownloadUrl;
    private File pendingInstallFile;
    private String pendingInstallVersion;
    private long pendingInstallSize;
    private String pendingInstallSha256;

    private final ActivityResultLauncher<Intent> createDocument = registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(),
            result -> {
                Uri destination = result.getData() == null ? null : result.getData().getData();
                String source = pendingDownloadUrl;
                pendingDownloadUrl = null;
                if (result.getResultCode() == RESULT_OK && destination != null && source != null) {
                    fileExecutor.execute(() -> saveLoopbackDownload(source, destination));
                } else if (source != null) {
                    dispatchDownloadEvent(
                            "affiliate-report-download-error",
                            source,
                            0,
                            "Đã hủy chọn nơi lưu."
                    );
                }
            }
    );

    private final ActivityResultLauncher<Intent> allowPackageInstalls = registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(),
            result -> {
                File apk = pendingInstallFile;
                String version = pendingInstallVersion;
                long size = pendingInstallSize;
                String sha256 = pendingInstallSha256;
                clearPendingInstall();
                if (apk != null && canRequestPackageInstalls()) {
                    launchPackageInstaller(apk, version, size, sha256);
                } else if (apk != null) {
                    dispatchApkInstallError("Bạn chưa cho phép cài ứng dụng từ nguồn này.");
                    Toast.makeText(
                            this,
                            "Cần cho phép cài ứng dụng từ nguồn này để hoàn tất cập nhật.",
                            Toast.LENGTH_LONG
                    ).show();
                }
            }
    );

    @Override
    public void onCreate(Bundle savedInstanceState) {
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setCookie(APP_URL, LOCAL_TOKEN_COOKIE + "=; Max-Age=0; Path=/");
        super.onCreate(savedInstanceState);
        getBridge().getWebView().addJavascriptInterface(
                new AndroidDownloadBridge(),
                "AffiliateReportAndroid"
        );
        if (savedInstanceState != null) {
            pendingDownloadUrl = savedInstanceState.getString(STATE_DOWNLOAD_URL);
            String installPath = savedInstanceState.getString(STATE_INSTALL_FILE);
            if (installPath != null) pendingInstallFile = new File(installPath);
            pendingInstallVersion = savedInstanceState.getString(STATE_INSTALL_VERSION);
            pendingInstallSize = savedInstanceState.getLong(STATE_INSTALL_SIZE, 0);
            pendingInstallSha256 = savedInstanceState.getString(STATE_INSTALL_SHA256);
        }
        getBridge().getWebView().setDownloadListener((url, userAgent, contentDisposition, mimeType, contentLength) -> {
            if (!isTrustedLoopbackUrl(url)) {
                Toast.makeText(this, "Chỉ có thể lưu tệp từ ứng dụng cục bộ.", Toast.LENGTH_LONG).show();
                return;
            }
            if (isApkDownload(url, mimeType)) {
                fileExecutor.execute(() -> downloadApkAndLaunch(url));
                return;
            }
            pendingDownloadUrl = url;
            Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT)
                    .addCategory(Intent.CATEGORY_OPENABLE)
                    .setType(mimeType == null || mimeType.trim().isEmpty() ? "application/octet-stream" : mimeType)
                    .putExtra(Intent.EXTRA_TITLE, URLUtil.guessFileName(url, contentDisposition, mimeType));
            createDocument.launch(intent);
        });
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                if (getBridge().getWebView().canGoBack()) {
                    getBridge().getWebView().goBack();
                } else {
                    moveTaskToBack(true);
                }
            }
        });
        fileExecutor.execute(this::connectToLocalRuntime);
    }

    private final class AndroidDownloadBridge {
        @JavascriptInterface
        public void download(String source, String filename, String mimeType) {
            runOnUiThread(() -> handleNativeDownload(source, filename, mimeType));
        }
    }

    private void handleNativeDownload(String source, String filename, String mimeType) {
        String currentPage = getBridge().getWebView().getUrl();
        if (!isTrustedLoopbackUrl(currentPage) || !isTrustedLoopbackUrl(source)) {
            dispatchDownloadEvent(
                    "affiliate-report-download-error",
                    source == null ? "" : source,
                    0,
                    "Chỉ có thể lưu tệp từ ứng dụng cục bộ."
            );
            return;
        }
        if (isApkDownload(source, mimeType)) {
            fileExecutor.execute(() -> downloadApkAndLaunch(source));
            return;
        }
        if (pendingDownloadUrl != null) {
            dispatchDownloadEvent(
                    "affiliate-report-download-error",
                    source,
                    0,
                    "Một tệp khác đang chờ chọn nơi lưu."
            );
            return;
        }
        pendingDownloadUrl = source;
        String safeFilename = safeDownloadFilename(filename, source, mimeType);
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT)
                .addCategory(Intent.CATEGORY_OPENABLE)
                .setType(mimeType == null || mimeType.trim().isEmpty() ? "application/octet-stream" : mimeType)
                .putExtra(Intent.EXTRA_TITLE, safeFilename);
        createDocument.launch(intent);
    }

    private void connectToLocalRuntime() {
        try {
            AffiliateReportApplication application = (AffiliateReportApplication) getApplication();
            if (!application.awaitRuntimeReady(65_000)) {
                throw new IllegalStateException("Không thể khởi động dữ liệu cục bộ.");
            }
            String token = application.getLocalToken();
            runOnUiThread(() -> CookieManager.getInstance().setCookie(
                    APP_URL,
                    LOCAL_TOKEN_COOKIE + "=" + token + "; Path=/; HttpOnly; SameSite=Strict",
                    accepted -> {
                        if (Boolean.TRUE.equals(accepted)) {
                            CookieManager.getInstance().flush();
                            getBridge().getWebView().loadUrl(APP_URL);
                        } else {
                            showStartupFailure("Không thể mở phiên dữ liệu riêng tư.");
                        }
                    }
            ));
        } catch (Exception error) {
            runOnUiThread(() -> showStartupFailure("Không thể khởi động dữ liệu cục bộ. Hãy đóng và mở lại ứng dụng."));
        }
    }

    private void showStartupFailure(String message) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
        String safe = org.json.JSONObject.quote(message);
        getBridge().getWebView().evaluateJavascript(
                "window.affiliateReportStartupFailed && window.affiliateReportStartupFailed(" + safe + ")",
                null
        );
    }

    @Override
    public void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        outState.putString(STATE_DOWNLOAD_URL, pendingDownloadUrl);
        if (pendingInstallFile != null) outState.putString(STATE_INSTALL_FILE, pendingInstallFile.getAbsolutePath());
        if (pendingInstallVersion != null) outState.putString(STATE_INSTALL_VERSION, pendingInstallVersion);
        if (pendingInstallSize > 0) outState.putLong(STATE_INSTALL_SIZE, pendingInstallSize);
        if (pendingInstallSha256 != null) outState.putString(STATE_INSTALL_SHA256, pendingInstallSha256);
    }

    @Override
    public void onDestroy() {
        fileExecutor.shutdownNow();
        super.onDestroy();
    }

    static boolean isTrustedLoopbackUrl(String value) {
        try {
            URI uri = URI.create(value);
            return "http".equals(uri.getScheme())
                    && "127.0.0.1".equals(uri.getHost())
                    && uri.getPort() == API_PORT;
        } catch (IllegalArgumentException ignored) {
            return false;
        }
    }

    static boolean isApkDownload(String url, String mimeType) {
        if (APK_MIME_TYPE.equalsIgnoreCase(mimeType == null ? "" : mimeType.trim())) return true;
        try {
            String path = URI.create(url).getPath();
            return path != null && path.toLowerCase(Locale.ROOT).endsWith(".apk");
        } catch (IllegalArgumentException ignored) {
            return false;
        }
    }

    static String safeDownloadFilename(String filename, String source, String mimeType) {
        String candidate = filename == null ? "" : new File(filename).getName().trim();
        if (!candidate.isEmpty()) return candidate;
        return URLUtil.guessFileName(source, null, mimeType);
    }

    private void downloadApkAndLaunch(String source) {
        File updateDir = new File(getCacheDir(), "updates");
        File partial = new File(updateDir, "AffiliateReport-update.apk.part");
        File apk = new File(updateDir, "AffiliateReport-update.apk");
        HttpURLConnection connection = null;
        try {
            if (!updateDir.isDirectory() && !updateDir.mkdirs()) {
                throw new IllegalStateException("Không thể tạo thư mục cập nhật");
            }
            connection = openLoopbackConnection(source);
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) throw new IllegalStateException("HTTP " + status);
            String expectedSha256 = requiredHeader(connection, "X-Affiliate-Report-SHA256").toUpperCase(Locale.ROOT);
            if (!expectedSha256.matches("[0-9A-F]{64}")) throw new IllegalStateException("SHA-256 không hợp lệ");
            long expectedSize;
            try {
                expectedSize = Long.parseLong(requiredHeader(connection, "X-Affiliate-Report-Size"));
            } catch (NumberFormatException error) {
                throw new IllegalStateException("Dung lượng APK không hợp lệ", error);
            }
            if (expectedSize <= 0) throw new IllegalStateException("Dung lượng APK không hợp lệ");
            String expectedVersion = requiredHeader(connection, "X-Affiliate-Report-Version");
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            long copied;
            try (InputStream input = connection.getInputStream();
                 OutputStream output = new FileOutputStream(partial, false)) {
                copied = copyStream(input, output, digest);
            }
            String actualSha256 = hexDigest(digest.digest());
            if (!matchesApkMetadata(copied, actualSha256, expectedSize, expectedSha256)) {
                throw new IllegalStateException("APK không khớp thông tin xác minh");
            }
            if (apk.exists() && !apk.delete()) throw new IllegalStateException("Không thể thay tệp cập nhật cũ");
            if (!partial.renameTo(apk)) throw new IllegalStateException("Không thể hoàn tất tệp cập nhật");
            runOnUiThread(() -> requestPackageInstall(apk, expectedVersion, copied, actualSha256));
        } catch (Exception error) {
            if (partial.exists()) partial.delete();
            runOnUiThread(() -> {
                dispatchApkEvent(
                        "affiliate-report-apk-error",
                        null,
                        0,
                        null,
                        "Không thể xác minh APK. Hãy thử lại hoặc tải từ trang phát hành."
                );
                Toast.makeText(this, "Không thể xác minh APK.", Toast.LENGTH_LONG).show();
            });
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private void requestPackageInstall(File apk, String version, long size, String sha256) {
        if (!canRequestPackageInstalls()) {
            pendingInstallFile = apk;
            pendingInstallVersion = version;
            pendingInstallSize = size;
            pendingInstallSha256 = sha256;
            try {
                allowPackageInstalls.launch(new Intent(
                        Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                        Uri.parse("package:" + getPackageName())
                ));
            } catch (RuntimeException error) {
                clearPendingInstall();
                dispatchApkInstallError("Không thể mở phần cấp quyền cài đặt.");
            }
            return;
        }
        launchPackageInstaller(apk, version, size, sha256);
    }

    private boolean canRequestPackageInstalls() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.O || getPackageManager().canRequestPackageInstalls();
    }

    private void launchPackageInstaller(File apk, String version, long size, String sha256) {
        try {
            Uri contentUri = FileProvider.getUriForFile(this, getPackageName() + ".fileprovider", apk);
            Intent install = new Intent(Intent.ACTION_VIEW)
                    .setDataAndType(contentUri, APK_MIME_TYPE)
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(install);
            dispatchApkEvent("affiliate-report-apk-ready", version, size, sha256, null);
        } catch (RuntimeException error) {
            dispatchApkInstallError("Không thể mở trình cài đặt Android.");
        }
    }

    private void clearPendingInstall() {
        pendingInstallFile = null;
        pendingInstallVersion = null;
        pendingInstallSize = 0;
        pendingInstallSha256 = null;
    }

    private void dispatchApkInstallError(String message) {
        dispatchApkEvent("affiliate-report-apk-error", null, 0, null, message);
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }

    private HttpURLConnection openLoopbackConnection(String source) throws Exception {
        if (!isTrustedLoopbackUrl(source)) throw new IllegalArgumentException("URL nội bộ không hợp lệ");
        HttpURLConnection connection = (HttpURLConnection) new URL(source).openConnection();
        connection.setConnectTimeout(10_000);
        connection.setReadTimeout(120_000);
        connection.setInstanceFollowRedirects(false);
        AffiliateReportApplication application = (AffiliateReportApplication) getApplication();
        connection.setRequestProperty("X-Android-Local-Token", application.getLocalToken());
        String cookies = CookieManager.getInstance().getCookie(source);
        if (cookies != null && !cookies.trim().isEmpty()) connection.setRequestProperty("Cookie", cookies);
        return connection;
    }

    private static String requiredHeader(HttpURLConnection connection, String name) {
        String value = connection.getHeaderField(name);
        if (value == null || value.trim().isEmpty()) throw new IllegalStateException("Thiếu header " + name);
        return value.trim();
    }

    static boolean matchesApkMetadata(long actualSize, String actualSha256, long expectedSize, String expectedSha256) {
        return actualSize == expectedSize
                && actualSize > 0
                && actualSha256 != null
                && expectedSha256 != null
                && actualSha256.equalsIgnoreCase(expectedSha256);
    }

    private void dispatchApkEvent(String eventName, String version, long size, String sha256, String message) {
        org.json.JSONObject detail = new org.json.JSONObject();
        try {
            if (version != null) detail.put("version", version);
            if (size > 0) detail.put("size", size);
            if (sha256 != null) detail.put("sha256", sha256);
            if (message != null) detail.put("message", message);
        } catch (org.json.JSONException impossible) {
            return;
        }
        getBridge().getWebView().evaluateJavascript(
                "window.dispatchEvent(new CustomEvent(" + org.json.JSONObject.quote(eventName)
                        + ", {detail:" + detail + "}))",
                null
        );
    }

    private void dispatchDownloadEvent(String eventName, String source, long size, String message) {
        org.json.JSONObject detail = new org.json.JSONObject();
        try {
            detail.put("source", source);
            if (size > 0) detail.put("size", size);
            if (message != null) detail.put("message", message);
        } catch (org.json.JSONException impossible) {
            return;
        }
        getBridge().getWebView().evaluateJavascript(
                "window.dispatchEvent(new CustomEvent(" + org.json.JSONObject.quote(eventName)
                        + ", {detail:" + detail + "}))",
                null
        );
    }

    private static long copyStream(InputStream input, OutputStream output) throws Exception {
        byte[] buffer = new byte[32 * 1024];
        long total = 0;
        int count;
        while ((count = input.read(buffer)) != -1) {
            output.write(buffer, 0, count);
            total += count;
        }
        return total;
    }

    private static long copyStream(InputStream input, OutputStream output, MessageDigest digest) throws Exception {
        byte[] buffer = new byte[32 * 1024];
        long total = 0;
        int count;
        while ((count = input.read(buffer)) != -1) {
            output.write(buffer, 0, count);
            digest.update(buffer, 0, count);
            total += count;
        }
        return total;
    }

    private static String hexDigest(byte[] value) {
        StringBuilder result = new StringBuilder(value.length * 2);
        for (byte item : value) result.append(String.format(Locale.ROOT, "%02X", item & 0xff));
        return result.toString();
    }

    private void saveLoopbackDownload(String source, Uri destination) {
        HttpURLConnection connection = null;
        try {
            connection = openLoopbackConnection(source);
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) throw new IllegalStateException("HTTP " + status);
            try (InputStream input = connection.getInputStream();
                 OutputStream output = getContentResolver().openOutputStream(destination, "w")) {
                if (output == null) throw new IllegalStateException("Không thể mở tệp đích");
                long copied = copyStream(input, output);
                runOnUiThread(() -> {
                    dispatchDownloadEvent("affiliate-report-download-ready", source, copied, null);
                    Toast.makeText(this, "Đã lưu tệp.", Toast.LENGTH_SHORT).show();
                });
            }
        } catch (Exception error) {
            runOnUiThread(() -> {
                dispatchDownloadEvent(
                        "affiliate-report-download-error",
                        source,
                        0,
                        "Không thể lưu tệp. Hãy chọn lại nơi lưu."
                );
                Toast.makeText(this, "Không thể lưu tệp.", Toast.LENGTH_LONG).show();
            });
        } finally {
            if (connection != null) connection.disconnect();
        }
    }
}
