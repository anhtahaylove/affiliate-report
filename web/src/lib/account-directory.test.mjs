import assert from "node:assert/strict";
import test from "node:test";

import { createAccountDirectory } from "./account-directory.ts";

const directory = createAccountDirectory([
  { code: "SHOP_A", display_name: "Gian hàng chính", active: true, display_order: 1 },
  { code: "SHOP_B", display_name: "Gian hàng chính", active: true, display_order: 2 },
], ["SHOP_A", "SHOP_B"]);

test("AccountDirectory keeps ALL as a virtual all-account scope", () => {
  const identity = directory.get("ALL");
  assert.equal(identity.primary, "Tất cả tài khoản");
  assert.equal(identity.secondary, null);
  assert.equal(identity.known, true);
});

test("AccountDirectory falls back safely for unknown or archived codes", () => {
  const identity = directory.get("ARCHIVED_1");
  assert.equal(identity.primary, "ARCHIVED_1");
  assert.equal(identity.secondary, "Mã: ARCHIVED_1");
  assert.equal(identity.known, false);
});

test("AccountDirectory keeps duplicate display names distinguishable by code", () => {
  assert.equal(directory.get("SHOP_A").inline, "Gian hàng chính — SHOP_A");
  assert.equal(directory.get("SHOP_B").inline, "Gian hàng chính — SHOP_B");
  assert.notEqual(directory.get("SHOP_A").accessibleName, directory.get("SHOP_B").accessibleName);
});

test("AccountDirectory exposes display name primary and code secondary", () => {
  const identity = directory.get("SHOP_A");
  assert.equal(identity.primary, "Gian hàng chính");
  assert.equal(identity.secondary, "Mã: SHOP_A");
  assert.equal(identity.accessibleName, "Gian hàng chính, mã tài khoản SHOP_A");
});
