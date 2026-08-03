import assert from "node:assert/strict";
import test from "node:test";

import { accountLabel, roleLabel, statusLabel } from "./format.ts";

test("Vietnamese presentation labels keep canonical values out of the UI", () => {
  assert.equal(statusLabel("settled"), "Đã quyết toán");
  assert.equal(statusLabel("pending"), "Đang chờ quyết toán");
  assert.equal(statusLabel("ineligible"), "Không đủ điều kiện");
  assert.equal(statusLabel("unknown"), "Chưa xác định");
  assert.equal(statusLabel("future_status"), "future_status");
  assert.equal(roleLabel("operator"), "Nhân viên vận hành");
  assert.equal(accountLabel("ALL"), "Tất cả tài khoản");
});
