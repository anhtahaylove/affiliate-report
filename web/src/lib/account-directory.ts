import type { AccountItem } from "@/lib/api";

export type AccountIdentity = Readonly<{
  code: string;
  displayName: string;
  primary: string;
  secondary: string | null;
  inline: string;
  accessibleName: string;
  known: boolean;
}>;

export type AccountDirectory = Readonly<{
  accounts: readonly string[];
  items: readonly AccountItem[];
  get: (code: string | null | undefined) => AccountIdentity;
  label: (code: string | null | undefined) => string;
}>;

const ALL_ACCOUNT: AccountIdentity = Object.freeze({
  code: "ALL",
  displayName: "Tất cả account",
  primary: "Tất cả account",
  secondary: null,
  inline: "Tất cả account",
  accessibleName: "Tất cả account",
  known: true,
});

export function createAccountDirectory(accountItems: readonly AccountItem[] = [], accountCodes: readonly string[] = []): AccountDirectory {
  const items = Object.freeze(accountItems.map((item) => Object.freeze({ ...item })));
  const itemByCode = new Map(items.map((item) => [item.code, item]));
  const accounts = Object.freeze(Array.from(new Set([...accountCodes, ...items.filter((item) => item.active).map((item) => item.code)])));

  function get(value: string | null | undefined): AccountIdentity {
    const code = value?.trim() || "";
    if (code === "ALL") return ALL_ACCOUNT;
    const item = itemByCode.get(code);
    const displayName = item?.display_name.trim() || code || "Chưa xác định";
    const inline = code && displayName !== code ? `${displayName} — ${code}` : displayName;
    return Object.freeze({
      code,
      displayName,
      primary: displayName,
      secondary: code ? `Mã: ${code}` : null,
      inline,
      accessibleName: code && displayName !== code ? `${displayName}, mã tài khoản ${code}` : displayName,
      known: Boolean(item),
    });
  }

  return Object.freeze({
    accounts,
    items,
    get,
    label: (code) => get(code).inline,
  });
}
