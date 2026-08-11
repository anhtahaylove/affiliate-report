import assert from "node:assert/strict";
import test from "node:test";

process.env.NEXT_PUBLIC_API_URL = "https://example.test/";

const { ApiError, NETWORK_ERROR_MESSAGE, dailyReportExportUrl, loadMeta, visibleRejectedRows } = await import("./api.ts");

test("daily report export URL only keeps account status and date filters", () => {
  assert.equal(
    dailyReportExportUrl({
      accounts: ["CHIISTORE", "THAOBRA"],
      statuses: ["unknown"],
      start: "2026-08-01",
      end: "2026-08-31",
      month: "2026-08",
      search: "SKU123",
    }),
    "https://example.test/api/v1/reports/daily.xlsx?account=CHIISTORE&account=THAOBRA&status=unknown&start=2026-08-01&end=2026-08-31",
  );
});

test("app đã đóng thì báo cách mở lại, không phải 'Failed to fetch' của trình duyệt", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = () => Promise.reject(new TypeError("Failed to fetch"));
  try {
    await assert.rejects(loadMeta(), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 0);
      assert.equal(error.message, NETWORK_ERROR_MESSAGE);
      assert.doesNotMatch(error.message, /Failed to fetch/);
      return true;
    });
  } finally {
    globalThis.fetch = original;
  }
});

test("visible rejected rows keeps only the first ten details", () => {
  const rows = Array.from({ length: 12 }, (_, index) => ({ row_number: index + 2, reason: `Lỗi ${index + 1}` }));

  assert.deepEqual(visibleRejectedRows(rows), rows.slice(0, 10));
});
