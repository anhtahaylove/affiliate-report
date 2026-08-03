"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";
import { firstDayOfMonth, lastDayOfMonth, currentMonth } from "@/lib/format";

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
  const filterKey = JSON.stringify(filters);
  return <FilterForm key={filterKey} accounts={accounts} statuses={statuses} showSearch={showSearch} initialFilters={filters} />;
}

function FilterForm({ accounts, statuses, showSearch = false, initialFilters }: { accounts: string[]; statuses: string[]; showSearch?: boolean; initialFilters: UrlFilters }) {
  const router = useRouter();
  const pathname = usePathname();
  const [draft, setDraft] = useState(initialFilters);
  const monthStart = draft.month ? firstDayOfMonth(draft.month) : "";
  const monthEnd = draft.month ? lastDayOfMonth(draft.month) : "";

  function toggle(list: "accounts" | "statuses", value: string) {
    setDraft((current) => ({ ...current, [list]: current[list].includes(value) ? current[list].filter((item) => item !== value) : [...current[list], value] }));
  }

  function apply(event: FormEvent) {
    event.preventDefault();
    const query = new URLSearchParams();
    query.set("month", draft.month);
    query.set("start", draft.start);
    query.set("end", draft.end);
    draft.accounts.forEach((account) => query.append("account", account));
    draft.statuses.forEach((status) => query.append("status", status));
    if (draft.search.trim()) query.set("search", draft.search.trim());
    router.push(`${pathname}?${query.toString()}`);
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
      <div className="filter-stack">
        <span className="field-label">Account</span>
        <div className="account-options" role="group" aria-label="Lọc theo account">
          {accounts.map((account) => (
            <label className="account-option" key={account}>
              <input type="checkbox" checked={draft.accounts.includes(account)} onChange={() => toggle("accounts", account)} />
              {account}
            </label>
          ))}
        </div>
      </div>
      {statuses.length ? (
        <div className="filter-stack">
          <span className="field-label">Trạng thái</span>
          <div className="account-options" role="group" aria-label="Lọc theo trạng thái đơn">
            {statuses.map((status) => (
              <label className="account-option" key={status}>
                <input type="checkbox" checked={draft.statuses.includes(status)} onChange={() => toggle("statuses", status)} />
                {status}
              </label>
            ))}
          </div>
        </div>
      ) : null}
      <button className="primary" type="submit">Áp dụng</button>
    </form>
  );
}
