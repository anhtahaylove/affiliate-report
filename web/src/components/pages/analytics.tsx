"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import clsx from "clsx";
import { useEffect, useState, type ReactNode } from "react";
import { Tabs } from "radix-ui";
import { AnalyticsBreakdownRow, AnalyticsDimensionRow, AnalyticsResponse, loadAnalytics } from "@/lib/api";
import { UrlFilters } from "@/components/filters";
import { Notice, Skeleton, StateCard, StatusBadge } from "@/components/ui";
import { useApi } from "@/lib/use-api";
import { qualityIssueCount, qualityIssues, rejectedAllTime } from "@/lib/data-quality";
import { agingBucketLabel, formatDateTime, formatMoney, integer, percent, statusLabel } from "@/lib/format";
import { AccountIdentity } from "@/components/account-identity";
import type { AccountDirectory } from "@/lib/account-directory";
import styles from "./analytics.module.css";

const CommissionTrendChart = dynamic(
  () => import("@/components/commerce-intelligence-charts").then((module) => module.CommissionTrendChart),
  { ssr: false, loading: () => <div className={styles.chartLoading} role="status" aria-label="Đang dựng biểu đồ" /> },
);
const AccountContributionChart = dynamic(
  () => import("@/components/commerce-intelligence-charts").then((module) => module.AccountContributionChart),
  { ssr: false, loading: () => <div className={styles.chartLoading} role="status" aria-label="Đang dựng biểu đồ" /> },
);
const StatusMixChart = dynamic(
  () => import("@/components/commerce-intelligence-charts").then((module) => module.StatusMixChart),
  { ssr: false, loading: () => <div className={styles.chartLoading} role="status" aria-label="Đang dựng biểu đồ" /> },
);

export function AnalyticsPage({ filters, directory }: { filters: UrlFilters; directory: AccountDirectory }) {
  const compact = useCompactAnalytics();
  const { data, error, loading } = useApi<AnalyticsResponse>(
    `analytics-v2:${JSON.stringify([filters.accounts, filters.statuses, filters.start, filters.end])}`,
    () => loadAnalytics({ accounts: filters.accounts, statuses: filters.statuses, start: filters.start, end: filters.end }),
    "Không thể tải dữ liệu phân tích.",
  );
  if (error) return <Notice text={error} />;
  if (loading) return <Skeleton rows={4} tall label="Đang tải Phân tích" />;
  if (!data) return <StateCard text="Chưa có dữ liệu phân tích." />;

  const previous = data.previous_period?.summary;
  const commissionDelta = previous ? data.summary.actual_commission - previous.actual_commission : null;
  const soVanDe = qualityIssueCount(data.data_quality);

  return (
    <div className={styles.page}>
      <section className={styles.summary} aria-labelledby="analytics-summary-title">
        <div className={styles.summaryHeading}>
          <div>
            <p className={styles.sectionLabel}>Tóm tắt phân tích</p>
            <h2 id="analytics-summary-title">Kết quả và độ tin cậy</h2>
          </div>
          <span className={styles.freshness}>
            <span className={styles.freshnessDot} aria-hidden="true" />
            <span>Dữ liệu cập nhật</span>
            <strong>{formatDateTime(data.data_quality.latest_import_at)}</strong>
          </span>
        </div>
        <div className={styles.metricRail}>
          <InsightMetric primary signal label="Hoa hồng thực tế" value={formatMoney(data.summary.actual_commission)} note={commissionDelta == null ? "Chưa có kỳ so sánh" : `${commissionDelta >= 0 ? "+" : "−"}${formatMoney(Math.abs(commissionDelta))} so kỳ trước`} tone={commissionDelta != null && commissionDelta < 0 ? "danger" : "success"} />
          <InsightMetric signal label="Tỷ lệ hoa hồng" value={percent(data.summary.effective_commission_rate)} note={`${integer.format(data.summary.orders)} đơn trong phạm vi`} />
          <InsightMetric signal label="Đã nhận cuối cùng" value={formatMoney(data.summary.final_received)} note={`Chênh ${formatMoney(data.summary.final_received_variance)}`} />
          <InsightMetric signal label="Chất lượng dữ liệu" value={soVanDe ? `${integer.format(soVanDe)} vấn đề` : "Sạch"} note={soVanDe ? "Có dòng cần kiểm tra" : "Không có ngoại lệ trong phạm vi"} tone={soVanDe ? "warning" : "success"} />
        </div>
      </section>

      <Tabs.Root className={styles.tabs} defaultValue="finance">
        <Tabs.List className={styles.tabList} aria-label="Nhóm phân tích">
          <Tabs.Trigger value="finance">Tài chính</Tabs.Trigger>
          <Tabs.Trigger value="accounts">Tài khoản</Tabs.Trigger>
          <Tabs.Trigger value="commerce">Sản phẩm & nội dung</Tabs.Trigger>
          <Tabs.Trigger value="settlement">Đối soát</Tabs.Trigger>
          <Tabs.Trigger value="quality">Chất lượng dữ liệu</Tabs.Trigger>
        </Tabs.List>

        <Tabs.Content value="finance" className={styles.tabPanel}>
          <section className={styles.surface}>
            <div className={styles.panelHeading}><div><p className={styles.sectionLabel}>Đà tài chính</p><h2>Hoa hồng và dòng tiền theo thời gian</h2></div><span className={styles.cadence}>{data.filters.group_by === "day" ? "Theo ngày" : data.filters.group_by === "week" ? "Theo tuần" : "Theo tháng"}</span></div>
            <p className={styles.interpretation}>{trendInterpretation(data.trend)}</p>
            <ChartEvidence compact={compact} summary="Mở biểu đồ và bảng dữ liệu theo thời gian">
              <div className={styles.legend} aria-label="Chú giải biểu đồ">
                <span data-series="commission">Hoa hồng thực tế</span>
                <span data-series="received">Tiền đã nhận</span>
              </div>
              {data.trend.length ? <CommissionTrendChart rows={data.trend} /> : <p className={styles.empty}>Chưa có dữ liệu xu hướng.</p>}
              <ChartDataTable rows={data.trend} />
            </ChartEvidence>
          </section>
          <div className={styles.split}>
            <section className={styles.surface}>
              <div className={styles.panelHeading}><div><p className={styles.sectionLabel}>Phễu đơn hàng</p><h2>Quy mô theo trạng thái</h2></div></div>
              <p className={styles.interpretation}>{breakdownInterpretation(data.status_breakdown, "status", directory)}</p>
              <ChartEvidence compact={compact} summary="Mở biểu đồ quy mô theo trạng thái">
                {data.status_breakdown.length ? <StatusMixChart rows={data.status_breakdown} /> : <p className={styles.empty}>Chưa có dữ liệu trạng thái.</p>}
              </ChartEvidence>
            </section>
            <BreakdownList rows={data.status_breakdown} mode="status" />
          </div>
        </Tabs.Content>

        <Tabs.Content value="accounts" className={styles.tabPanel}>
          <div className={styles.split}>
            <section className={styles.surface}>
              <div className={styles.panelHeading}><div><p className={styles.sectionLabel}>Đóng góp</p><h2>Tài khoản tạo ra hoa hồng</h2></div><Link className={styles.link} href="/accounts">Quản lý tài khoản</Link></div>
              <p className={styles.interpretation}>{breakdownInterpretation(data.account_breakdown, "account", directory)}</p>
              <ChartEvidence compact={compact} summary="Mở biểu đồ đóng góp theo tài khoản">
                {data.account_breakdown.length ? <AccountContributionChart rows={data.account_breakdown} directory={directory} /> : <p className={styles.empty}>Chưa có dữ liệu tài khoản.</p>}
              </ChartEvidence>
            </section>
            <BreakdownList rows={data.account_breakdown} mode="account" directory={directory} />
          </div>
          <BreakdownTable rows={data.account_breakdown} mode="account" directory={directory} />
        </Tabs.Content>

        <Tabs.Content value="commerce" className={styles.tabPanel}>
          <DimensionLeaderboard title="Sản phẩm dẫn đầu" eyebrow="Hiệu suất sản phẩm" rows={data.products} total={data.summary.actual_commission} />
          <DimensionLeaderboard title="Cửa hàng tạo doanh thu" eyebrow="Đóng góp cửa hàng" rows={data.shops} total={data.summary.actual_commission} />
          {/* Nội dung nhận diện bằng ID 19 chữ số, không có tên. Chữ đều giúp đọc và đối chiếu
              được; title cho phép xem đủ khi ô bị cắt; labelPrefix + footnote nói rõ đó là MÃ,
              không phải chọn nhầm hiển thị lỗi, và chỉ người dùng tra được ở đâu. */}
          <DimensionLeaderboard
            title="Nội dung chuyển đổi"
            eyebrow="Hiệu suất nội dung"
            rows={data.content}
            total={data.summary.actual_commission}
            mono
            labelPrefix="Mã nội dung: "
            footnote="TikTok chưa cung cấp tên nội dung, chỉ có mã — bạn có thể tra mã này trong Trung tâm nhà bán TikTok để biết đó là video nào."
          />
        </Tabs.Content>

        <Tabs.Content value="settlement" className={styles.tabPanel}>
          <SettlementStudio data={data} />
        </Tabs.Content>

        <Tabs.Content value="quality" className={styles.tabPanel}>
          <QualityStudio data={data} />
        </Tabs.Content>
      </Tabs.Root>
    </div>
  );
}

function InsightMetric({ label, value, note, tone = "neutral", primary = false, signal = false }: { label: string; value: string; note: string; tone?: "neutral" | "success" | "warning" | "danger"; primary?: boolean; signal?: boolean }) {
  return <article className={styles.metric} data-tone={tone} data-primary={primary ? "true" : undefined}><span>{label}</span><strong>{value}</strong><small>{signal ? <span className={styles.metricSignal} aria-hidden="true" /> : null}{note}</small></article>;
}

function BreakdownList({ rows, mode, directory }: { rows: AnalyticsBreakdownRow[]; mode: "status" | "account"; directory?: AccountDirectory }) {
  return (
    <section className={styles.surface}>
      <div className={styles.panelHeading}><div><p className={styles.sectionLabel}>Phân bổ</p><h2>{mode === "status" ? "Tín hiệu cần chú ý" : "Tỷ trọng tài khoản"}</h2></div></div>
      <ol className={styles.rankList}>
        {rows.slice(0, 6).map((row, index) => {
          const label = mode === "status" ? statusLabel(row.status) : directory?.label(row.account) ?? row.account ?? "Chưa xác định";
          const share = row.commission_share ?? 0;
          const sharePercent = Math.max(0, Math.min(share * 100, 100));
          return <li key={`${mode}-${label}`}><span className={styles.rankIndex}>{String(index + 1).padStart(2, "0")}</span><div><strong>{label}</strong><small>{integer.format(row.orders)} đơn · {formatMoney(mode === "status" ? row.initial_commission : row.actual_commission)}</small><div className={styles.shareTrack} role="progressbar" aria-label={`${label}: tỷ trọng hoa hồng`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Number(sharePercent.toFixed(1))}><span style={{ width: `${sharePercent}%` }} /></div></div><b>{percent(share)}</b></li>;
        })}
      </ol>
    </section>
  );
}

function BreakdownTable({ rows, mode, directory }: { rows: AnalyticsBreakdownRow[]; mode: "status" | "account"; directory?: AccountDirectory }) {
  return <section className={clsx(styles.surface, styles.desktopOnly)}><div className={styles.panelHeading}><div><p className={styles.sectionLabel}>Chi tiết</p><h2>Bảng đóng góp</h2></div></div><div className={styles.tableWrap} role="region" aria-label="Bảng đóng góp theo tài khoản" tabIndex={0}><table><caption className="sr-only">Đóng góp theo {mode === "status" ? "trạng thái" : "tài khoản"}</caption><thead><tr><th>{mode === "status" ? "Trạng thái" : "Tài khoản"}</th><th>Đơn</th><th>GMV thực tế</th><th>Hoa hồng</th><th>Tỷ trọng</th></tr></thead><tbody>{rows.map((row) => <tr key={row[mode === "status" ? "status" : "account"] ?? "unknown"}><td>{mode === "status" ? <StatusBadge status={row.status} /> : directory ? <AccountIdentity directory={directory} code={row.account} /> : row.account}</td><td>{integer.format(row.orders)}</td><td>{formatMoney(row.actual_gmv)}</td><td>{formatMoney(row.actual_commission)}</td><td>{percent(row.commission_share)}</td></tr>)}</tbody></table></div></section>;
}

function DimensionLeaderboard({ title, eyebrow, rows, total, mono = false, labelPrefix, footnote }: { title: string; eyebrow: string; rows: AnalyticsDimensionRow[]; total: number; mono?: boolean; labelPrefix?: string; footnote?: string }) {
  // Đo trên dữ liệu thật: 3 dòng đầu chiếm 56% hoa hồng ở cả sản phẩm lẫn cửa hàng. Mức tập
  // trung đó mới là điều cần thấy, chứ không phải một danh sách phẳng — nên mỗi dòng hiện
  // phần trăm đóng góp, và phần đầu bảng nói thẳng nhóm dẫn đầu chiếm bao nhiêu.
  const dan_dau = rows.slice(0, 3).reduce((con, row) => con + row.actual_commission, 0);
  const ty_trong = (giatri: number) => (total > 0 ? giatri / total : 0);
  const label = (value: string) => (labelPrefix ? `${labelPrefix}${value}` : value);
  return (
    <section className={styles.surface}>
      <div className={styles.panelHeading}><div><p className={styles.sectionLabel}>{eyebrow}</p><h2>{title}</h2></div><span>Top {rows.length}</span></div>
      {rows.length ? <>
        {total > 0 ? <p className={styles.dimensionConcentration}>3 dòng đầu chiếm <strong>{percent(ty_trong(dan_dau))}</strong> hoa hồng trong phạm vi</p> : null}
        <ol className={styles.dimensionRanks}>{rows.slice(0, 5).map((row, index) => <li key={row.id}><span className={styles.rankIndex}>{String(index + 1).padStart(2, "0")}</span><div><strong className={styles.dimensionLabel} data-mono={mono ? "true" : undefined} title={row.label}>{label(row.label)}</strong><small>{integer.format(row.orders)} đơn · {integer.format(row.units_sold)} sản phẩm</small></div><div><b>{formatMoney(row.actual_commission)}</b><small>{percent(ty_trong(row.actual_commission))} · Huỷ {percent(row.cancellation_rate)}</small></div></li>)}</ol>
        <div className={clsx(styles.tableWrap, styles.desktopOnly)} role="region" aria-label={`Bảng ${title.toLowerCase()}`} tabIndex={0}><table><caption className="sr-only">{title}</caption><thead><tr><th>Tên</th><th>Đơn</th><th>SL</th><th>SL hoàn</th><th>GMV</th><th>Hoa hồng</th><th>Tỷ lệ huỷ</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td className={styles.dimensionCell} data-mono={mono ? "true" : undefined} title={row.label}>{label(row.label)}</td><td>{integer.format(row.orders)}</td><td>{integer.format(row.units_sold)}</td><td>{integer.format(row.units_refunded)}</td><td>{formatMoney(row.actual_gmv)}</td><td>{formatMoney(row.actual_commission)}</td><td>{percent(row.cancellation_rate)}</td></tr>)}</tbody></table></div>
        {footnote ? <p className={styles.footnote}>{footnote}</p> : null}
      </> : <p className={styles.empty}>Chưa có dữ liệu trong phạm vi này.</p>}
    </section>
  );
}

function SettlementStudio({ data }: { data: AnalyticsResponse }) {
  return (
    <div className={styles.settlementStudio}>
      <section className={clsx(styles.surface, styles.settlementHero)}>
        <div><p className={styles.sectionLabel}>Dòng tiền nhận về</p><h2>{formatMoney(data.summary.final_received)}</h2><p>Tiền đã nhận cuối cùng trong phạm vi đang xem.</p></div>
        <div className={styles.settlementMetrics}><InsightMetric label="Đã quyết toán" value={integer.format(data.settlement.settled_lines)} note={`Thường mất ${data.settlement.median_lag_days ?? "—"} ngày`} /><InsightMetric label="Đang chờ" value={integer.format(data.settlement.pending_lines)} note="Xem chi tiết bên dưới" tone={data.settlement.pending_lines ? "warning" : "success"} /><InsightMetric label="Chênh tiền về" value={formatMoney(data.summary.final_received_variance)} note="So với hoa hồng thực tế" tone={data.summary.final_received_variance < 0 ? "danger" : "neutral"} /></div>
      </section>
      <section className={styles.surface}><div className={styles.panelHeading}><div><p className={styles.sectionLabel}>Tuổi khoản chờ</p><h2>Khoản chưa quyết toán theo thời gian</h2></div></div>{data.settlement.pending_aging.length ? <div className={styles.agingGrid}>{data.settlement.pending_aging.map((row) => <article key={row.bucket}><span>{agingBucketLabel(row.bucket)}</span><strong>{integer.format(row.count)}</strong><small>dòng đang chờ</small></article>)}</div> : <p className={styles.empty}>Không có khoản đang chờ trong phạm vi này.</p>}</section>
    </div>
  );
}

function QualityStudio({ data }: { data: AnalyticsResponse }) {
  const quality = data.data_quality;
  // Cùng danh sách với con số ở đầu trang, nên hai chỗ không thể lệch nhau.
  const issues = qualityIssues(quality);
  return (
    <div className={styles.qualityStudio}>
      <section className={clsx(styles.surface, styles.qualitySummary)}><div className={styles.panelHeading}><div><p className={styles.sectionLabel}>Dòng dữ liệu</p><h2>Lịch sử xử lý dữ liệu</h2></div><span>Cập nhật {formatDateTime(quality.latest_import_at)}</span></div><div className={styles.qualityFlow}><InsightMetric label="Lượt nhập" value={integer.format(quality.import_batches)} note="mỗi lần nhập tệp tính 1 lượt" /><InsightMetric label="Dòng mới" value={integer.format(quality.import_inserted)} note="được thêm vào lịch sử" tone="success" /><InsightMetric label="Đã cập nhật" value={integer.format(quality.import_updated)} note="đơn đã có, cập nhật thông tin mới" /><InsightMetric label="Không thay đổi" value={integer.format(quality.import_unchanged)} note="trùng lần nhập trước, đã tự bỏ qua" /></div></section>
      <section className={styles.surface}><div className={styles.panelHeading}><div><p className={styles.sectionLabel}>Ngoại lệ dữ liệu</p><h2>Vấn đề cần làm sạch</h2></div><Link className={styles.link} href="/imports">Mở lịch sử import</Link></div><div className={styles.exceptionList}>{issues.map(({ label, value, help }) => <article data-tone={value ? "warning" : "success"} key={label}><div><strong>{label}</strong><p>{help}</p></div><span>{integer.format(value)}</span></article>)}</div>
        {/* Cố ý nằm NGOÀI danh sách vấn đề: TikTok để trống ngày quyết toán cho mọi đơn chưa
            được trả tiền, nên đây là tình trạng bình thường chứ không phải dữ liệu bẩn. */}
        <p className={styles.qualityNote}>Ngoài ra có <strong>{integer.format(quality.missing_settlement_date_rows)}</strong> dòng chưa có ngày quyết toán — đơn đang chờ TikTok trả tiền, không phải lỗi dữ liệu.</p>
        <p className={styles.qualityNote}><strong>{integer.format(rejectedAllTime(quality))}</strong> dòng bị từ chối khi nhập, tính từ trước tới nay. Không xếp được vào phạm vi ngày nào vì chúng chưa bao giờ đọc được. <Link className={styles.link} href="/imports">Xem lịch sử nhập</Link></p>
      </section>
    </div>
  );
}

function ChartDataTable({ rows }: { rows: AnalyticsResponse["trend"] }) {
  return <details className={styles.dataDisclosure}><summary>Xem bảng dữ liệu biểu đồ</summary><div className={styles.tableWrap} role="region" aria-label="Bảng dữ liệu xu hướng" tabIndex={0}><table><caption className="sr-only">Dữ liệu hoa hồng và tiền đã nhận theo kỳ</caption><thead><tr><th>Kỳ</th><th>Đơn</th><th>GMV thực tế</th><th>Hoa hồng</th><th>Đã nhận</th></tr></thead><tbody>{rows.map((row) => <tr key={row.period}><td>{row.period}</td><td>{integer.format(row.orders)}</td><td>{formatMoney(row.actual_gmv)}</td><td>{formatMoney(row.actual_commission)}</td><td>{formatMoney(row.final_received)}</td></tr>)}</tbody></table></div></details>;
}

function ChartEvidence({ children, compact, summary }: { children: ReactNode; compact: boolean; summary: string }) {
  const [expanded, setExpanded] = useState(false);
  if (!compact) return <div className={styles.chartBody}>{children}</div>;
  return (
    <details className={styles.chartDisclosure} onToggle={(event) => setExpanded(event.currentTarget.open)}>
      <summary>{summary}</summary>
      {expanded ? <div className={styles.chartBody}>{children}</div> : null}
    </details>
  );
}

function useCompactAnalytics() {
  const [compact, setCompact] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 760px)").matches,
  );

  useEffect(() => {
    const query = window.matchMedia("(max-width: 760px)");
    const sync = () => setCompact(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  return compact;
}

function trendInterpretation(rows: AnalyticsResponse["trend"]) {
  if (!rows.length) return "Chưa có mốc thời gian đủ để đọc xu hướng trong phạm vi này.";
  const latest = rows[rows.length - 1];
  const previous = rows.at(-2);
  if (!previous) return `Kỳ ${latest.period} ghi nhận ${formatMoney(latest.actual_commission)} hoa hồng thực tế.`;
  const delta = latest.actual_commission - previous.actual_commission;
  if (delta === 0) return `Kỳ ${latest.period} giữ nguyên hoa hồng so với mốc liền trước, ở mức ${formatMoney(latest.actual_commission)}.`;
  return `Kỳ ${latest.period} ${delta > 0 ? "tăng" : "giảm"} ${formatMoney(Math.abs(delta))} hoa hồng so với mốc liền trước.`;
}

function breakdownInterpretation(rows: AnalyticsBreakdownRow[], mode: "status" | "account", directory: AccountDirectory) {
  const leading = rows[0];
  if (!leading) return mode === "status" ? "Chưa có trạng thái đơn hàng để phân tích." : "Chưa có tài khoản phát sinh dữ liệu trong phạm vi này.";
  const label = mode === "status" ? statusLabel(leading.status) : directory.label(leading.account);
  return mode === "status"
    ? `${label} đang có quy mô lớn nhất với ${integer.format(leading.orders)} đơn và ${formatMoney(leading.gross_gmv)} GMV.`
    : `${label} đang đóng góp nhiều nhất: ${percent(leading.commission_share)} hoa hồng trong phạm vi.`;
}
