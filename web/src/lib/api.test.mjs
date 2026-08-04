import assert from "node:assert/strict";
import test from "node:test";

process.env.NEXT_PUBLIC_API_URL = "https://example.test/";

const { dailyReportExportUrl, visibleRejectedRows } = await import("./api.ts");

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

test("visible rejected rows keeps only the first ten details", () => {
  const rows = Array.from({ length: 12 }, (_, index) => ({ row_number: index + 2, reason: `Lỗi ${index + 1}` }));

  assert.deepEqual(visibleRejectedRows(rows), rows.slice(0, 10));
});
