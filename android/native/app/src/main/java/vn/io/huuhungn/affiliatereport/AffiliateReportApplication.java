package vn.io.huuhungn.affiliatereport;

import android.app.Application;
import android.content.res.AssetManager;
import android.util.Base64;
import android.util.Log;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class AffiliateReportApplication extends Application {
    private static final String TAG = "AffiliateReport";
    private static final String WEB_VERSION = "2.1.1";
    private static final int API_PORT = 8765;
    private final ExecutorService runtimeExecutor = Executors.newSingleThreadExecutor();
    private final CountDownLatch startupFinished = new CountDownLatch(1);
    private volatile boolean runtimeReady;
    private String localToken;

    @Override
    public void onCreate() {
        super.onCreate();
        try {
            localToken = loadOrCreateLocalToken();
        } catch (IOException error) {
            Log.e(TAG, "Unable to create the private local token", error);
            writeStartupError(error);
            startupFinished.countDown();
            return;
        }
        runtimeExecutor.execute(this::startRuntime);
    }

    private void startRuntime() {
        try {
            File webDir = installWebBundle();
            if (!Python.isStarted()) {
                Python.start(new AndroidPlatform(this));
            }
            Python.getInstance()
                    .getModule("android_runtime")
                    .callAttr(
                            "start",
                            getFilesDir().getAbsolutePath(),
                            getCacheDir().getAbsolutePath(),
                            webDir.getAbsolutePath(),
                            localToken,
                            API_PORT
                    );
            for (int attempt = 0; attempt < 240; attempt++) {
                if (Python.getInstance().getModule("android_runtime").callAttr("is_running").toBoolean()) {
                    runtimeReady = true;
                    return;
                }
                Thread.sleep(250);
            }
            throw new IllegalStateException("Local runtime did not become ready");
        } catch (Exception error) {
            Log.e(TAG, "Unable to start the local runtime", error);
            writeStartupError(error);
        } finally {
            startupFinished.countDown();
        }
    }

    boolean awaitRuntimeReady(long timeoutMillis) throws InterruptedException {
        return startupFinished.await(timeoutMillis, TimeUnit.MILLISECONDS) && runtimeReady;
    }

    String getLocalToken() {
        if (localToken == null || localToken.length() < 32) {
            throw new IllegalStateException("Android local token is unavailable");
        }
        return localToken;
    }

    private String loadOrCreateLocalToken() throws IOException {
        File tokenFile = new File(getFilesDir(), "android-local-token");
        if (tokenFile.isFile()) {
            byte[] bytes = new byte[(int) Math.min(tokenFile.length(), 512)];
            int read;
            try (InputStream input = new java.io.FileInputStream(tokenFile)) {
                read = input.read(bytes);
            }
            String existing = new String(bytes, 0, Math.max(read, 0), StandardCharsets.US_ASCII).trim();
            if (existing.length() >= 32 && existing.length() <= 256) return existing;
            throw new IOException("Stored Android local token is invalid");
        }
        byte[] random = new byte[32];
        new SecureRandom().nextBytes(random);
        String created = Base64.encodeToString(random, Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
        File partial = new File(getFilesDir(), "android-local-token.tmp");
        try (OutputStream output = new FileOutputStream(partial, false)) {
            output.write(created.getBytes(StandardCharsets.US_ASCII));
            output.flush();
        }
        if (!partial.renameTo(tokenFile)) {
            partial.delete();
            throw new IOException("Cannot persist Android local token");
        }
        return created;
    }

    private File installWebBundle() throws IOException {
        File webDir = new File(getFilesDir(), "web/" + WEB_VERSION);
        File ready = new File(webDir, ".ready");
        if (ready.isFile() && new File(webDir, "index.html").isFile()) {
            return webDir;
        }
        deleteRecursively(webDir);
        if (!webDir.mkdirs() && !webDir.isDirectory()) {
            throw new IOException("Cannot create web bundle directory");
        }
        copyAssetTree(getAssets(), "web", webDir);
        try (OutputStream output = new FileOutputStream(ready)) {
            output.write(WEB_VERSION.getBytes(StandardCharsets.UTF_8));
        }
        return webDir;
    }

    private static void copyAssetTree(AssetManager assets, String assetPath, File destination) throws IOException {
        String[] children = assets.list(assetPath);
        if (children == null || children.length == 0) {
            try (InputStream input = assets.open(assetPath);
                 OutputStream output = new FileOutputStream(destination)) {
                copyStream(input, output);
            }
            return;
        }
        if (!destination.isDirectory() && !destination.mkdirs()) {
            throw new IOException("Cannot create " + destination);
        }
        for (String child : children) {
            copyAssetTree(assets, assetPath + "/" + child, new File(destination, child));
        }
    }

    private static void deleteRecursively(File file) throws IOException {
        if (!file.exists()) return;
        File[] children = file.listFiles();
        if (children != null) {
            for (File child : children) deleteRecursively(child);
        }
        if (!file.delete()) throw new IOException("Cannot delete partial web bundle: " + file);
    }

    private static void copyStream(InputStream input, OutputStream output) throws IOException {
        byte[] buffer = new byte[32 * 1024];
        int count;
        while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
    }

    private void writeStartupError(Exception error) {
        try {
            try (OutputStream output = new FileOutputStream(new File(getCacheDir(), "startup-error.txt"))) {
                output.write(
                        (error.getClass().getSimpleName() + ": " + String.valueOf(error.getMessage()))
                                .getBytes(StandardCharsets.UTF_8)
                );
            }
        } catch (IOException ignored) {
            Log.e(TAG, "Unable to record startup error", ignored);
        }
    }
}
