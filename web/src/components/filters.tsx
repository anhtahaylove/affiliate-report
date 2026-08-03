"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";
import { firstDayOfMonth, lastDayOfMonth, currentMonth, statusLabel } from "@/lib/format";
import { buildFilterHref } from "@/lib/filter-query";

export type UrlFilters = {
  month: string;
  start: string;
  end: string;
  accounts: string[];
  statuses: string[];
  search: string;
  page: number;
};

export function useUrlFilters() {
  const params = useSearchParams();
  const month = params.get("month") || currentMonth();
  return useMemo<UrlFilters>(() => ({
    month,
    start: params.get("start") || firstDayOfMonth(month),
    end: params.get("end") || lastDayOfMonth(month),
    accounts: params.getAll("account"),
    statuses: params.getAll("status"),
    search: params.get("search") || "",
    page: Math.max(1, Number(params.get("page") || "1") || 1),
  }), [month, params]);
}

export function FilterBar({ accounts, statuses, showSearch = false }: { accounts: string[]; statuses: string[]; showSearch?: boolean }) {
  const filters = useUrlFilters();
  const initialFilters = {
    ...filters,
    accounts: filters.accounts.length ? filters.accounts : accounts,
    statuses: statuses.length ? (filters.statuses.length ? filters.statuses : statuses) : [],
  };
  const filterKey = JSON.stringify({ filters, accounts, statuses });
  return <FilterForm key={filterKey} accounts={accounts} statuses={statuses} showSearch={showSearch} initialFilters={initialFilters} />;
}

function FilterForm({ accounts, statuses, showSearch = false, initialFilters }: { accounts: string[]; statuses: string[]; showSearch?: boolean; initialFilters: UrlFilters }) {
  const router = useRouter();
  const pathname = usePathname();
  const [draft, setDraft] = useState(initialFilters);
  const [error, setError] = useState("");
  const monthStart = draft.month ? firstDayOfMonth(draft.month) : "";
  const monthEnd = draft.month ? lastDayOfMonth(draft.month) : "";
  const allAccountsSelected = accounts.length > 0 && draft.accounts.length === accounts.length;
  const allStatusesSelected = statuses.length > 0 && draft.statuses.length === statuses.length;

  function toggle(list: "accounts" | "statuses", value: string) {
    setError("");
    setDraft((current) => ({ ...current, [list]: current[list].includes(value) ? current[list].filter((item) => item !== value) : [...current[list], value] }));
  }

  function toggleAll(list: "accounts" | "statuses", values: string[]) {
    setError("");
    setDraft((current) => ({ ...current, [list]: current[list].length === values.length ? [] : values }));
  }

  function reset() {
    const month = currentMonth();
    const nextDraft = { month, start: firstDayOfMonth(month), end: lastDayOfMonth(month), accounts, statuses, search: "", page: 1 };
    setError("");
    setDraft(nextDraft);
    router.replace(buildFilterHref(pathname, nextDraft, accounts, statuses));
  }

  function apply(event: FormEvent) {
    event.preventDefault();
    if (!draft.accounts.length) return setError("Hãy chọn ít nhất một tài khoản.");
    if (statuses.length && !draft.statuses.length) return setError("Hãy chọn ít nhất một trạng thái.");
    setError("");
    router.push(buildFilterHref(pathname, draft, accounts, statuses));
  }

  return (
    <form className="command-bar panel" onSubmit={apply}>
      <div className="field compact">
        <label htmlFor="target-month">Tháng KPI</label>
        <input
          id="target-month"
          type="month"
          value={draft.month}
          required
          onChange={(event) => {
            const next = event.target.value;
            if (!next) return;
            setDraft((current) => ({ ...current, month: next, start: firstDayOfMonth(next), end: lastDayOfMonth(next) }));
          }}
        />
      </div>
      <div className="field compact">
        <label htmlFor="start-date">Từ ngày</label>
        <input id="start-date" type="date" value={draft.start} min={monthStart || undefined} max={draft.end || monthEnd || undefined} onChange={(event) => setDraft((current) => ({ ...current, start: event.target.value }))} />
      </div>
      <div className="field compact">
        <label htmlFor="end-date">Đến ngày</label>
        <input id="end-date" type="date" value={draft.end} min={draft.start || monthStart || undefined} max={monthEnd || undefined} onChange={(event) => setDraft((current) => ({ ...current, end: event.target.value }))} />
      </div>
      {showSearch ? (
        <div className="field compact search-field">
          <label htmlFor="order-search">Tìm đơn/SKU</label>
          <input id="order-search" value={draft.search} onChange={(event) => setDraft((current) => ({ ...current, search: event.target.value }))} placeholder="Mã đơn, SKU, sản phẩm" />
        </div>
      ) : null}
      <fieldset className="filter-stack">
        <legend className="field-label">Tài khoản</legend>
        <div className="account-options">
          <label className="account-option select-all-option">
            <input type="checkbox" checked={allAccountsSelected} onChange={() => toggleAll("accounts", accounts)} />
            Tất cả tài khoản
          </label>
          {accounts.map((account) => (
            <label className="account-option" key={account}>
              <input type="checkbox" checked={draft.accounts.includes(account)} onChange={() => toggle("accounts", account)} />
              {account}
            </label>
          ))}
        </div>
      </fieldset>
      {statuses.length ? (
        <fieldset className="filter-stack">
          <legend className="field-label">Trạng thái</legend>
          <div className="account-options">
            <label className="account-option select-all-option">
              <input type="checkbox" checked={allStatusesSelected} onChange={() => toggleAll("statuses", statuses)} />
              Tất cả trạng thái
            </label>
            {statuses.map((status) => (
              <label className="account-option" key={status} title={`Mã hệ thống: ${status}`}>
                <input type="checkbox" checked={draft.statuses.includes(status)} onChange={() => toggle("statuses", status)} />
                {statusLabel(status)}
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}
      <div className="filter-actions">
        <button className="primary" type="submit">Áp dụng bộ lọc</button>
        <button type="button" onClick={reset}>Đặt lại</button>
      </div>
      {error ? <p className="filter-error" role="alert">{error}</p> : null}
    </form>
  );
}
