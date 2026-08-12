import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

function componentFiles(root) {
  return readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
    const path = join(root, entry.name);
    return entry.isDirectory() ? componentFiles(path) : entry.name.endsWith(".tsx") ? [path] : [];
  });
}

test("account-facing components use the canonical AccountDirectory seam", () => {
  const files = componentFiles(new URL("../components", import.meta.url).pathname.replace(/^\/(.:)/, "$1"));
  const offenders = files.flatMap((file) => {
    const source = readFileSync(file, "utf8");
    const violations = [];
    if (/\baccountLabel\s*\(/.test(source)) violations.push("accountLabel");
    if (/window\.location\.reload\s*\(/.test(source)) violations.push("document reload");
    if (/new\s+CustomEvent\s*\(/.test(source)) violations.push("event bus");
    return violations.map((violation) => `${file}: ${violation}`);
  });
  assert.deepEqual(offenders, []);
});
