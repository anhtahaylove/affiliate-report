"use client";

import Image from "next/image";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  apiUrl,
  BackupItem,
  checkUpdate,
  CurrentUser,
  DailyRow,
  installUpdate,
  loadDashboard,
  loadBackups,
  loadImportHistory,
  loadMonthlyKpi,
  loadCurrentUser,
  loadMeta,
  loadTargets,
  logout,
  OverviewRow,
  ImportHistoryRow,
  MonthlyKpiRow,
  resetData,
  restoreBackup,
  saveTarget,
  TargetRow,
  UpdateStatus,
  uploadExport,
} from "@/lib/api";

const money = new Intl.NumberFormat("vi-VN", {
  style: "currency",
  currency: "VND",
  maximumFractionDigits: 0,
});

const integer = new Intl.NumberFormat("vi-VN");
const dateTime = new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" });

function formatMoney(value: number | null | undefined) {
  return value == null ? "—" : money.format(Number(value));
}

function errorMessage(reason: unknown, fallback: string) {
  return reason instanceof Error ? reason.message : fallback;
}

function currentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function firstDayOfMonth(month: string) {
  return `${month}-01`;
}

function lastDayOfMonth(month: string) {
  const [year, monthNumber] = month.split("-").map(Number);
  const lastDay = new Date(year, monthNumber, 0).getDate();
  return `${month}-${String(lastDay).padStart(2, "0")}`;
}

function percent(value: number | null) {
  return value == null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : dateTime.format(parsed);
}

function formatBytes(value: number | null | undefined) {
  if (value == null) return "—";
  if (value < 1024 * 1024) return `${integer.format(Math.round(value / 1024))} KB`;
  return `${integer.format(Math.round((value / 1024 / 1024) * 10) / 10)} MB`;
}

function countsText(counts: Record<string, number>) {
  const text = Object.entries(counts)
    .map(([name, count]) => `${name}: ${integer.format(Number(count))}`)
    .join(" · ");
  return text || "Không có bảng";
}

function updateErrorMessage(reason: unknown) {
  const message = errorMessage(reason, "Không thể kiểm tra cập nhật.");
  if (reason instanceof ApiError && [401, 403, 404].includes(reason.status)) {
    return `${message} Kiểm tra token feed private/cấu hình quyền truy cập bản phát hành.`;
  }
  return message;
}

export function Dashboard() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [authError, setAuthError] = useState("");
  const [availableAccounts, setAvailableAccounts] = useState<string[]>([]);
  const [accounts, setAccounts] = useState<string[]>([]);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [month, setMonth] = useState("");
  const [overview, setOverview] = useState<OverviewRow[]>([]);
  const [daily, setDaily] = useState<DailyRow[]>([]);
  const [targets, setTargets] = useState<TargetRow[]>([]);
  const [monthlyKpi, setMonthlyKpi] = useState<MonthlyKpiRow[]>([]);
  const [importHistory, setImportHistory] = useState<ImportHistoryRow[]>([]);
  const [targetDrafts, setTargetDrafts] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [metaError, setMetaError] = useState("");
  const [targetError, setTargetError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [savingTarget, setSavingTarget] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState("");
  const [resetPhrase, setResetPhrase] = useState("");
  const [resetting, setResetting] = useState(false);
  const [resetMessage, setResetMessage] = useState("");
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [backupsLoading, setBackupsLoading] = useState(false);
  const [backupMessage, setBackupMessage] = useState("");
  const [selectedBackupId, setSelectedBackupId] = useState("");
  const [restorePhrase, setRestorePhrase] = useState("");
  const [restoring, setRestoring] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus | null>(null);
  const [updateLoading, setUpdateLoading] = useState(false);
  const [updateMessage, setUpdateMessage] = useState("");
  const [installingUpdate, setInstallingUpdate] = useState(false);

  const canWrite = user?.role === "operator" || user?.role === "owner";
  const isOwner = user?.role === "owner";
  const monthStart = month ? firstDayOfMonth(month) : "";
  const monthEnd = month ? lastDayOfMonth(month) : "";

  const apiBase = apiUrl();
  const apiBaseLabel = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "same-origin";
  const total = useMemo(() => overview.find((row) => row.account === "ALL"), [overview]);
  const accountRows = useMemo(() => overview.filter((row) => row.account !== "ALL"), [overview]);
  const dailyTotals = useMemo(() => daily.filter((row) => row.account === "ALL").slice(0, 14), [daily]);
  const cockpitAccounts = useMemo(() => {
    const names = new Set([...(user?.role === "owner" ? ["ALL"] : []), ...availableAccounts, ...accountRows.map((row) => row.account)]);
    return [...names];
  }, [accountRows, availableAccounts, user?.role]);
  const targetMap = useMemo(() => new Map(targets.map((target) => [target.account, target])), [targets]);
  const selectedLabel = accounts.length ? accounts.join(" + ") : "ALL";
  const kpiMap = useMemo(() => new Map(monthlyKpi.map((row) => [row.account, row])), [monthlyKpi]);
  const activeKpi = accounts.length === 1 ? kpiMap.get(accounts[0]) : kpiMap.get("ALL");
  const activeActualCommission = activeKpi?.actual_commission ?? null;
  const activeDailyTarget = activeKpi?.daily_target ?? null;
  const activeMonthlyTarget = activeKpi?.monthly_target ?? null;
  const activeAchievement = activeKpi?.target_achievement ?? null;
  const activeProgress = Math.max(0, Math.min((activeAchievement ?? 0) * 100, 100));
  const gap = activeKpi?.gap == null ? null : Math.max(-Number(activeKpi.gap), 0);
  const selectedBackup = useMemo(
    () => backups.find((backup) => backup.id === selectedBackupId),
    [backups, selectedBackupId],
  );

  const loadRecentImports = useCallback(async () => {
    try {
      const response = await loadImportHistory(5);
      setImportHistory(response.items);
      setHistoryError("");
    } catch (reason) {
      setImportHistory([]);
      setHistoryError(errorMessage(reason, "Không thể tải lịch sử import."));
    }
  }, []);

  const loadTargetRows = useCallback(async (targetMonth: string) => {
    try {
      const response = await loadTargets(targetMonth);
      setTargets(response.items);
      setTargetDrafts(Object.fromEntries(response.items.map((item) => [item.account, String(item.target_commission)])));
      setTargetError("");
    } catch (reason) {
      setTargets([]);
      setTargetDrafts({});
      setTargetError(errorMessage(reason, "Không thể tải mục tiêu tháng."));
    }
  }, []);

  const loadBackupRows = useCallback(async () => {
    setBackupsLoading(true);
    try {
      const response = await loadBackups();
      setBackups(response.items);
      setSelectedBackupId((current) =>
        current && response.items.some((backup) => backup.id === current && backup.valid)
          ? current
          : (response.items.find((backup) => backup.valid)?.id ?? ""),
      );
      setBackupMessage("");
    } catch (reason) {
      setBackups([]);
      setSelectedBackupId("");
      setBackupMessage(errorMessage(reason, "Không thể tải danh sách backup."));
    } finally {
      setBackupsLoading(false);
    }
  }, []);

  const loadUpdateStatus = useCallback(async () => {
    setUpdateLoading(true);
    try {
      const response = await checkUpdate();
      setUpdateStatus(response);
      setUpdateMessage(
        response.available
          ? `Có bản ${response.latest_version}${response.installable ? " sẵn sàng cài." : " nhưng chưa cài tự động được."}`
          : `Đang ở bản mới nhất (${response.current_version}).`,
      );
    } catch (reason) {
      setUpdateStatus(null);
      setUpdateMessage(updateErrorMessage(reason));
    } finally {
      setUpdateLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [data, kpi] = await Promise.all([
        loadDashboard({ accounts, start, end }),
        loadMonthlyKpi({ month, accounts, start, end }),
      ]);
      setOverview(data.overview);
      setDaily(data.daily);
      setMonthlyKpi(kpi.items);
      await Promise.all([loadTargetRows(month), loadRecentImports()]);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) {
        setAuthError(reason.message || "Phiên đăng nhập đã hết hạn.");
      } else {
        setError(errorMessage(reason, "Không thể tải dữ liệu API."));
      }
    } finally {
      setLoading(false);
    }
  }, [accounts, end, loadRecentImports, loadTargetRows, month, start]);

  useEffect(() => {
    let active = true;
    async function loadInitial() {
      setLoading(true);
      try {
        const currentUser = await loadCurrentUser();
        if (!active) return;
        setUser(currentUser);
        setAuthError("");

        const initialMonth = currentMonth();
        setMonth(initialMonth);
        setStart(firstDayOfMonth(initialMonth));
        setEnd(lastDayOfMonth(initialMonth));
        const [meta, data, kpi] = await Promise.all([
          loadMeta(),
          loadDashboard({ start: firstDayOfMonth(initialMonth), end: lastDayOfMonth(initialMonth) }),
          loadMonthlyKpi({
            month: initialMonth,
            start: firstDayOfMonth(initialMonth),
            end: lastDayOfMonth(initialMonth),
          }),
        ]);
        if (!active) return;
        setAvailableAccounts(meta.accounts);
        setMetaError("");
        setOverview(data.overview);
        setDaily(data.daily);
        setMonthlyKpi(kpi.items);
        await Promise.all([loadTargetRows(initialMonth), loadRecentImports()]);
      } catch (reason) {
        if (!active) return;
        if (reason instanceof ApiError && reason.status === 401) {
          setAuthError(reason.message || "Phiên đăng nhập đã hết hạn.");
        } else {
          setError(errorMessage(reason, "Không thể tải dữ liệu API."));
          setMetaError(errorMessage(reason, "Không thể tải danh sách account."));
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    void loadInitial();
    return () => {
      active = false;
    };
  }, [loadRecentImports, loadTargetRows]);

  useEffect(() => {
    if (user?.role !== "owner") return;
    async function loadOwnerPanels() {
      await Promise.all([loadBackupRows(), loadUpdateStatus()]);
    }
    void loadOwnerPanels();
  }, [loadBackupRows, loadUpdateStatus, user?.role]);

  function toggleAccount(account: string) {
    setAccounts((current) =>
      current.includes(account) ? current.filter((item) => item !== account) : [...current, account],
    );
  }

  async function handleTargetSave(account: string) {
    const draft = (targetDrafts[account] ?? "").trim();
    if (!/^\d+$/.test(draft)) {
      setTargetError("KPI/ngày phải là số nguyên không âm, không để trống và không nhập số thập phân.");
      return;
    }
    const value = Number(draft);
    setSavingTarget(account);
    setTargetError("");
    try {
      await saveTarget(account, month, value);
      await refresh();
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) {
        setAuthError(reason.message || "Phiên đăng nhập đã hết hạn.");
      } else {
        setTargetError(errorMessage(reason, "Không thể lưu mục tiêu."));
      }
    } finally {
      setSavingTarget("");
    }
  }

  async function handleResetData(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isOwner) return;
    const phrase = resetPhrase.trim();
    if (phrase !== "XOA DU LIEU") {
      setResetMessage("Nhập đúng cụm XOA DU LIEU để mở khóa reset.");
      return;
    }
    if (!window.confirm("Xóa toàn bộ dữ liệu import/report? Hệ thống sẽ tạo backup trước khi xóa.")) return;

    setResetting(true);
    setResetMessage("");
    try {
      const result = await resetData(phrase);
      const deleted = result.deleted_counts;
      const deletedText = Object.entries(deleted)
        .map(([name, count]) => `${name}: ${integer.format(Number(count))}`)
        .join(" · ");
      setResetPhrase("");
      setResetMessage(`Đã xóa dữ liệu. Backup: ${result.backup_path}${deletedText ? `. Đã xóa: ${deletedText}` : ""}. Khôi phục ${integer.format(result.default_targets_restored)} target mặc định.`);
      await Promise.all([refresh(), loadBackupRows()]);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) {
        setAuthError(reason.message || "Phiên đăng nhập đã hết hạn.");
      } else {
        setResetMessage(errorMessage(reason, "Reset dữ liệu thất bại."));
      }
    } finally {
      setResetting(false);
    }
  }

  async function handleRestoreBackup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isOwner) return;
    const phrase = restorePhrase.trim();
    if (!selectedBackup) {
      setBackupMessage("Hãy chọn một backup hợp lệ để khôi phục.");
      return;
    }
    if (!selectedBackup.valid) {
      setBackupMessage("Backup đang chọn không hợp lệ; không thể khôi phục.");
      return;
    }
    if (phrase !== "KHOI PHUC DU LIEU") {
      setBackupMessage("Nhập đúng cụm KHOI PHUC DU LIEU để mở khóa khôi phục.");
      return;
    }
    if (!window.confirm(`Khôi phục backup ${selectedBackup.filename}? Dữ liệu hiện tại sẽ được backup an toàn trước khi ghi đè.`)) return;

    setRestoring(true);
    setBackupMessage("");
    try {
      const result = await restoreBackup(selectedBackup.id, phrase);
      setRestorePhrase("");
      setBackupMessage(`Đã khôi phục. Safety backup: ${result.safety_backup_path}. Bảng: ${countsText(result.restored_counts)}.`);
      await Promise.all([refresh(), loadBackupRows()]);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) {
        setAuthError(reason.message || "Phiên đăng nhập đã hết hạn.");
      } else {
        setBackupMessage(errorMessage(reason, "Khôi phục backup thất bại."));
      }
    } finally {
      setRestoring(false);
    }
  }

  async function handleInstallUpdate() {
    if (!isOwner || !updateStatus?.available || !updateStatus.installable || !updateStatus.automatic_install_supported) return;
    if (!window.confirm("Cài bản cập nhật ngay? Ứng dụng sẽ đóng và mở lại sau khi cài xong.")) return;

    setInstallingUpdate(true);
    setUpdateMessage("");
    try {
      const result = await installUpdate("CAP NHAT UNG DUNG");
      setUpdateMessage(`Đang cài bản ${result.version} (${result.status}). Ứng dụng sẽ đóng và mở lại sau khi hoàn tất. SHA256: ${result.sha256}.`);
    } catch (reason) {
      setUpdateMessage(updateErrorMessage(reason));
    } finally {
      setInstallingUpdate(false);
    }
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canWrite) {
      setUploadMessage("Tài khoản viewer không có quyền import dữ liệu.");
      return;
    }
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
      const imported = Number(result.inserted ?? 0) + Number(result.updated ?? 0) + Number(result.unchanged ?? 0);
      setUploadMessage(
        result.duplicate
          ? "File này đã được import trước đó; dữ liệu không bị nhân đôi."
          : `Đã import ${integer.format(imported)} dòng cho ${account}.`,
      );
      await refresh();
      event.currentTarget.reset();
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 401) {
        setAuthError(reason.message || "Phiên đăng nhập đã hết hạn.");
      } else {
        setUploadMessage(errorMessage(reason, "Import thất bại."));
      }
    } finally {
      setUploading(false);
    }
  }

  async function handleLogout() {
    try {
      await logout();
    } finally {
      window.location.href = `${apiUrl()}/auth/login`;
    }
  }

  if (authError) {
    return (
      <main className="auth-shell">
        <section className="auth-card panel">
          <div className="brand-badge">AFF</div>
          <h1>TikTok Affiliate Report</h1>
          <p>Vui lòng đăng nhập để xem Operations Cockpit.</p>
          <a className="button-link" href={`${apiBase}/auth/login`}>
            Đăng nhập
          </a>
          <p className="hint">{authError}</p>
        </section>
      </main>
    );
  }

  return (
    <main className="cockpit-shell">
      <aside className="sidebar" aria-label="Điều hướng chính">
        <div className="sidebar-brand">
          <Image className="brand-mark" src="/icon-192.png" alt="" width={42} height={42} priority />
          <div>
            <strong>TikTok Affiliate</strong>
            <span>Operations Cockpit</span>
          </div>
        </div>
        <nav>
          <a href="#dashboard" aria-current="page">Dashboard</a>
          <a href="#targets">Mục tiêu</a>
          {canWrite ? <a href="#import">Import</a> : null}
          {isOwner ? <a href="#backup-restore">Backup</a> : null}
          {isOwner ? <a href="#app-update">Cập nhật</a> : null}
          <a href="#accounts">Account</a>
        </nav>
        <div className={`health-card${error || metaError ? " offline" : ""}`}>
          <span>{error || metaError ? "API lỗi" : "API online"}</span>
          <small>{apiBaseLabel}</small>
        </div>
      </aside>

      <section className="cockpit-main" id="dashboard">
        <header className="cockpit-header">
          <div>
            <p className="section-label">Dashboard · {month}</p>
            <h1>Tổng quan hiệu suất</h1>
            <p className="subtle">Theo dõi hoa hồng, tiến độ target và import chồng lặp theo từng account.</p>
          </div>
          {user ? (
          <div className="user-menu" role="group" aria-label="Tài khoản hiện tại">
              <span>{user.email}</span>
              <strong>{user.role}</strong>
              <button type="button" onClick={handleLogout}>Đăng xuất</button>
            </div>
          ) : null}
        </header>

        <form
          className="command-bar panel"
          onSubmit={(event) => {
            event.preventDefault();
            void refresh();
          }}
        >
          <div className="field compact">
            <label htmlFor="target-month">Tháng KPI</label>
            <input
              id="target-month"
              type="month"
              value={month}
              required
              onChange={(event) => {
                const nextMonth = event.target.value;
                if (!nextMonth) return;
                setMonth(nextMonth);
                setStart(firstDayOfMonth(nextMonth));
                setEnd(lastDayOfMonth(nextMonth));
                void loadTargetRows(nextMonth);
              }}
            />
          </div>
          <div className="field compact">
            <label htmlFor="start-date">Từ ngày</label>
            <input id="start-date" type="date" value={start} min={monthStart || undefined} max={end || monthEnd || undefined} onChange={(event) => setStart(event.target.value)} />
          </div>
          <div className="field compact">
            <label htmlFor="end-date">Đến ngày</label>
            <input id="end-date" type="date" value={end} min={start || monthStart || undefined} max={monthEnd || undefined} onChange={(event) => setEnd(event.target.value)} />
          </div>
          <div className="filter-stack">
            <span className="field-label">Account</span>
            <div className="account-options" role="group" aria-label="Lọc theo account">
              {availableAccounts.map((account) => (
                <label className="account-option" key={account}>
                  <input type="checkbox" checked={accounts.includes(account)} onChange={() => toggleAccount(account)} />
                  {account}
                </label>
              ))}
            </div>
          </div>
          <button className="primary" type="submit" disabled={loading}>{loading ? "Đang tải…" : "Áp dụng"}</button>
        </form>

        {[error, metaError, targetError, historyError].filter(Boolean).map((message) => (
          <div className="notice" role="alert" key={message}>{message}</div>
        ))}

        <section className="hero-grid" aria-label="Tổng quan KPI">
          <article className="metric panel"><span>Đơn hàng</span><strong>{total ? integer.format(total.orders) : "—"}</strong><small>{total ? integer.format(total.order_lines) : "—"} dòng đơn</small></article>
          <article className="metric panel"><span>GMV thực tế</span><strong>{total ? formatMoney(total.actual_gmv) : "—"}</strong><small>GMV gốc {total ? formatMoney(total.gmv) : "—"}</small></article>
          <article className="metric panel"><span>Hoa hồng thực tế</span><strong>{formatMoney(activeActualCommission)}</strong><small>{selectedLabel} · KPI/ngày {formatMoney(activeDailyTarget)}</small></article>
          <article className="metric progress-metric panel">
            <span>Tiến độ mục tiêu</span>
            <strong>{percent(activeAchievement)}</strong>
            <div className="progress-track" role="progressbar" aria-label="Tiến độ hoa hồng" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Number(activeProgress.toFixed(1))}>
              <span style={{ width: `${activeProgress}%` }} />
            </div>
            <small>Target tháng {formatMoney(activeMonthlyTarget)}</small>
          </article>
          <article className="metric danger-metric panel"><span>Còn thiếu</span><strong>{formatMoney(gap)}</strong><small>{selectedLabel} · {month}</small></article>
        </section>

        <div className="content-grid">
          <section className="section panel" id="targets">
            <div className="section-heading">
              <div>
                <p className="section-label">Sửa KPI/ngày</p>
                <h2>Mục tiêu theo account</h2>
                <p>Giá trị đang sửa là KPI/ngày; target tháng được tính bằng KPI/ngày × số ngày trong phạm vi.</p>
              </div>
              {!canWrite ? <span className="read-only">Viewer chỉ xem</span> : null}
            </div>
            <div className="target-list">
              {cockpitAccounts.map((account) => {
                const row = accountRows.find((item) => item.account === account);
                const actual = kpiMap.get(account)?.actual_commission ?? (account === "ALL" ? total?.actual_commission : row?.actual_commission) ?? null;
                const targetDraft = targetDrafts[account] ?? "";
                const savedTarget = targetMap.get(account)?.target_commission ?? null;
                const achievement = kpiMap.get(account)?.target_achievement ?? null;
                return (
                  <div className="target-row" key={account}>
                    <div>
                      <strong>{account}</strong>
                      <span>HH {formatMoney(actual)} · KPI/ngày {formatMoney(savedTarget)} · {percent(achievement)}</span>
                    </div>
                    <input
                      type="number"
                      min="0"
                      max="1000000000000"
                      step="1"
                      aria-label={`KPI ngày ${account}`}
                      value={targetDraft}
                      onChange={(event) => setTargetDrafts((current) => ({ ...current, [account]: event.target.value }))}
                      disabled={!canWrite || savingTarget === account}
                      placeholder="0"
                    />
                    <button type="button" onClick={() => void handleTargetSave(account)} disabled={!canWrite || savingTarget === account}>
                      {savingTarget === account ? "Lưu…" : "Lưu"}
                    </button>
                  </div>
                );
              })}
            </div>
          </section>

          {canWrite ? (
            <section className="section panel" id="import">
              <div className="section-heading">
                <div>
                  <p className="section-label">Import dữ liệu</p>
                  <h2>Import file TikTok</h2>
                  <p>Upload theo account; backend giữ chống trùng file export bị chồng lặp.</p>
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
                <div className="field dropzone">
                  <label htmlFor="upload-file">File export .xlsx</label>
                  <input id="upload-file" name="file" type="file" accept=".xlsx" required />
                  <span>Kéo thả hoặc chọn file export từ TikTok App.</span>
                </div>
                <button className="primary" type="submit" disabled={uploading || !availableAccounts.length}>
                  {uploading ? "Đang import…" : "Import dữ liệu"}
                </button>
                {uploadMessage ? <p className="upload-result" aria-live="polite">{uploadMessage}</p> : null}
              </form>
            </section>
          ) : null}

          {isOwner ? (
            <section className="section danger-zone panel wide" aria-labelledby="reset-data-title">
              <div className="section-heading">
                <div>
                  <p className="section-label danger-label">Danger zone</p>
                  <h2 id="reset-data-title">Reset dữ liệu</h2>
                  <p>Xóa dữ liệu import/report hiện tại sau khi backend tạo backup. Chỉ owner được thực hiện.</p>
                </div>
              </div>
              <form className="reset-form" onSubmit={handleResetData}>
                <div className="field">
                  <label htmlFor="reset-confirmation">Nhập chính xác <strong>XOA DU LIEU</strong></label>
                  <input
                    id="reset-confirmation"
                    value={resetPhrase}
                    onChange={(event) => setResetPhrase(event.target.value)}
                    autoComplete="off"
                    aria-describedby="reset-help"
                    disabled={resetting}
                  />
                  <span id="reset-help">Reset sẽ refresh dashboard và lịch sử import sau khi hoàn tất.</span>
                </div>
                <button className="danger-button" type="submit" disabled={resetting || resetPhrase.trim() !== "XOA DU LIEU"}>
                  {resetting ? "Đang reset…" : "Reset dữ liệu"}
                </button>
                {resetMessage ? <p className="reset-result" role="status" aria-live="polite">{resetMessage}</p> : null}
              </form>
            </section>
          ) : null}

          {isOwner ? (
            <section className="section danger-zone panel wide" id="backup-restore" aria-labelledby="restore-backup-title">
              <div className="section-heading">
                <div>
                  <p className="section-label danger-label">Owner backup</p>
                  <h2 id="restore-backup-title">Khôi phục backup</h2>
                  <p>Chọn backup hợp lệ, xem trước số bảng/dòng, rồi nhập cụm xác nhận để restore.</p>
                </div>
                <button type="button" onClick={() => void loadBackupRows()} disabled={backupsLoading || restoring}>
                  {backupsLoading ? "Đang tải…" : "Tải lại"}
                </button>
              </div>
              <form className="reset-form" onSubmit={handleRestoreBackup}>
                <div className="backup-list" role="radiogroup" aria-label="Chọn backup để khôi phục">
                  {backups.length ? backups.map((backup) => (
                    <label className={`backup-item${backup.valid ? "" : " invalid"}`} key={backup.id}>
                      <input
                        type="radio"
                        name="backup-id"
                        checked={selectedBackupId === backup.id}
                        onChange={() => setSelectedBackupId(backup.id)}
                        disabled={restoring || !backup.valid}
                      />
                      <span>
                        <strong>{backup.filename}</strong>
                        <small>{formatDateTime(backup.created_at)} · {formatBytes(backup.size_bytes)} · {backup.valid ? "Hợp lệ" : `Không hợp lệ: ${backup.error || "lỗi backup"}`}</small>
                        <small>Dữ liệu báo cáo: {countsText(backup.counts.business)}</small>
                        <small>Tài khoản trong backup (chỉ xem trước, không ghi đè): {countsText(backup.counts.auth)}</small>
                      </span>
                    </label>
                  )) : <p className="empty">{backupsLoading ? "Đang tải backup…" : "Chưa có backup."}</p>}
                </div>
                <div className="field">
                  <label htmlFor="restore-confirmation">Nhập chính xác <strong>KHOI PHUC DU LIEU</strong></label>
                  <input
                    id="restore-confirmation"
                    value={restorePhrase}
                    onChange={(event) => setRestorePhrase(event.target.value)}
                    autoComplete="off"
                    aria-describedby="restore-help"
                    disabled={restoring}
                  />
                  <span id="restore-help">Restore sẽ tạo safety backup, sau đó refresh dashboard và danh sách backup.</span>
                </div>
                <button className="danger-button" type="submit" disabled={restoring || restorePhrase.trim() !== "KHOI PHUC DU LIEU" || !selectedBackup?.valid}>
                  {restoring ? "Đang khôi phục…" : "Khôi phục backup"}
                </button>
                {backupMessage ? <p className="reset-result" role="status" aria-live="polite">{backupMessage}</p> : null}
              </form>
            </section>
          ) : null}

          {isOwner ? (
            <section className="section panel" id="app-update" aria-labelledby="app-update-title">
              <div className="section-heading">
                <div>
                  <p className="section-label">Ứng dụng</p>
                  <h2 id="app-update-title">Cập nhật phiên bản</h2>
                  <p>Dashboard tự kiểm tra một lần cho owner; có thể kiểm tra lại thủ công.</p>
                </div>
                <button type="button" onClick={() => void loadUpdateStatus()} disabled={updateLoading || installingUpdate}>
                  {updateLoading ? "Đang kiểm tra…" : "Check"}
                </button>
              </div>
              <div className="update-panel" aria-live="polite">
                <div className="update-versions">
                  <span>Hiện tại <strong>{updateStatus?.current_version ?? "—"}</strong></span>
                  <span>Mới nhất <strong>{updateStatus?.latest_version ?? "—"}</strong></span>
                  <span>Trạng thái <strong>{updateStatus ? (updateStatus.available ? "Có cập nhật" : "Mới nhất") : "Chưa kiểm tra"}</strong></span>
                </div>
                {updateStatus?.release_name ? <p><strong>{updateStatus.release_name}</strong></p> : null}
                {updateStatus?.published_at ? <p>Phát hành: {formatDateTime(updateStatus.published_at)}</p> : null}
                {updateStatus?.source_repo ? <p>Nguồn: {updateStatus.source_repo}</p> : null}
                {updateStatus?.notes ? <p className="update-notes" tabIndex={0}>{updateStatus.notes}</p> : null}
                {updateStatus?.release_url ? <a className="button-link secondary-link" href={updateStatus.release_url} target="_blank" rel="noreferrer">Xem release</a> : null}
                {updateStatus && !updateStatus.automatic_install_supported ? <p className="hint">Cài tự động chỉ khả dụng trong bản Windows đã cài đặt.</p> : null}
                <button className="primary" type="button" onClick={() => void handleInstallUpdate()} disabled={!updateStatus?.available || !updateStatus.installable || !updateStatus.automatic_install_supported || installingUpdate || updateLoading}>
                  {installingUpdate ? "Đang cài…" : "Cài cập nhật"}
                </button>
                <p className="hint">Khi cài, ứng dụng sẽ đóng và mở lại sau khi updater hoàn tất.</p>
                {updateMessage ? <p className="upload-result" role="status">{updateMessage}</p> : null}
              </div>
            </section>
          ) : null}

          <section className="section panel" id="recent-imports">
            <div className="section-heading">
              <div>
                <p className="section-label">Audit import</p>
                <h2>Import gần đây</h2>
              </div>
            </div>
            <div className="import-list">
              {importHistory.length ? importHistory.map((item) => (
                <article className="import-item" key={item.id}>
                  <strong>{item.filename}</strong>
                  <span>{item.account} · +{integer.format(item.inserted)} / cập nhật {integer.format(item.updated)} / trùng {integer.format(item.unchanged)} / lỗi {integer.format(item.rejected)}</span>
                  <time dateTime={item.created_at}>{formatDateTime(item.created_at)}</time>
                </article>
              )) : <p className="empty">Chưa có lịch sử import.</p>}
            </div>
          </section>

          <section className="section panel wide">
            <div className="section-heading">
              <div>
                <p className="section-label">Nhịp ngày</p>
                <h2>14 ngày gần nhất</h2>
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
                        <td>{percent(row.target_achievement)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : <p className="empty">Chưa có dữ liệu trong bộ lọc.</p>}
            </div>
          </section>

          <section className="section panel wide" id="accounts">
            <div className="section-heading">
              <div>
                <p className="section-label">Theo account</p>
                <h2>So sánh account</h2>
              </div>
            </div>
            <div className="table-wrap">
              {accountRows.length ? (
                <table>
                  <thead><tr><th>Account</th><th>Đơn</th><th>GMV</th><th>GMV thực tế</th><th>Hoa hồng</th><th>Target</th><th>Đạt</th></tr></thead>
                  <tbody>
                    {accountRows.map((row) => {
                      const target = targetMap.get(row.account)?.target_commission ?? null;
                      return (
                        <tr key={row.account}>
                          <td>{row.account}</td>
                          <td>{integer.format(row.orders)}</td>
                          <td>{formatMoney(row.gmv)}</td>
                          <td>{formatMoney(row.actual_gmv)}</td>
                          <td>{formatMoney(row.actual_commission)}</td>
                          <td>{target == null ? "—" : `${formatMoney(target)}/ngày`}</td>
                          <td>{percent(kpiMap.get(row.account)?.target_achievement ?? null)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : <p className="empty">Chưa có dữ liệu account.</p>}
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}
