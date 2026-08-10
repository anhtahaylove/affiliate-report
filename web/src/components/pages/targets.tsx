"use client";

import { useCallback, useEffect, useState } from "react";
import { CurrentUser, MonthlyKpiRow, TargetRow, loadMonthlyKpi, loadTargets, saveTarget } from "@/lib/api";
import { UrlFilters } from "@/components/filters";
import { canWrite } from "@/components/ui";
import { invalidateApiCache } from "@/lib/use-api";
import { accountLabel, achievementTone, errorMessage, formatMoney, percent } from "@/lib/format";

export function TargetsPage({ user, filters, accounts }: { user: CurrentUser; filters: UrlFilters; accounts: string[] }) {
  const [targets, setTargets] = useState<TargetRow[]>([]);
  const [kpi, setKpi] = useState<MonthlyKpiRow[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState("");
  const [message, setMessage] = useState("");
  const scopedAccounts = filters.accounts.length ? accounts.filter((account) => filters.accounts.includes(account)) : accounts;
  const allowedAccounts = user.role === "owner" ? ["ALL", ...scopedAccounts] : scopedAccounts;
  const refresh = useCallback(async () => {
    const [targetData, monthly] = await Promise.all([
      loadTargets(filters.month),
      loadMonthlyKpi({ month: filters.month, accounts: filters.accounts, start: filters.start, end: filters.end }),
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
    if (!/^\d+$/.test(draft)) return setMessage("KPI/ngày phải là số nguyên không âm.");
    setSaving(account);
    try {
      await saveTarget(account, filters.month, Number(draft));
      invalidateApiCache();
      setMessage(`Đã lưu KPI/ngày cho ${account}.`);
      await refresh();
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể lưu mục tiêu."));
    } finally {
      setSaving("");
    }
  }
  const targetMap = new Map(targets.map((target) => [target.account, target]));
  const kpiMap = new Map(kpi.map((row) => [row.account, row]));
  return <section className="section panel wide"><div className="section-heading"><div><p className="section-label">KPI mỗi ngày</p><h2>Mục tiêu tháng {filters.month}</h2></div>{!canWrite(user) ? <span className="read-only">Chỉ xem</span> : null}</div><div className="target-list">{allowedAccounts.map((account) => { const achievement = kpiMap.get(account)?.target_achievement; return <div className="target-row" key={account}><div><strong>{accountLabel(account)}</strong><span>Hoa hồng {formatMoney(kpiMap.get(account)?.actual_commission)} · KPI/ngày {formatMoney(targetMap.get(account)?.daily_target_commission)} · đã đạt <span className="tone-text" data-tone={achievementTone(achievement)}>{percent(achievement)}</span></span></div><input type="number" min="0" step="1" value={drafts[account] ?? ""} onChange={(event) => setDrafts((current) => ({ ...current, [account]: event.target.value }))} disabled={!canWrite(user) || saving === account} aria-label={`KPI ngày ${accountLabel(account)}`} /><button type="button" onClick={() => void save(account)} disabled={!canWrite(user) || saving === account}>{saving === account ? "Đang lưu…" : "Lưu"}</button></div>; })}</div>{message ? <p className="upload-result" role="status">{message}</p> : null}</section>;
}
