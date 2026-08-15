package vn.io.huuhungn.affiliatereport;

import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.DocumentsContract;
import android.provider.Settings;
import android.util.Log;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.URLUtil;
import android.widget.Toast;

import androidx.activity.OnBackPressedCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.core.content.FileProvider;

import com.getcapacitor.BridgeActivity;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends BridgeActivity {
    private static final String TAG = "AffiliateReport";
    private static final int API_PORT = 8765;
    private static final String APP_URL = "http://127.0.0.1:8765/";
    private static final String LOCAL_TOKEN_COOKIE = "android_local_token";
    private static final String APK_MIME_TYPE = "application/vnd.android.package-archive";
    private static final String XLSX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    private static final String STATE_DOWNLOAD_URL = "affiliate_report_download_url";
    private static final String STATE_INSTALL_FILE = "affiliate_report_install_file";
    private static final String STATE_INSTALL_VERSION = "affiliate_report_install_version";
    private static final String STATE_INSTALL_SIZE = "affiliate_report_install_size";
    private static final String STATE_INSTALL_SHA256 = "affiliate_report_install_sha256";
    // Thư mục đồng bộ liên tục (SAF) — xem AndroidSyncFolder (web) + parser.FILENAME_PATTERN (Python).
    private static final String SYNC_FOLDER_PREFS = "affiliate_report_sync_folder";
    private static final String PREF_SYNC_FOLDER_URI = "tree_uri";
    private static final String SYNC_DONE_SUBFOLDER = ".done";
    private static final String SYNC_FAILED_SUBFOLDER = ".failed";
    private static final long SYNC_STABLE_CHECK_DELAY_MILLIS = 2_000;
    private static final String SYNC_MULTIPART_BOUNDARY = "AffiliateReportSyncBoundary7f3a9c";
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

    private final ActivityResultLauncher<Intent> pickSyncFolderLauncher = registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(),
            result -> {
                Uri treeUri = result.getData() == null ? null : result.getData().getData();
                if (result.getResultCode() != RESULT_OK || treeUri == null) {
                    dispatchSyncFolderEvent(currentSyncFolderLabel(), null);
                    return;
                }
                try {
                    getContentResolver().takePersistableUriPermission(
                            treeUri,
                            Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                    );
                    getSyncFolderPreferences().edit().putString(PREF_SYNC_FOLDER_URI, treeUri.toString()).apply();
                    dispatchSyncFolderEvent(queryDisplayName(treeUri), null);
                } catch (Exception error) {
                    dispatchSyncFolderEvent(currentSyncFolderLabel(), "Không thể lưu quyền truy cập thư mục.");
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

        @JavascriptInterface
        public void pickSyncFolder() {
            runOnUiThread(MainActivity.this::launchSyncFolderPicker);
        }

        @JavascriptInterface
        public void requestSyncFolderState() {
            runOnUiThread(() -> dispatchSyncFolderEvent(currentSyncFolderLabel(), null));
        }

        @JavascriptInterface
        public void syncNow(String account) {
            fileExecutor.execute(() -> runSync(account));
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
                            // APK vừa cài bản web mới (khác lần trước tái dùng bundle cũ):
                            // WebView vẫn có thể giữ HTML/JS cache từ bản trước dù server giờ
                            // trả bản mới. Xoá đúng một lần ở đây thay vì mọi lần mở app.
                            if (application.isWebBundleFreshlyInstalled()) {
                                getBridge().getWebView().clearCache(true);
                            }
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

    // --- Thư mục đồng bộ liên tục (Android SAF) --------------------------------------------
    // Người dùng chọn một thư mục (thường là Download) một lần qua ACTION_OPEN_DOCUMENT_TREE;
    // từ đó mỗi lần mở app hoặc bấm "Đồng bộ ngay", ứng dụng tự quét thư mục đó, POST thẳng từng
    // tệp khớp affiliate_orders*.xlsx tới /api/v1/imports qua loopback (đi đúng pipeline nhập có
    // sẵn — chống trùng SHA-256, kiểm 47 cột, mọi validate khác giữ nguyên), rồi dời tệp đã xử lý
    // sang .done/.failed ngay trong thư mục đó. Dùng thẳng DocumentsContract/ContentResolver thay
    // vì thư viện androidx.documentfile để không phải thêm dependency Gradle mới.

    private void launchSyncFolderPicker() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION
                        | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                        | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        // Gợi ý mở sẵn tại Download — chỉ là gợi ý tốt-nhất-có-thể cho provider lưu trữ ngoài
        // chuẩn AOSP; SAF không có khái niệm mặc định thật, provider khác (thẻ nhớ rời, provider
        // app khác) bỏ qua gợi ý này một cách an toàn, người dùng vẫn tự chọn thư mục như thường.
        intent.putExtra(DocumentsContract.EXTRA_INITIAL_URI,
                DocumentsContract.buildDocumentUri("com.android.externalstorage.documents", "primary:Download"));
        try {
            pickSyncFolderLauncher.launch(intent);
        } catch (Exception error) {
            dispatchSyncFolderEvent(currentSyncFolderLabel(), "Không thể mở trình chọn thư mục.");
        }
    }

    private SharedPreferences getSyncFolderPreferences() {
        return getSharedPreferences(SYNC_FOLDER_PREFS, MODE_PRIVATE);
    }

    private Uri currentSyncFolderUri() {
        String stored = getSyncFolderPreferences().getString(PREF_SYNC_FOLDER_URI, null);
        return stored == null ? null : Uri.parse(stored);
    }

    private String currentSyncFolderLabel() {
        Uri treeUri = currentSyncFolderUri();
        return treeUri == null ? null : queryDisplayName(treeUri);
    }

    /** Đọc tên thư mục gốc để hiện cho người dùng — dùng đúng cột SAF chuẩn (không giả định định
     * dạng docId "primary:..." riêng của AOSP external storage provider) nên chạy được với mọi
     * provider. Trả về null nếu không đọc được (quyền bị thu hồi, thẻ nhớ bị rút…) — phía React
     * coi như CHƯA chọn thư mục, không phân biệt hai ca này để giữ đơn giản. */
    private String queryDisplayName(Uri treeUri) {
        try {
            Uri rootDocUri = DocumentsContract.buildDocumentUriUsingTree(treeUri, DocumentsContract.getTreeDocumentId(treeUri));
            try (Cursor cursor = getContentResolver().query(
                    rootDocUri, new String[]{DocumentsContract.Document.COLUMN_DISPLAY_NAME}, null, null, null)) {
                if (cursor != null && cursor.moveToFirst()) {
                    String name = cursor.getString(0);
                    if (name != null && !name.trim().isEmpty()) return name;
                }
            }
        } catch (Exception ignored) {
            // rơi xuống trả null bên dưới
        }
        return null;
    }

    private void dispatchSyncFolderEvent(String label, String error) {
        org.json.JSONObject detail = new org.json.JSONObject();
        try {
            detail.put("picked", label != null);
            if (label != null) detail.put("label", label);
            if (error != null) detail.put("error", error);
        } catch (org.json.JSONException impossible) {
            return;
        }
        getBridge().getWebView().evaluateJavascript(
                "window.dispatchEvent(new CustomEvent(" + org.json.JSONObject.quote("affiliate-report-sync-folder")
                        + ", {detail:" + detail + "}))",
                null
        );
    }

    private void dispatchSyncResultEvent(int imported, int duplicate, int rejected, String message) {
        org.json.JSONObject detail = new org.json.JSONObject();
        try {
            detail.put("imported", imported);
            detail.put("duplicate", duplicate);
            detail.put("rejected", rejected);
            if (message != null) detail.put("message", message);
        } catch (org.json.JSONException impossible) {
            return;
        }
        getBridge().getWebView().evaluateJavascript(
                "window.dispatchEvent(new CustomEvent(" + org.json.JSONObject.quote("affiliate-report-sync-result")
                        + ", {detail:" + detail + "}))",
                null
        );
    }

    // Khớp affiliate_report/parser.py:FILENAME_PATTERN — đổi một bên mà quên bên kia thì Java lọc
    // khác lúc server kiểm lại: tệp bị bỏ qua ở đây dù lẽ ra hợp lệ, hoặc ngược lại bị server từ
    // chối dù Java tưởng hợp lệ.
    private static boolean isValidSyncFilename(String name) {
        if (name == null) return false;
        String lower = name.toLowerCase(Locale.ROOT);
        return lower.startsWith("affiliate_orders") && lower.endsWith(".xlsx");
    }

    private boolean isSyncFileStable(Uri documentUri) {
        long[] first = querySizeAndModified(documentUri);
        if (first == null) return false;
        try {
            Thread.sleep(SYNC_STABLE_CHECK_DELAY_MILLIS);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            return false;
        }
        long[] second = querySizeAndModified(documentUri);
        return second != null && first[0] == second[0] && first[1] == second[1];
    }

    private long[] querySizeAndModified(Uri documentUri) {
        try (Cursor cursor = getContentResolver().query(documentUri, new String[]{
                DocumentsContract.Document.COLUMN_SIZE, DocumentsContract.Document.COLUMN_LAST_MODIFIED,
        }, null, null, null)) {
            if (cursor == null || !cursor.moveToFirst()) return null;
            return new long[]{cursor.getLong(0), cursor.getLong(1)};
        } catch (Exception error) {
            return null;
        }
    }

    /** Quét đúng cấp gốc của thư mục đã chọn (không đệ quy vào .done/.failed hay thư mục con
     * khác), nhập từng tệp affiliate_orders*.xlsx ổn định rồi dời sang .done/.failed. Chạy trên
     * fileExecutor (nền, tuần tự) — gọi từ syncNow() qua bridge. */
    private void runSync(String account) {
        Uri treeUri = currentSyncFolderUri();
        if (treeUri == null) {
            runOnUiThread(() -> dispatchSyncResultEvent(0, 0, 0, "Chưa chọn thư mục đồng bộ."));
            return;
        }
        if (account == null || account.trim().isEmpty()) {
            runOnUiThread(() -> dispatchSyncResultEvent(0, 0, 0, "Chưa chọn tài khoản để đồng bộ."));
            return;
        }
        int imported = 0;
        int duplicate = 0;
        int rejected = 0;
        List<String> errors = new ArrayList<>();
        try {
            String rootDocId = DocumentsContract.getTreeDocumentId(treeUri);
            List<Uri> candidates = new ArrayList<>();
            List<String> candidateNames = new ArrayList<>();
            try (Cursor cursor = getContentResolver().query(
                    DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, rootDocId),
                    new String[]{
                            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                            DocumentsContract.Document.COLUMN_MIME_TYPE,
                    }, null, null, null)) {
                if (cursor != null) {
                    while (cursor.moveToNext()) {
                        String mime = cursor.getString(2);
                        String name = cursor.getString(1);
                        if (DocumentsContract.Document.MIME_TYPE_DIR.equals(mime) || !isValidSyncFilename(name)) continue;
                        candidates.add(DocumentsContract.buildDocumentUriUsingTree(treeUri, cursor.getString(0)));
                        candidateNames.add(name);
                    }
                }
            }
            for (int index = 0; index < candidates.size(); index++) {
                Uri fileUri = candidates.get(index);
                String name = candidateNames.get(index);
                if (!isSyncFileStable(fileUri)) continue; // vẫn đang tải/đồng bộ, để lượt sau
                try {
                    org.json.JSONObject uploadResult = postSyncImport(account, name, fileUri);
                    if (uploadResult.optBoolean("duplicate", false)) duplicate++; else imported++;
                    moveSyncFile(treeUri, rootDocId, fileUri, name, SYNC_DONE_SUBFOLDER);
                } catch (Exception fileError) {
                    rejected++;
                    errors.add(name + ": " + fileError.getMessage());
                    moveSyncFile(treeUri, rootDocId, fileUri, name, SYNC_FAILED_SUBFOLDER);
                }
            }
            int finalImported = imported;
            int finalDuplicate = duplicate;
            int finalRejected = rejected;
            String message = !errors.isEmpty()
                    ? String.join(" · ", errors.subList(0, Math.min(3, errors.size())))
                    : candidates.isEmpty() ? "Không có tệp mới trong thư mục." : null;
            runOnUiThread(() -> dispatchSyncResultEvent(finalImported, finalDuplicate, finalRejected, message));
        } catch (Exception error) {
            runOnUiThread(() -> dispatchSyncResultEvent(0, 0, 0, "Không thể đọc thư mục đồng bộ: " + error.getMessage()));
        }
    }

    private org.json.JSONObject postSyncImport(String account, String filename, Uri source) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(APP_URL + "api/v1/imports").openConnection();
        connection.setConnectTimeout(10_000);
        connection.setReadTimeout(120_000);
        connection.setInstanceFollowRedirects(false);
        connection.setDoOutput(true);
        connection.setRequestMethod("POST");
        connection.setChunkedStreamingMode(64 * 1024);
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + SYNC_MULTIPART_BOUNDARY);
        AffiliateReportApplication application = (AffiliateReportApplication) getApplication();
        connection.setRequestProperty("X-Android-Local-Token", application.getLocalToken());
        String cookies = CookieManager.getInstance().getCookie(APP_URL);
        if (cookies != null && !cookies.trim().isEmpty()) connection.setRequestProperty("Cookie", cookies);
        try {
            try (OutputStream body = connection.getOutputStream()) {
                writeMultipartField(body, "account", account);
                body.write(("--" + SYNC_MULTIPART_BOUNDARY + "\r\n").getBytes(StandardCharsets.UTF_8));
                body.write(("Content-Disposition: form-data; name=\"file\"; filename=\""
                        + filename.replace("\"", "") + "\"\r\n").getBytes(StandardCharsets.UTF_8));
                body.write(("Content-Type: " + XLSX_MIME_TYPE + "\r\n\r\n").getBytes(StandardCharsets.UTF_8));
                try (InputStream input = getContentResolver().openInputStream(source)) {
                    if (input == null) throw new IllegalStateException("Không thể mở tệp " + filename);
                    copyStream(input, body);
                }
                body.write(("\r\n--" + SYNC_MULTIPART_BOUNDARY + "--\r\n").getBytes(StandardCharsets.UTF_8));
            }
            int status = connection.getResponseCode();
            InputStream responseStream = status >= 200 && status < 300 ? connection.getInputStream() : connection.getErrorStream();
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            if (responseStream != null) {
                try (InputStream stream = responseStream) {
                    copyStream(stream, buffer);
                }
            }
            String responseBody = buffer.toString("UTF-8");
            if (status < 200 || status >= 300) throw new IllegalStateException(extractDetail(responseBody, status));
            return new org.json.JSONObject(responseBody);
        } finally {
            connection.disconnect();
        }
    }

    private static void writeMultipartField(OutputStream body, String name, String value) throws Exception {
        body.write(("--" + SYNC_MULTIPART_BOUNDARY + "\r\n").getBytes(StandardCharsets.UTF_8));
        body.write(("Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n").getBytes(StandardCharsets.UTF_8));
        body.write((value + "\r\n").getBytes(StandardCharsets.UTF_8));
    }

    /** Diễn giải {"detail": "..."} lẫn {"detail": [{"msg": "...", ...}, ...]} — FastAPI trả chuỗi
     * khi code app tự raise lỗi, trả mảng khi Pydantic tự chặn request trước khi vào code app (vd.
     * sai định dạng account/filename). Cùng gốc với web/src/lib/api.ts:detailMessage(). */
    private static String extractDetail(String responseBody, int status) {
        try {
            org.json.JSONObject json = new org.json.JSONObject(responseBody);
            Object detail = json.opt("detail");
            if (detail instanceof String) return (String) detail;
            if (detail instanceof org.json.JSONArray) {
                org.json.JSONArray items = (org.json.JSONArray) detail;
                StringBuilder combined = new StringBuilder();
                for (int index = 0; index < items.length(); index++) {
                    Object item = items.opt(index);
                    String msg = item instanceof org.json.JSONObject ? ((org.json.JSONObject) item).optString("msg", null) : null;
                    if (msg == null) continue;
                    if (combined.length() > 0) combined.append("; ");
                    combined.append(msg);
                }
                if (combined.length() > 0) return combined.toString();
            }
        } catch (Exception ignored) {
            // rơi xuống fallback bên dưới
        }
        return "HTTP " + status;
    }

    /** Copy+delete thủ công thay vì DocumentsContract.moveDocument: không phải provider SAF nào
     * cũng hỗ trợ move, copy+delete luôn hoạt động ở mọi provider. Lỗi dời tệp chỉ log — tệp đã
     * nhập/từ chối thành công rồi (kết quả sync đã tính), dời thất bại không phải lỗi nhập liệu. */
    private void moveSyncFile(Uri treeUri, String rootDocId, Uri sourceUri, String filename, String subfolder) {
        try {
            Uri targetDirUri = ensureSyncSubfolder(treeUri, rootDocId, subfolder);
            Uri newFileUri = DocumentsContract.createDocument(getContentResolver(), targetDirUri, XLSX_MIME_TYPE, filename);
            if (newFileUri == null) throw new IllegalStateException("Không thể tạo tệp trong " + subfolder);
            try (InputStream input = getContentResolver().openInputStream(sourceUri);
                 OutputStream output = getContentResolver().openOutputStream(newFileUri)) {
                if (input == null || output == null) throw new IllegalStateException("Không thể sao chép tệp");
                copyStream(input, output);
            }
            DocumentsContract.deleteDocument(getContentResolver(), sourceUri);
        } catch (Exception error) {
            Log.e(TAG, "Không thể dời " + filename + " sang " + subfolder, error);
        }
    }

    private Uri ensureSyncSubfolder(Uri treeUri, String parentDocId, String name) throws Exception {
        try (Cursor cursor = getContentResolver().query(
                DocumentsContract.buildChildDocumentsUriUsingTree(treeUri, parentDocId),
                new String[]{
                        DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                        DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                        DocumentsContract.Document.COLUMN_MIME_TYPE,
                }, null, null, null)) {
            if (cursor != null) {
                while (cursor.moveToNext()) {
                    if (DocumentsContract.Document.MIME_TYPE_DIR.equals(cursor.getString(2)) && name.equals(cursor.getString(1))) {
                        return DocumentsContract.buildDocumentUriUsingTree(treeUri, cursor.getString(0));
                    }
                }
            }
        }
        Uri created = DocumentsContract.createDocument(
                getContentResolver(),
                DocumentsContract.buildDocumentUriUsingTree(treeUri, parentDocId),
                DocumentsContract.Document.MIME_TYPE_DIR,
                name
        );
        if (created == null) throw new IllegalStateException("Không thể tạo thư mục " + name);
        return created;
    }
}
