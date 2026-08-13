"use client";

import { useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { OrderRow, OrderVersionRow, PageResponse, loadOrderVersions, loadOrders, ordersExportUrl } from "@/lib/api";
import { ORDER_PAGE_SIZES, UrlFilters } from "@/components/filters";
import { Notice, Skeleton, StatusBadge } from "@/components/ui";
import { useApi } from "@/lib/use-api";
import { errorMessage, formatDateTime, formatMoney, integer, statusLabel } from "@/lib/format";
import { AccountIdentity } from "@/components/account-identity";
import type { AccountDirectory } from "@/lib/account-directory";

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

type OrderColumnKey = "account" | "order_id" | "sku_id" | "product_name" | "status" | "order_date" | "units_sold" | "gmv" | "estimated_commission" | "details";

type OrderColumn = {
  key: OrderColumnKey;
  label: string;
  sort?: string;
  defaultVisible?: boolean;
};

const ORDER_COLUMNS: OrderColumn[] = [
  { key: "account", label: "Tài khoản", sort: "account", defaultVisible: true },
  { key: "order_id", label: "Mã đơn", sort: "order_id", defaultVisible: true },
  { key: "sku_id", label: "SKU", sort: "sku_id", defaultVisible: true },
  { key: "product_name", label: "Sản phẩm", sort: "product_name", defaultVisible: true },
  { key: "status", label: "Trạng thái", sort: "status", defaultVisible: true },
  { key: "order_date", label: "Ngày", sort: "order_date", defaultVisible: true },
  { key: "units_sold", label: "SL bán", sort: "units_sold", defaultVisible: true },
  { key: "gmv", label: "GMV", sort: "gmv", defaultVisible: true },
  { key: "estimated_commission", label: "Hoa hồng ước tính", sort: "estimated_commission", defaultVisible: true },
  { key: "details", label: "Chi tiết", defaultVisible: true },
];

const DEFAULT_VISIBLE_COLUMNS = ORDER_COLUMNS.filter((column) => column.defaultVisible).map((column) => column.key);

function filterSummary(filters: UrlFilters) {
  const parts = [
    filters.accounts.length ? `${integer.format(filters.accounts.length)} tài khoản` : "Tất cả tài khoản",
    filters.statuses.length ? `${integer.format(filters.statuses.length)} trạng thái` : "Tất cả trạng thái",
    `${filters.start.split("-").reverse().join("/")} – ${filters.end.split("-").reverse().join("/")}`,
  ];
  if (filters.search) parts.push(`Tìm: ${filters.search}`);
  return parts;
}

function orderCell(column: OrderColumnKey, row: OrderRow, index: number, directory: AccountDirectory) {
  switch (column) {
    case "account": return <AccountIdentity directory={directory} code={row.account} />;
    case "order_id": return row.order_id ?? "—";
    case "sku_id": return row.sku_id ?? "—";
    case "product_name": return <span className="product-cell" title={row.product_name ?? undefined}>{row.product_name ?? "—"}</span>;
    case "status": return <StatusBadge status={row.status} />;
    case "order_date": return formatDateTime(row.order_date);
    case "units_sold": return row.units_sold == null ? "—" : integer.format(row.units_sold);
    case "gmv": return formatMoney(row.gmv);
    case "estimated_commission": return <span title="Hoa hồng ước tính theo file gốc, chưa trừ đơn Không đủ điều kiện">{formatMoney(row.estimated_commission)}</span>;
    case "details": return <OrderDetails row={row} index={index} />;
  }
}

export function OrdersPage({ filters, directory }: { filters: UrlFilters; directory: AccountDirectory }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [visibleColumns, setVisibleColumns] = useState<OrderColumnKey[]>(DEFAULT_VISIBLE_COLUMNS);
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

  function toggleSort(column: string) {
    const next = filters.sort === column && filters.direction === "desc" ? "asc" : "desc";
    navigate({ sort: column, direction: next, page: "1" });
  }

  function toggleColumn(column: OrderColumnKey) {
    setVisibleColumns((current) => current.includes(column) ? current.filter((item) => item !== column) : [...current, column]);
  }

  const activeColumns = useMemo(
    () => ORDER_COLUMNS.filter((column) => visibleColumns.includes(column.key)),
    [visibleColumns],
  );

  if (error) return <Notice text={error} />;
  if (loading || !data) return <Skeleton rows={1} tall label="Đang tải đơn hàng" />;
  const orders = data.items;
  const total = data.total;
  const totalPages = Math.max(1, Math.ceil(total / filters.size));
  const page = Math.min(filters.page, totalPages);
  const startRow = total ? data.offset + 1 : 0;
  const endRow = Math.min(data.offset + orders.length, total);

  return (
    <section className="section panel wide orders-workflow-page">
      <div className="section-heading orders-heading">
        <div>
          <p className="section-label">Danh sách đơn hàng</p>
          <h2>{integer.format(total)} đơn trong bộ lọc</h2>
          <p className="subtle">Đang xem dòng {integer.format(startRow)}–{integer.format(endRow)}. Có thể lưu phạm vi này bằng thanh Chế độ xem phía trên.</p>
        </div>
      </div>

      <div className="orders-sticky-toolbar" aria-label="Thanh thao tác đơn hàng">
        <div className="saved-view-strip" aria-label="Bộ lọc đang áp dụng">
          <strong>Bộ lọc đang áp dụng</strong>
          {filterSummary(filters).map((item) => <span className="saved-view-chip" key={item}>{item}</span>)}
        </div>
        <div className="row-actions">
          <label className="page-size">
            <span>Dòng mỗi trang</span>
            <select value={filters.size} onChange={(event) => navigate({ size: event.target.value, page: "1" })}>
              {ORDER_PAGE_SIZES.map((size) => <option key={size} value={size}>{size}</option>)}
            </select>
          </label>
          <a className="button-link" download="affiliate-orders.xlsx" href={ordersExportUrl({ accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end, search: filters.search })}>Xuất toàn bộ ra Excel</a>
          <button type="button" onClick={() => downloadCsv(`orders-${filters.start}-${filters.end}.csv`, orders)} disabled={!orders.length}>Xuất CSV trang này</button>
        </div>
        <details className="column-controls">
          <summary>Cột hiển thị ({integer.format(activeColumns.length)}/{integer.format(ORDER_COLUMNS.length)})</summary>
          <div className="column-control-grid">
            {ORDER_COLUMNS.map((column) => (
              <label className="column-toggle" key={column.key}>
                <input type="checkbox" checked={visibleColumns.includes(column.key)} onChange={() => toggleColumn(column.key)} />
                {column.label}
              </label>
            ))}
          </div>
        </details>
      </div>

      <div className="table-wrap orders-table" role="region" aria-label="Danh sách đơn hàng, có thể cuộn ngang" tabIndex={0}>
        <table>
          <thead>
            <tr>{activeColumns.map((header) => {
              const active = header.sort && filters.sort === header.sort;
              return (
                <th key={header.key} aria-sort={active ? (filters.direction === "asc" ? "ascending" : "descending") : undefined}>
                  {header.sort
                    ? <button type="button" className="sort-button" onClick={() => toggleSort(header.sort as string)} aria-label={`Sắp xếp theo ${header.label}`}>{header.label}<span aria-hidden="true">{active ? (filters.direction === "asc" ? "↑" : "↓") : "↕"}</span></button>
                    : header.label}
                </th>
              );
            })}</tr>
          </thead>
          <tbody>
            {orders.map((row, index) => (
              <tr key={`${row.account}-${row.order_id}-${row.sku_id}-${index}`}>
                {activeColumns.map((column) => <td key={column.key}>{orderCell(column.key, row, index, directory)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
        {!orders.length ? <p className="empty">Không có đơn phù hợp. Hãy đổi bộ lọc hoặc nhập thêm tệp TikTok.</p> : null}
      </div>

      <div className="orders-card-list" role="list" aria-label="Danh sách đơn hàng trên màn hình nhỏ">
        {orders.map((row, index) => (
          <article className="order-card" role="listitem" key={`${row.business_key}-${index}`}>
            <div className="record-title"><strong>{row.order_id ?? row.sku_id ?? `Dòng ${index + 1}`}</strong><StatusBadge status={row.status} /></div>
            <dl className="order-card-metrics">
              <div><dt>Tài khoản</dt><dd><AccountIdentity directory={directory} code={row.account} /></dd></div>
              <div><dt>Ngày</dt><dd>{formatDateTime(row.order_date)}</dd></div>
              <div><dt>GMV</dt><dd>{formatMoney(row.gmv)}</dd></div>
              <div><dt>Hoa hồng ước tính</dt><dd>{formatMoney(row.estimated_commission)}</dd></div>
            </dl>
            <p className="product-cell">{row.product_name ?? "Chưa có tên sản phẩm"}</p>
            <OrderDetails row={row} index={index} />
          </article>
        ))}
      </div>

      <nav className="pagination" aria-label="Phân trang đơn hàng">
        <button type="button" onClick={() => navigate({ page: String(Math.max(1, page - 1)) })} disabled={page <= 1}>Trang trước</button>
        <span>Trang {integer.format(page)} / {integer.format(totalPages)}</span>
        <button type="button" onClick={() => navigate({ page: String(Math.min(totalPages, page + 1)) })} disabled={page >= totalPages}>Trang sau</button>
      </nav>
    </section>
  );
}

function OrderDetails({ row, index }: { row: OrderRow; index: number }) {
  return (
    <details className="order-detail">
      <summary>{`Chi tiết ${row.order_id ?? row.sku_id ?? index + 1}`}</summary>
      <span>ID sản phẩm: {row.product_id ?? "—"}</span>
      <span>Cửa hàng: {row.shop_name ?? "—"} ({row.shop_id ?? "—"})</span>
      <span>Nội dung: {row.content_type ?? "—"} / {row.content_id ?? "—"}</span>
      <span>Loại đơn: {row.order_type ?? "—"}</span>
      <span>Loại hoa hồng: {row.commission_type ?? "—"}</span>
      <span>Ngày quyết toán: {formatDateTime(row.settlement_date)}</span>
      <span>Hoa hồng thực tế (sau khi trừ không đủ điều kiện): {formatMoney(row.actual_commission)}</span>
      <span>Đã nhận: {formatMoney(row.final_received)}</span>
      <OrderVersions businessKey={row.business_key} />
    </details>
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
