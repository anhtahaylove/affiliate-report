"use client";

import { useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { OrderRow, OrderVersionRow, PageResponse, loadOrderVersions, loadOrders, ordersExportUrl } from "@/lib/api";
import { ORDER_PAGE_SIZES, UrlFilters } from "@/components/filters";
import { Notice, StateCard, StatusBadge } from "@/components/ui";
import { useApi } from "@/lib/use-api";
import { errorMessage, formatDateTime, formatMoney, integer, statusLabel } from "@/lib/format";

function csvCell(value: unknown) {
  const text = value == null ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function downloadCsv(name: string, rows: OrderRow[]) {
  const columns: Array<keyof OrderRow> = ["account", "order_id", "sku_id", "product_name", "shop_name", "status", "order_date", "gmv", "units_sold", "units_refunded", "estimated_commission", "final_received", "version", "created_at"];
  const csv = [columns.join(","), ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(","))].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

const ORDER_HEADERS: Array<{ label: string; sort?: string; numeric?: boolean }> = [
  { label: "Tài khoản", sort: "account" },
  { label: "Mã đơn", sort: "order_id" },
  { label: "SKU", sort: "sku_id" },
  { label: "Sản phẩm", sort: "product_name" },
  { label: "Trạng thái", sort: "status" },
  { label: "Ngày", sort: "order_date" },
  { label: "SL bán", sort: "units_sold", numeric: true },
  { label: "GMV", sort: "gmv", numeric: true },
  { label: "Hoa hồng ước tính", sort: "estimated_commission", numeric: true },
  { label: "Chi tiết" },
];

export function OrdersPage({ filters }: { filters: UrlFilters }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { data, error, loading } = useApi<PageResponse<OrderRow>>(
    `orders:${JSON.stringify([filters.accounts, filters.statuses, filters.start, filters.end, filters.search, filters.page, filters.size, filters.sort, filters.direction])}`,
    () => loadOrders({
      accounts: filters.accounts,
      statuses: filters.statuses,
      start: filters.start,
      end: filters.end,
      search: filters.search,
      limit: filters.size,
      offset: (filters.page - 1) * filters.size,
      sort: filters.sort || undefined,
      direction: filters.sort ? filters.direction : undefined,
    }),
    "Không thể tải đơn hàng.",
  );

  function navigate(changes: Record<string, string | null>) {
    const query = new URLSearchParams(searchParams.toString());
    Object.entries(changes).forEach(([key, value]) => (value === null ? query.delete(key) : query.set(key, value)));
    router.push(`${pathname}?${query.toString()}`);
  }

  if (error) return <Notice text={error} />;
  if (loading || !data) return <StateCard text="Đang tải đơn hàng…" />;
  const orders = data.items;
  const total = data.total;
  const totalPages = Math.max(1, Math.ceil(total / filters.size));
  const page = Math.min(filters.page, totalPages);

  function toggleSort(column: string) {
    const next = filters.sort === column && filters.direction === "desc" ? "asc" : "desc";
    navigate({ sort: column, direction: next, page: "1" });
  }

  return (
    <section className="section panel wide">
      <div className="section-heading">
        <div><p className="section-label">Danh sách đơn hàng</p><h2>{integer.format(total)} đơn trong bộ lọc</h2></div>
        <div className="row-actions">
          <label className="page-size"><span>Dòng mỗi trang</span>
            <select value={filters.size} onChange={(event) => navigate({ size: event.target.value, page: "1" })}>
              {ORDER_PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}
            </select>
          </label>
          <a className="button-link" download="tiktok-affiliate-orders.xlsx" href={ordersExportUrl({ accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end, search: filters.search })}>Xuất toàn bộ ra Excel</a>
          <button type="button" onClick={() => downloadCsv(`orders-${filters.start}-${filters.end}.csv`, orders)} disabled={!orders.length}>Xuất CSV trang này</button>
        </div>
      </div>
      <div className="table-wrap orders-table" role="region" aria-label="Danh sách đơn hàng, có thể cuộn ngang" tabIndex={0}>
        <table>
          <thead><tr>{ORDER_HEADERS.map((header) => {
            const active = header.sort && filters.sort === header.sort;
            return (
              <th key={header.label} aria-sort={active ? (filters.direction === "asc" ? "ascending" : "descending") : undefined}>
                {header.sort
                  ? <button type="button" className="sort-button" onClick={() => toggleSort(header.sort as string)} aria-label={`Sắp xếp theo ${header.label}`}>{header.label}<span aria-hidden="true">{active ? (filters.direction === "asc" ? "↑" : "↓") : "↕"}</span></button>
                  : header.label}
              </th>
            );
          })}</tr></thead>
          <tbody>{orders.map((row, index) => <tr key={`${row.account}-${row.order_id}-${row.sku_id}-${index}`}><td>{row.account}</td><td>{row.order_id ?? "—"}</td><td>{row.sku_id ?? "—"}</td><td className="product-cell" title={row.product_name ?? undefined}>{row.product_name ?? "—"}</td><td><StatusBadge status={row.status} /></td><td>{row.order_date ?? "—"}</td><td>{row.units_sold == null ? "—" : integer.format(row.units_sold)}</td><td>{formatMoney(row.gmv)}</td><td title="Hoa hồng ước tính theo file gốc, chưa trừ đơn Không đủ điều kiện">{formatMoney(row.estimated_commission)}</td><td><details className="order-detail"><summary>{`Chi tiết ${row.order_id ?? row.sku_id ?? index + 1}`}</summary><span>ID sản phẩm: {row.product_id ?? "—"}</span><span>Cửa hàng: {row.shop_name ?? "—"} ({row.shop_id ?? "—"})</span><span>Nội dung: {row.content_type ?? "—"} / {row.content_id ?? "—"}</span><span>Loại đơn: {row.order_type ?? "—"}</span><span>Loại hoa hồng: {row.commission_type ?? "—"}</span><span>Ngày quyết toán: {row.settlement_date ?? "—"}</span><span>Hoa hồng thực tế (sau khi trừ không đủ điều kiện): {formatMoney(row.actual_commission)}</span><span>Đã nhận: {formatMoney(row.final_received)}</span><OrderVersions businessKey={row.business_key} /></details></td></tr>)}</tbody>
        </table>
        {!orders.length ? <p className="empty">Không có đơn phù hợp. Hãy đổi bộ lọc hoặc nhập thêm file TikTok.</p> : null}
      </div>
      <nav className="pagination" aria-label="Phân trang đơn hàng"><button type="button" onClick={() => navigate({ page: String(Math.max(1, page - 1)) })} disabled={page <= 1}>Trang trước</button><span>Trang {integer.format(page)} / {integer.format(totalPages)}</span><button type="button" onClick={() => navigate({ page: String(Math.min(totalPages, page + 1)) })} disabled={page >= totalPages}>Trang sau</button></nav>
    </section>
  );
}


function OrderVersions({ businessKey }: { businessKey: string }) {
  const [rows, setRows] = useState<OrderVersionRow[] | null>(null);
  const [error, setError] = useState("");
  async function load() {
    if (rows || error) return;
    try {
      setRows((await loadOrderVersions(businessKey)).items);
    } catch (reason) {
      setError(errorMessage(reason, "Không tải được lịch sử phiên bản."));
    }
  }
  return (
    <details className="order-history" onToggle={(event) => { if (event.currentTarget.open) void load(); }}>
      <summary>Lịch sử phiên bản</summary>
      {error ? <span role="alert">{error}</span> : null}
      {!rows && !error ? <span>Đang tải…</span> : null}
      {rows?.map((row) => <span key={row.version}>Bản {integer.format(row.version)}{row.is_current ? " (đang dùng)" : ""} · {statusLabel(row.status)} · GMV {formatMoney(row.gmv)} · HH {formatMoney(row.estimated_commission)} · từ {row.filename ?? "—"} lúc {formatDateTime(row.recorded_at)}</span>)}
      {rows?.length === 0 ? <span>Chưa có lịch sử phiên bản.</span> : null}
    </details>
  );
}
