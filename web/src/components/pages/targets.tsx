"use client";

import { useCallback, useEffect, useState } from "react";
import { CalendarClock, Copy, Save, Target } from "lucide-react";
import { CurrentUser, MonthlyKpiRow, TargetRow, copyPreviousTargets, loadMonthlyKpi, loadTargets, saveTarget } from "@/lib/api";
import { UrlFilters } from "@/components/filters";
import { canWrite } from "@/components/ui";
import { invalidateApiCache } from "@/lib/use-api";
import { achievementTone, errorMessage, formatMoney, integer, percent } from "@/lib/format";
import { AccountIdentity } from "@/components/account-identity";
import type { AccountDirectory } from "@/lib/account-directory";
import styles from "./targets.module.css";

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
  const [focusedAccount, setFocusedAccount] = useState("");
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
  const mobileAccount = allowedAccounts.includes(focusedAccount) ? focusedAccount : allowedAccounts[0] ?? "";
  return (
    <section className={`${styles.page} targets-workflow-page`}>
      <div className={styles.heading}>
        <div>
          <p className="section-label">Mục tiêu hoa hồng mỗi ngày (KPI)</p>
          <h2>Lập mục tiêu tháng {monthLabel(filters.month)}</h2>
          <p className="subtle">Tiến độ tính trên phạm vi đang lọc: {filters.start.split("-").reverse().join("/")} – {filters.end.split("-").reverse().join("/")}.</p>
        </div>
        {canWrite(user) ? <button className={styles.copyButton} type="button" onClick={() => void copyPrevious()} disabled={copying}><Copy size={16} aria-hidden="true" /> {copying ? "Đang chép…" : `Chép KPI từ ${monthLabel(previousMonth)}`}</button> : <span className={styles.readOnly}>Chỉ xem</span>}
      </div>

      <div className={styles.context}>
        <CalendarClock size={18} aria-hidden="true" />
        <div><strong>Sao chép an toàn</strong><span>Chỉ tạo KPI còn thiếu từ tháng {monthLabel(previousMonth)}; KPI đã nhập cho tháng này luôn được giữ nguyên.</span></div>
      </div>

      <div className={styles.mobileAccountPicker} role="group" aria-label="Chọn tài khoản để chỉnh mục tiêu">
        {allowedAccounts.map((account) => <button key={account} type="button" aria-pressed={mobileAccount === account} onClick={() => setFocusedAccount(account)}>{directory.label(account)}</button>)}
      </div>

      <div className={styles.planner} role="table" aria-label={`Mục tiêu tháng ${monthLabel(filters.month)}`}>
        <div className={styles.plannerHeader} role="row">
          <span role="columnheader">Tài khoản</span>
          <span role="columnheader">Hoa hồng thực tế</span>
          <span role="columnheader">KPI/ngày</span>
          <span role="columnheader">KPI tháng</span>
          <span role="columnheader">Tiến độ</span>
          <span role="columnheader">Điều chỉnh</span>
        </div>
        {allowedAccounts.map((account) => {
          const target = targetMap.get(account);
          const row = kpiMap.get(account);
          const achievement = row?.target_achievement;
          const draft = drafts[account] ?? "";
          return (
            <article className={`${styles.plannerRow} target-card`} key={account} role="row" data-mobile-active={mobileAccount === account}>
              <div className={styles.accountCell} role="cell">
                <div className={styles.accountIdentity}>
                  <span className={styles.targetIcon}><Target size={16} aria-hidden="true" /></span>
                  <div>
                   <AccountIdentity directory={directory} code={account} />
                    <span>{account === "ALL" ? "Mục tiêu tổng độc lập" : "Mục tiêu riêng theo tài khoản"}</span>
                  </div>
                </div>
              </div>
              <div className={styles.metricCell} role="cell"><span>Hoa hồng thực tế</span><strong>{formatMoney(row?.actual_commission)}</strong></div>
              <div className={styles.metricCell} role="cell"><span>KPI/ngày hiện tại</span><strong>{formatMoney(target?.daily_target_commission)}</strong></div>
              <div className={styles.metricCell} role="cell"><span>KPI tháng</span><strong>{formatMoney(row?.monthly_target)}</strong></div>
              <div className={styles.progressCell} role="cell">
                <div><span>Tiến độ</span><strong className="tone-text" data-tone={achievementTone(achievement)}>{percent(achievement)}</strong></div>
                <progress max={1} value={Math.min(1, Math.max(0, achievement ?? 0))} aria-label={`Tiến độ mục tiêu ${directory.get(account).accessibleName}`} />
                <span className="tone-text" data-tone={row?.gap == null ? undefined : row.gap < 0 ? "critical" : "good"}>{row?.gap == null ? "Chưa có KPI" : row.gap < 0 ? `Còn thiếu ${formatMoney(Math.abs(row.gap))}` : `Vượt ${formatMoney(row.gap)}`}</span>
              </div>
              <div className={styles.editCell} role="cell">
                <div className={`${styles.targetField} field`}>
                  <label htmlFor={`target-${account}`}>KPI/ngày mới</label>
                  <input id={`target-${account}`} type="number" min="0" step="1" value={draft} onChange={(event) => setDrafts((current) => ({ ...current, [account]: event.target.value }))} disabled={!canWrite(user) || saving === account} aria-label={`KPI ngày ${directory.get(account).accessibleName}`} />
                </div>
                <button type="button" onClick={() => void save(account)} disabled={!canWrite(user) || saving === account}><Save size={15} aria-hidden="true" /> {saving === account ? "Đang lưu…" : "Lưu"}</button>
              </div>
            </article>
          );
        })}
      </div>
      {message ? <p className={`${styles.message} upload-result`} role={/^(Đã lưu|Đã chép|Tháng )/.test(message) ? "status" : "alert"}>{message}</p> : null}
    </section>
  );
}
