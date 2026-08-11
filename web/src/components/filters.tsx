"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, ReactNode, useMemo, useState } from "react";
import { SlidersHorizontal, X } from "lucide-react";
import { firstDayOfMonth, lastDayOfMonth, currentMonth, lastDays, previousMonth, statusLabel, wholeMonth } from "@/lib/format";
import { buildFilterHref } from "@/lib/filter-query";

export const ORDER_PAGE_SIZES = [50, 100, 200];

export type UrlFilters = {
  month: string;
  start: string;
  end: string;
  accounts: string[];
  statuses: string[];
  search: string;
  page: number;
  size: number;
  sort: string;
  direction: "asc" | "desc";
};

export function useUrlFilters() {
  const params = useSearchParams();
  // Có phạm vi ngày mà không có month thì tháng KPI phải bám theo phạm vi đó, không phải
  // tháng hiện tại — nếu không trang Mục tiêu sẽ sửa KPI tháng 8 trong khi đang lọc tháng 3.
  const month = params.get("month") || params.get("start")?.slice(0, 7) || currentMonth();
  return useMemo<UrlFilters>(() => ({
    month,
    start: params.get("start") || firstDayOfMonth(month),
    end: params.get("end") || lastDayOfMonth(month),
    accounts: params.getAll("account"),
    statuses: params.getAll("status"),
    search: params.get("search") || "",
    page: Math.max(1, Number(params.get("page") || "1") || 1),
    size: ORDER_PAGE_SIZES.includes(Number(params.get("size"))) ? Number(params.get("size")) : 100,
    sort: params.get("sort") || "",
    direction: params.get("direction") === "asc" ? "asc" : "desc",
  }), [month, params]);
}

export function FilterBar({ accounts, statuses, showSearch = false, actions }: { accounts: string[]; statuses: string[]; showSearch?: boolean; actions?: ReactNode }) {
  const filters = useUrlFilters();
  const initialFilters = {
    ...filters,
    accounts: filters.accounts.length ? filters.accounts : accounts,
    statuses: statuses.length ? (filters.statuses.length ? filters.statuses : statuses) : [],
  };
  const filterKey = JSON.stringify({ filters, accounts, statuses });
  return <FilterForm key={filterKey} accounts={accounts} statuses={statuses} showSearch={showSearch} actions={actions} initialFilters={initialFilters} />;
}

function FilterForm({ accounts, statuses, showSearch = false, actions, initialFilters }: { accounts: string[]; statuses: string[]; showSearch?: boolean; actions?: ReactNode; initialFilters: UrlFilters }) {
  const router = useRouter();
  const pathname = usePathname();
  const [draft, setDraft] = useState(initialFilters);
  const [error, setError] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const monthStart = draft.month ? firstDayOfMonth(draft.month) : "";
  const monthEnd = draft.month ? lastDayOfMonth(draft.month) : "";
  const allAccountsSelected = accounts.length > 0 && draft.accounts.length === accounts.length;
  const allStatusesSelected = statuses.length > 0 && draft.statuses.length === statuses.length;
  const compactSummary = [
    `${draft.start.split("-").reverse().join("/")} – ${draft.end.split("-").reverse().join("/")}`,
    allAccountsSelected ? "Tất cả tài khoản" : `${draft.accounts.length}/${accounts.length} tài khoản`,
    statuses.length ? (allStatusesSelected ? "Tất cả trạng thái" : `${draft.statuses.length}/${statuses.length} trạng thái`) : null,
  ].filter(Boolean).join(" · ");

  // Khoảng hay dùng nhất, để không phải bấm tay ba ô ngày mỗi lần. Nằm ngoài phần thu gọn vì
  // đây là thao tác thường xuyên nhất — bắt mở bộ lọc ra chỉ để đổi sang "30 ngày" là thừa.
  const quickRanges: Array<{ label: string; range: { start: string; end: string; month: string } }> = [
    { label: "7 ngày", range: lastDays(7) },
    { label: "30 ngày", range: lastDays(30) },
    { label: "Tháng này", range: wholeMonth(currentMonth()) },
    { label: "Tháng trước", range: wholeMonth(previousMonth()) },
  ];

  function applyQuickRange(range: { start: string; end: string; month: string }) {
    setError("");
    const nextDraft = { ...draft, ...range, page: 1 };
    setDraft(nextDraft);
    setFiltersOpen(false);
    router.push(buildFilterHref(pathname, nextDraft, accounts, statuses));
  }

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
    const nextDraft: UrlFilters = { month, start: firstDayOfMonth(month), end: lastDayOfMonth(month), accounts, statuses, search: "", page: 1, size: 100, sort: "", direction: "desc" };
    setError("");
    setDraft(nextDraft);
    setFiltersOpen(false);
    router.replace(buildFilterHref(pathname, nextDraft, accounts, statuses));
  }

  function apply(event: FormEvent) {
    event.preventDefault();
    if (!draft.accounts.length) return setError("Hãy chọn ít nhất một tài khoản.");
    if (statuses.length && !draft.statuses.length) return setError("Hãy chọn ít nhất một trạng thái.");
    setError("");
    setFiltersOpen(false);
    router.push(buildFilterHref(pathname, draft, accounts, statuses));
  }

  return (
    <form className="command-bar panel" onSubmit={apply}>
      {/* Mở sẵn toàn bộ bộ lọc ngốn gần 300px trên mọi màn hình, đẩy số liệu xuống dưới nếp
          gấp. Mặc định chỉ hiện một dòng tóm tắt phạm vi đang xem; bấm mới mở ra để chỉnh. */}
      <div className="filter-head">
        <button className="filter-toggle" type="button" aria-expanded={filtersOpen} aria-controls="report-filters" onClick={() => setFiltersOpen((open) => !open)}>
          <span><strong>Phạm vi báo cáo</strong><small>{compactSummary}</small></span>
          <span className="filter-toggle-action" aria-hidden="true">{filtersOpen ? "Thu gọn" : "Chỉnh sửa"}</span>
        </button>
        <div className="segmented" role="group" aria-label="Khoảng thời gian nhanh">
          {quickRanges.map((quick) => {
            const active = quick.range.start === draft.start && quick.range.end === draft.end;
            return <button key={quick.label} type="button" aria-pressed={active} onClick={() => applyQuickRange(quick.range)}>{quick.label}</button>;
          })}
        </div>
        {actions}
      </div>
      {filtersOpen ? <button className="mobile-filter-overlay" type="button" aria-label="Đóng bộ lọc" onClick={() => setFiltersOpen(false)} /> : null}
      <div id="report-filters" className={`filter-body${filtersOpen ? " is-open" : ""}`}>
        <div className="mobile-filter-sheet-head">
          <span><SlidersHorizontal size={18} aria-hidden="true" /><strong>Bộ lọc báo cáo</strong></span>
          <button type="button" onClick={() => setFiltersOpen(false)} aria-label="Đóng bộ lọc"><X size={18} aria-hidden="true" /></button>
        </div>
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
      </div>
      {error ? <p className="filter-error" role="alert">{error}</p> : null}
    </form>
  );
}
