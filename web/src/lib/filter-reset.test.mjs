import assert from "node:assert/strict";
import test from "node:test";

import { buildFilterHref } from "./filter-query.ts";

const accounts = ["CHIISTORE", "EMLINHNOIY", "THAOBRA"];
const statuses = ["settled", "pending", "ineligible", "unknown"];

test("canonical reset URL keeps dates and omits account/status/search/page params", () => {
  assert.equal(
    buildFilterHref(
      "/orders",
      {
        month: "2026-08",
        start: "2026-08-01",
        end: "2026-08-31",
        accounts,
        statuses,
        search: "",
      },
      accounts,
      statuses,
    ),
    "/orders?month=2026-08&start=2026-08-01&end=2026-08-31",
  );
});

test("partial apply URL keeps scoped account, status and trimmed search", () => {
  assert.equal(
    buildFilterHref(
      "/orders",
      {
        month: "2026-08",
        start: "2026-08-05",
        end: "2026-08-20",
        accounts: ["CHIISTORE"],
        statuses: ["pending", "settled"],
        search: "  SKU123  ",
      },
      accounts,
      statuses,
    ),
    "/orders?month=2026-08&start=2026-08-05&end=2026-08-20&account=CHIISTORE&status=pending&status=settled&search=SKU123",
  );
});
