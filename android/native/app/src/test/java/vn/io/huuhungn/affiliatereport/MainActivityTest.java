package vn.io.huuhungn.affiliatereport;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class MainActivityTest {
    @Test
    public void downloadBoundaryAllowsOnlyTheLocalApi() {
        assertTrue(MainActivity.isTrustedLoopbackUrl("http://127.0.0.1:8765/api/v1/orders/export.xlsx"));
        assertFalse(MainActivity.isTrustedLoopbackUrl("http://localhost:8765/api/v1/orders/export.xlsx"));
        assertFalse(MainActivity.isTrustedLoopbackUrl("https://127.0.0.1:8765/api/v1/orders/export.xlsx"));
        assertFalse(MainActivity.isTrustedLoopbackUrl("http://127.0.0.1:9000/api/v1/orders/export.xlsx"));
        assertFalse(MainActivity.isTrustedLoopbackUrl("https://example.com/file.xlsx"));
        assertFalse(MainActivity.isTrustedLoopbackUrl("not a URL"));
    }

    @Test
    public void apkDetectionUsesMimeTypeOrFileExtension() {
        assertTrue(MainActivity.isApkDownload(
                "http://127.0.0.1:8765/api/v1/admin/update/android/package",
                "application/vnd.android.package-archive"
        ));
        assertTrue(MainActivity.isApkDownload(
                "http://127.0.0.1:8765/cache/AffiliateReport.apk",
                "application/octet-stream"
        ));
        assertFalse(MainActivity.isApkDownload(
                "http://127.0.0.1:8765/api/v1/orders/export.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ));
    }

    @Test
    public void apkMetadataRequiresExactSizeAndSha256() {
        String digest = "A".repeat(64);
        assertTrue(MainActivity.matchesApkMetadata(123, digest, 123, digest.toLowerCase()));
        assertFalse(MainActivity.matchesApkMetadata(122, digest, 123, digest));
        assertFalse(MainActivity.matchesApkMetadata(123, "B".repeat(64), 123, digest));
        assertFalse(MainActivity.matchesApkMetadata(0, digest, 0, digest));
    }

    @Test
    public void downloadFilenameCannotEscapeTheChosenDirectory() {
        assertEquals(
                "AffiliateReport.affsync",
                MainActivity.safeDownloadFilename(
                        "../../AffiliateReport.affsync",
                        "http://127.0.0.1:8765/api/v1/sync/export/download/token",
                        "application/vnd.affiliate-report.sync"
                )
        );
    }
}
