"use client";

import { useCallback, useEffect, useState } from "react";
import { CurrentUser, MonthlyKpiRow, TargetRow, copyPreviousTargets, loadMonthlyKpi, loadTargets, saveTarget } from "@/lib/api";
import { UrlFilters } from "@/components/filters";
import { canWrite } from "@/components/ui";
import { invalidateApiCache } from "@/lib/use-api";
import { achievementTone, errorMessage, formatMoney, integer, percent } from "@/lib/format";
import { AccountIdentity } from "@/components/account-identity";
import type { AccountDirectory } from "@/lib/account-directory";

function previousMonthOf(month: string) {
  const [year, monthNumber] = month.split("-").map(Number);
  const previous = new Date(year, monthNumber - 2, 1);
  return `${previous.getFullYear()}-${String(previous.getMonth() + 1).padStart(2, "0")}`;
}

function monthLabel(month: string) {
  const [year, monthNumber] = month.split("-");
  return `${monthNumber}/${year}`;
}

export function TargetsPage({ user, filters, accounts, directory }: { user: CurrentUser; filters: UrlFilters; accounts: string[]; directory: AccountDirectory }) {
  const [targets, setTargets] = useState<TargetRow[]>([]);
  const [kpi, setKpi] = useState<MonthlyKpiRow[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState("");
  const [copying, setCopying] = useState(false);
  const [message, setMessage] = useState("");
  const scopedAccounts = filters.accounts.length ? accounts.filter((account) => filters.accounts.includes(account)) : accounts;
  const allowedAccounts = user.role === "owner" ? ["ALL", ...scopedAccounts] : scopedAccounts;
  const previousMonth = previousMonthOf(filters.month);
  const refresh = useCallback(async () => {
    const [targetData, monthly] = await Promise.all([
      loadTargets(filters.month),
      loadMonthlyKpi({ accounts: filters.accounts, start: filters.start, end: filters.end }),
    ]);
    setTargets(targetData.items);
    setDrafts(Object.fromEntries(targetData.items.map((item) => [item.account, String(item.daily_target_commission)])));
    setKpi(monthly.items);
  }, [filters.accounts, filters.end, filters.month, filters.start]);
  useEffect(() => {
    async function load() {
      try { await refresh(); }
      catch (reason) { setMessage(errorMessage(reason, "Không thể tải mục tiêu.")); }
    }
    void load();
  }, [refresh]);
  async function save(account: string) {
    const draft = (drafts[account] ?? "").trim();
    if (!/^\d+$/.test(draft)) return setMessage("Vui lòng nhập một số nguyên từ 0 trở lên (không dấu chấm/phẩy).");
    setSaving(account);
    try {
      await saveTarget(account, filters.month, Number(draft));
      invalidateApiCache();
      setMessage(`Đã lưu KPI/ngày cho ${directory.label(account)}.`);
      await refresh();
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể lưu mục tiêu."));
    } finally {
      setSaving("");
    }
  }
  async function copyPrevious() {
    setCopying(true);
    try {
      const result = await copyPreviousTargets(filters.month);
      invalidateApiCache();
      const kept = result.kept.length ? ` Giữ nguyên ${integer.format(result.kept.length)} tài khoản đã có KPI.` : "";
      setMessage(result.copied.length
        ? `Đã chép KPI của ${integer.format(result.copied.length)} tài khoản từ tháng ${monthLabel(result.from_month)}.${kept}`
        : `Tháng ${monthLabel(result.from_month)} không có KPI nào để chép.${kept}`);
      await refresh();
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể chép KPI từ tháng trước."));
    } finally {
      setCopying(false);
    }
  }
  const targetMap = new Map(targets.map((target) => [target.account, target]));
  const kpiMap = new Map(kpi.map((row) => [row.account, row]));
  return (
    <section className="section panel wide targets-workflow-page">
      <div className="section-heading">
        <div>
          <p className="section-label">Mục tiêu hoa hồng mỗi ngày (KPI)</p>
          <h2>Lập mục tiêu tháng {monthLabel(filters.month)}</h2>
          <p className="subtle">Tiến độ tính trên phạm vi đang lọc: {filters.start.split("-").reverse().join("/")} – {filters.end.split("-").reverse().join("/")}.</p>
        </div>
        {canWrite(user) ? <button type="button" onClick={() => void copyPrevious()} disabled={copying}>{copying ? "Đang chép…" : `Chép từ ${monthLabel(previousMonth)}`}</button> : <span className="read-only">Chỉ xem</span>}
      </div>
      <div className="target-context panel-muted">
        <strong>Lưu ý</strong>
        <span>Nếu tháng {monthLabel(previousMonth)} có dữ liệu, nút chép sẽ tạo KPI còn thiếu và giữ nguyên KPI đã nhập cho tháng hiện tại.</span>
      </div>
      <div className="target-planner-grid">
        {allowedAccounts.map((account) => {
          const target = targetMap.get(account);
          const row = kpiMap.get(account);
          const achievement = row?.target_achievement;
          const draft = drafts[account] ?? "";
          return (
            <article className="target-card" key={account}>
              <div className="record-title">
                <div>
                  <AccountIdentity directory={directory} code={account} />
                  <span>{account === "ALL" ? "Mục tiêu mặc định cho toàn bộ tài khoản" : "Mục tiêu riêng theo tài khoản"}</span>
                </div>
                <span className="tone-text" data-tone={achievementTone(achievement)}>{percent(achievement)}</span>
              </div>
              <dl className="target-metrics">
                <div><dt>Hoa hồng thực tế</dt><dd>{formatMoney(row?.actual_commission)}</dd></div>
                <div><dt>KPI/ngày hiện tại</dt><dd>{formatMoney(target?.daily_target_commission)}</dd></div>
                <div><dt>KPI tháng</dt><dd>{formatMoney(row?.monthly_target)}</dd></div>
                <div><dt>Chênh lệch</dt><dd className="tone-text" data-tone={row?.gap == null ? undefined : row.gap < 0 ? "critical" : "good"}>{row?.gap == null ? "—" : row.gap < 0 ? `Còn thiếu ${formatMoney(Math.abs(row.gap))}` : `Vượt mục tiêu ${formatMoney(row.gap)}`}</dd></div>
              </dl>
              <div className="target-edit-row">
                <div className="field">
                  <label htmlFor={`target-${account}`}>KPI/ngày mới</label>
                  <input id={`target-${account}`} type="number" min="0" step="1" value={draft} onChange={(event) => setDrafts((current) => ({ ...current, [account]: event.target.value }))} disabled={!canWrite(user) || saving === account} aria-label={`KPI ngày ${directory.get(account).accessibleName}`} />
                </div>
                <button type="button" onClick={() => void save(account)} disabled={!canWrite(user) || saving === account}>{saving === account ? "Đang lưu…" : "Lưu"}</button>
              </div>
            </article>
          );
        })}
      </div>
      {message ? <p className="upload-result" role={/^(Đã lưu|Đã chép|Tháng )/.test(message) ? "status" : "alert"}>{message}</p> : null}
    </section>
  );
}
