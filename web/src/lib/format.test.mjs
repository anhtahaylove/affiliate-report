import assert from "node:assert/strict";
import test from "node:test";

import { achievementTone, countsText, formatDateTime, roleLabel, statusLabel } from "./format.ts";

test("Vietnamese presentation labels keep canonical values out of the UI", () => {
  assert.equal(statusLabel("settled"), "Đã quyết toán");
  assert.equal(statusLabel("pending"), "Đang chờ quyết toán");
  assert.equal(statusLabel("ineligible"), "Không đủ điều kiện");
  assert.equal(statusLabel("unknown"), "Chưa xác định");
  assert.equal(statusLabel("future_status"), "future_status");
  assert.equal(roleLabel("operator"), "Nhân viên vận hành");
});

test("achievementTone maps target-achievement ratios to a traffic-light tone", () => {
  assert.equal(achievementTone(null), "neutral");
  assert.equal(achievementTone(undefined), "neutral");
  assert.equal(achievementTone(Number.NaN), "neutral");
  assert.equal(achievementTone(1), "good");
  assert.equal(achievementTone(1.2), "good");
  assert.equal(achievementTone(0.5), "warning");
  assert.equal(achievementTone(0.99), "warning");
  assert.equal(achievementTone(0.49), "critical");
  assert.equal(achievementTone(0), "critical");
});

test("formatDateTime keeps a four-digit year and unambiguous Vietnamese date", () => {
  const formatted = formatDateTime(new Date(2026, 2, 10, 8, 5).toISOString());
  assert.match(formatted, /2026/);
  assert.match(formatted, /10\/03/);
  assert.match(formatted, /08:05/);
});

test("countsText Việt hóa các bảng nghiệp vụ nhưng vẫn giữ key mở rộng", () => {
  assert.equal(countsText({ accounts: 2, raw_rows: 15 }), "Tài khoản: 2 · Dòng dữ liệu gốc: 15");
  assert.equal(countsText({ future_table: 1 }), "future_table: 1");
});
