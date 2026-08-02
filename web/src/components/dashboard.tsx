"use client";

import Image from "next/image";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  API_URL,
  DailyRow,
  loadDashboard,
  loadMeta,
  OverviewRow,
  uploadExport,
} from "@/lib/api";

const money = new Intl.NumberFormat("vi-VN", {
  style: "currency",
  currency: "VND",
  maximumFractionDigits: 0,
});

const integer = new Intl.NumberFormat("vi-VN");

function formatMoney(value: number | null | undefined) {
  return money.format(Number(value ?? 0));
}

export function Dashboard() {
  const [availableAccounts, setAvailableAccounts] = useState<string[]>([]);
  const [accounts, setAccounts] = useState<string[]>([]);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [overview, setOverview] = useState<OverviewRow[]>([]);
  const [daily, setDaily] = useState<DailyRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [metaError, setMetaError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await loadDashboard({ accounts, start, end });
      setOverview(data.overview);
      setDaily(data.daily);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể tải dữ liệu API.");
    } finally {
      setLoading(false);
    }
  }, [accounts, end, start]);

  useEffect(() => {
    loadMeta()
      .then((meta) => {
        setAvailableAccounts(meta.accounts);
        setMetaError("");
      })
      .catch((reason) => {
        setAvailableAccounts([]);
        setMetaError(reason instanceof Error ? reason.message : "Không thể tải danh sách account.");
      });
  }, []);

  useEffect(() => {
    let active = true;
    loadDashboard({})
      .then((data) => {
        if (!active) return;
        setOverview(data.overview);
        setDaily(data.daily);
      })
      .catch((reason) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "Không thể tải dữ liệu API.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const total = useMemo(
    () => overview.find((row) => row.account === "ALL"),
    [overview],
  );
  const accountRows = overview.filter((row) => row.account !== "ALL");
  const dailyTotals = daily.filter((row) => row.account === "ALL").slice(0, 14);

  function toggleAccount(account: string) {
    setAccounts((current) =>
      current.includes(account)
        ? current.filter((item) => item !== account)
        : [...current, account],
    );
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const account = String(form.get("account") ?? "");
    const file = form.get("file");
    if (!account || !(file instanceof File) || !file.size) {
      setUploadMessage("Hãy chọn account và file TikTok .xlsx.");
      return;
    }

    setUploading(true);
    setUploadMessage("");
    try {
      const result = await uploadExport(account, file);
      const imported =
        Number(result.inserted ?? 0) +
        Number(result.updated ?? 0) +
        Number(result.unchanged ?? 0);
      const duplicate = Boolean(result.duplicate);
      setUploadMessage(
        duplicate
          ? "File này đã được import trước đó; dữ liệu không bị nhân đôi."
          : `Đã import ${integer.format(imported)} dòng cho ${account}.`,
      );
      await refresh();
      event.currentTarget.reset();
    } catch (reason) {
      setUploadMessage(reason instanceof Error ? reason.message : "Import thất bại.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <Image className="brand-mark" src="/icon-192.png" alt="" width={44} height={44} priority />
          <div>
            <h1>TikTok Affiliate Report</h1>
            <p>Phase 2 PWA dùng chung dữ liệu với dashboard Python</p>
          </div>
        </div>
        <span className={`api-state${error || metaError ? " offline" : ""}`}>
          {error || metaError ? "API chưa sẵn sàng" : "API sẵn sàng"}: {API_URL}
        </span>
      </header>

      <form
        className="filters panel"
        onSubmit={(event) => {
          event.preventDefault();
          void refresh();
        }}
      >
        <div className="field">
          <label htmlFor="start-date">Từ ngày</label>
          <input id="start-date" type="date" value={start} onChange={(event) => setStart(event.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="end-date">Đến ngày</label>
          <input id="end-date" type="date" value={end} onChange={(event) => setEnd(event.target.value)} />
        </div>
        <div className="field-label">Account</div>
        <div className="account-options" role="group" aria-label="Lọc theo account">
          {availableAccounts.map((account) => (
            <label className="account-option" key={account}>
              <input
                type="checkbox"
                checked={accounts.includes(account)}
                onChange={() => toggleAccount(account)}
              />
              {account}
            </label>
          ))}
        </div>
        <button className="primary" type="submit" disabled={loading}>
          {loading ? "Đang tải…" : "Áp dụng"}
        </button>
      </form>

      {error ? (
        <div className="notice" role="alert">
          Không kết nối được API. Hãy chạy <code>python run_api.py</code>. Chi tiết: {error}
        </div>
      ) : null}

      {metaError ? (
        <div className="notice" role="alert">
          Không tải được danh sách account; bộ lọc và upload đang tạm khóa. Chi tiết: {metaError}
        </div>
      ) : null}

      <section className="metrics" aria-label="Tổng quan">
        <article className="metric panel"><span>Đơn hàng</span><strong>{total ? integer.format(total.orders) : "—"}</strong></article>
        <article className="metric panel"><span>Sản phẩm bán</span><strong>{total ? integer.format(total.units_sold) : "—"}</strong></article>
        <article className="metric panel"><span>Tổng GMV</span><strong>{total ? formatMoney(total.gmv) : "—"}</strong></article>
        <article className="metric panel"><span>GMV thực tế</span><strong>{total ? formatMoney(total.actual_gmv) : "—"}</strong></article>
        <article className="metric panel"><span>Hoa hồng thực tế</span><strong>{total ? formatMoney(total.actual_commission) : "—"}</strong></article>
      </section>

      <div className="content-grid">
        <section className="section panel">
          <div className="section-heading">
            <div>
              <h2>14 ngày gần nhất</h2>
              <p>Tổng hợp theo ngày từ dữ liệu TikTok hiện hành.</p>
            </div>
          </div>
          <div className="table-wrap">
            {dailyTotals.length ? (
              <table>
                <thead><tr><th>Ngày</th><th>Đơn</th><th>GMV thực tế</th><th>Hoa hồng</th><th>Đạt KPI</th></tr></thead>
                <tbody>
                  {dailyTotals.map((row) => (
                    <tr key={row.day}>
                      <td>{row.day}</td>
                      <td>{integer.format(row.orders)}</td>
                      <td>{formatMoney(row.actual_gmv)}</td>
                      <td>{formatMoney(row.actual_commission)}</td>
                      <td>{row.target_achievement == null ? "—" : `${(row.target_achievement * 100).toFixed(1)}%`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <p className="empty">Chưa có dữ liệu trong bộ lọc.</p>}
          </div>
        </section>

        <section className="section panel">
          <div className="section-heading">
            <div>
              <h2>Import file TikTok</h2>
              <p>Account là bắt buộc; hệ thống giữ cơ chế chống trùng hiện tại.</p>
            </div>
          </div>
          <form className="upload-form" onSubmit={handleUpload}>
            <div className="field">
              <label htmlFor="upload-account">Affiliate account</label>
              <select id="upload-account" name="account" required defaultValue="" disabled={!availableAccounts.length}>
                <option value="" disabled>Chọn account</option>
                {availableAccounts.map((account) => <option key={account}>{account}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="upload-file">File export .xlsx</label>
              <input id="upload-file" name="file" type="file" accept=".xlsx" required />
            </div>
            <button className="primary" type="submit" disabled={uploading || !availableAccounts.length}>
              {uploading ? "Đang import…" : "Import dữ liệu"}
            </button>
            {uploadMessage ? <p className="upload-result" aria-live="polite">{uploadMessage}</p> : null}
          </form>
        </section>

        <section className="section panel">
          <div className="section-heading">
            <div>
              <h2>So sánh account</h2>
              <p>Số chính xác từ file TikTok export, không áp dụng rounding thủ công.</p>
            </div>
          </div>
          <div className="table-wrap">
            {accountRows.length ? (
              <table>
                <thead><tr><th>Account</th><th>Đơn</th><th>GMV</th><th>GMV thực tế</th><th>Hoa hồng</th></tr></thead>
                <tbody>
                  {accountRows.map((row) => (
                    <tr key={row.account}>
                      <td>{row.account}</td>
                      <td>{integer.format(row.orders)}</td>
                      <td>{formatMoney(row.gmv)}</td>
                      <td>{formatMoney(row.actual_gmv)}</td>
                      <td>{formatMoney(row.actual_commission)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <p className="empty">Chưa có dữ liệu account.</p>}
          </div>
        </section>
      </div>
    </main>
  );
}
