import assert from "node:assert/strict";
import test from "node:test";

import { qualityIssueCount, qualityIssues, rejectedAllTime } from "./data-quality.ts";

function quality(overrides = {}) {
  return {
    unknown_status_rows: 0,
    non_vnd_rows: 0,
    missing_order_date_rows: 0,
    missing_settlement_date_rows: 0,
    settled_missing_settlement_rows: 0,
    negative_settlement_lag_rows: 0,
    import_batches: 0,
    import_inserted: 0,
    import_updated: 0,
    import_unchanged: 0,
    import_rejected: 0,
    latest_import_at: null,
    ...overrides,
  };
}

test("đơn chưa quyết toán không bị tính là vấn đề", () => {
  // TikTok để trống ngày quyết toán cho mọi đơn chưa trả tiền. Trên dữ liệu thật, đếm chúng
  // làm con số cảnh báo phồng lên tới hàng trăm trong khi không có gì hỏng cả.
  assert.equal(qualityIssueCount(quality({ missing_settlement_date_rows: 500 })), 0);
});

test("đã quyết toán mà thiếu ngày mới là bất thường", () => {
  assert.equal(qualityIssueCount(quality({ settled_missing_settlement_rows: 3 })), 3);
});

test("con số đầu trang bằng đúng tổng các mục liệt kê bên dưới", () => {
  // Trước đây hai chỗ tự cộng hai công thức khác nhau nên không bao giờ khớp.
  const q = quality({
    unknown_status_rows: 2,
    non_vnd_rows: 1,
    missing_order_date_rows: 4,
    settled_missing_settlement_rows: 8,
    negative_settlement_lag_rows: 16,
    import_rejected: 32,
    missing_settlement_date_rows: 500,
  });
  const tong = qualityIssues(q).reduce((con, issue) => con + issue.value, 0);

  assert.equal(qualityIssueCount(q), tong);
  assert.equal(tong, 31);
});

test("dòng bị từ chối là số toàn thời gian, không cộng vào chỉ số theo kỳ", () => {
  // Chúng chưa bao giờ phân tích được nên không có ngày đặt đơn; trộn vào con số theo kỳ thì
  // một tệp hỏng từ năm ngoái làm cảnh báo phồng lên mãi mà thu hẹp bộ lọc cũng không giảm.
  const q = quality({ import_rejected: 32 });
  assert.equal(qualityIssueCount(q), 0);
  assert.equal(rejectedAllTime(q), 32);
});

test("mọi mục đều có nhãn và lời giải thích tiếng Việt", () => {
  for (const issue of qualityIssues(quality())) {
    assert.ok(issue.label.length > 0, "thiếu nhãn");
    assert.ok(issue.help.length > 0, `thiếu giải thích cho ${issue.label}`);
  }
});
