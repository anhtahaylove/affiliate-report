import assert from "node:assert/strict";
import test from "node:test";

import { accountLabel, achievementTone, roleLabel, statusLabel } from "./format.ts";

test("Vietnamese presentation labels keep canonical values out of the UI", () => {
  assert.equal(statusLabel("settled"), "Đã quyết toán");
  assert.equal(statusLabel("pending"), "Đang chờ quyết toán");
  assert.equal(statusLabel("ineligible"), "Không đủ điều kiện");
  assert.equal(statusLabel("unknown"), "Chưa xác định");
  assert.equal(statusLabel("future_status"), "future_status");
  assert.equal(roleLabel("operator"), "Nhân viên vận hành");
  assert.equal(accountLabel("ALL"), "Tất cả tài khoản");
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
