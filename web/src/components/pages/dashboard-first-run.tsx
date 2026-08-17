"use client";

import Link from "next/link";
import clsx from "clsx";
import type { CurrentUser } from "@/lib/api";
import { canWrite, isOwner } from "@/components/ui";
import styles from "./dashboard.module.css";

type FirstRunSetup = {
  hasAccounts: boolean;
  hasImports: boolean;
  hasTarget: boolean;
};

export function DashboardFirstRun({ user, setup, compact = false }: { user: CurrentUser; setup: FirstRunSetup; compact?: boolean }) {
  const owner = isOwner(user);
  const writer = canWrite(user);
  if (!setup.hasAccounts && !owner) {
    return <section className={styles.firstRun} aria-labelledby="first-run-title"><div className={styles.panelHeading}><div><p className={styles.sectionLabel}>Chưa có phạm vi dữ liệu</p><h2 id="first-run-title">Liên hệ chủ sở hữu để được cấp tài khoản</h2><p>{writer ? "Sau khi được cấp tài khoản, bạn có thể nhập tệp và đặt mục tiêu trong phạm vi được phép." : "Tài khoản của bạn đang ở chế độ chỉ xem và chưa được cấp phạm vi báo cáo."}</p></div></div><p className={styles.guidance}>Không có thao tác quản trị nào được mở cho vai trò hiện tại.</p></section>;
  }
  const steps = [
    { done: setup.hasAccounts, href: owner ? "/accounts" : null, title: "Tạo tài khoản TikTok", copy: setup.hasAccounts ? "Đã có phạm vi tài khoản để vận hành." : "Tạo phạm vi báo cáo cho từng tài khoản affiliate." },
    { done: setup.hasImports, href: writer && setup.hasAccounts ? "/imports" : null, title: "Nhập tệp Excel đầu tiên", copy: setup.hasImports ? "Đã có lịch sử nhập để dựng báo cáo." : "Chọn tài khoản và tệp TikTok cần nhập." },
    { done: setup.hasTarget, href: writer && setup.hasAccounts ? "/targets" : null, title: "Đặt mục tiêu tháng", copy: setup.hasTarget ? "Đã có mục tiêu cho tháng hiện tại." : "Mở trang Mục tiêu để hệ thống tính nhịp và dự báo." },
  ];
  const pending = steps.filter((step) => !step.done);
  if (compact && pending.length) {
    const next = pending[0];
    return (
      <section className={clsx(styles.firstRun, styles.firstRunCompact)} aria-labelledby="first-run-title">
        <span className={styles.stepIndex} aria-hidden="true">{steps.length - pending.length + 1}</span>
        <div>
          <strong id="first-run-title">{next.title}</strong>
          <p>{next.copy}</p>
        </div>
        {next.href ? <Link className={styles.link} href={next.href}>Mở ngay</Link> : <span className={styles.stepState}>Chưa khả dụng</span>}
      </section>
    );
  }
  return <section className={styles.firstRun} aria-labelledby="first-run-title"><div className={styles.panelHeading}><div><p className={styles.sectionLabel}>Khởi động có hướng dẫn</p><h2 id="first-run-title">Hoàn tất thiết lập vận hành</h2><p>Các bước được cập nhật tự động từ dữ liệu và quyền hiện tại.</p></div></div><ol className={styles.stepList}>{steps.map((step, index) => <li key={step.title} data-state={step.done ? "done" : step.href ? "current" : "blocked"}><span className={styles.stepIndex} aria-hidden="true">{step.done ? "✓" : index + 1}</span><div>{step.href ? <Link href={step.href}><strong>{step.title}</strong></Link> : <strong>{step.title}</strong>}<p>{step.copy}</p></div><span className={styles.stepState}>{step.done ? "Hoàn tất" : step.href ? "Cần làm" : "Chưa khả dụng"}</span></li>)}</ol></section>;
}
