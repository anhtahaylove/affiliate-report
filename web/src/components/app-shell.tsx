"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { apiUrl, CurrentUser, exitApplication, logout } from "@/lib/api";
import { ConfirmDialog } from "@/components/ui";
import { ThemeToggle } from "@/components/theme-toggle";
import { roleLabel } from "@/lib/format";

type NavItem = { href: string; label: string; roles?: Array<CurrentUser["role"]> };

const navItems: NavItem[] = [
  { href: "/", label: "Tổng quan" },
  { href: "/analytics", label: "Phân tích" },
  { href: "/orders", label: "Đơn hàng" },
  { href: "/imports", label: "Nhập dữ liệu", roles: ["operator", "owner"] },
  { href: "/targets", label: "Mục tiêu" },
  { href: "/accounts", label: "Tài khoản", roles: ["owner"] },
  { href: "/settings/data", label: "Cài đặt", roles: ["owner"] },
];

export function AppShell({ user, apiError, children }: { user: CurrentUser; apiError?: string; children: ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [exiting, setExiting] = useState(false);
  const [exitError, setExitError] = useState("");
  const [askExit, setAskExit] = useState(false);
  const apiBaseLabel = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "Nội bộ ứng dụng";
  const visibleItems = navItems.filter((item) => !item.roles || item.roles.includes(user.role));

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  async function handleLogout() {
    try {
      await logout();
    } finally {
      window.location.href = `${apiUrl()}/auth/login`;
    }
  }

  async function handleExit() {
    if (!user.desktop_control_token) return;
    setAskExit(false);
    setExiting(true);
    setExitError("");
    try {
      await exitApplication(user.desktop_control_token);
    } catch (reason) {
      setExiting(false);
      setExitError(reason instanceof Error ? reason.message : "Không thể thoát ứng dụng.");
    }
  }

  return (
    <main className={`cockpit-shell${open ? " nav-open" : ""}`}>
      <aside id="mobile-navigation" className="sidebar" aria-label="Điều hướng chính">
        <div className="sidebar-brand">
          <Image className="brand-mark" src="/icon-192.png" alt="" width={42} height={42} priority />
          <div>
            <strong>TikTok Affiliate</strong>
            <span>Trung tâm vận hành</span>
          </div>
        </div>
        <nav>
          {visibleItems.map((item) => {
            const active = item.href === "/settings/data" ? pathname.startsWith("/settings") : pathname === item.href;
            return (
              <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined} onClick={() => setOpen(false)}>
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className={`health-card${apiError ? " offline" : ""}`}>
          <span>{apiError ? "API gặp lỗi" : "API hoạt động"}</span>
          <small>{apiBaseLabel}</small>
        </div>
      </aside>
      <button className="sidebar-backdrop" type="button" aria-label="Đóng menu điều hướng" onClick={() => setOpen(false)} />

      <section className="cockpit-main">
        <header className="cockpit-header">
          <button className="drawer-button" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-controls="mobile-navigation" aria-label={open ? "Đóng menu điều hướng" : "Mở menu điều hướng"}>
            {open ? "Đóng menu" : "Menu"}
          </button>
          <div className="user-menu" role="group" aria-label="Tài khoản hiện tại">
            <ThemeToggle />
            <span className="user-email" title={user.email}>{user.email}</span>
            <strong>{roleLabel(user.role)}</strong>
            <button type="button" onClick={handleLogout}>Đăng xuất</button>
            {user.desktop_app && user.desktop_control_token ? <button className="exit-button" type="button" onClick={() => setAskExit(true)} disabled={exiting}>{exiting ? "Đang thoát…" : "Thoát ứng dụng"}</button> : null}
            {exitError ? <span className="exit-error" role="alert">{exitError}</span> : null}
          </div>
        </header>
        {children}
      </section>
      <ConfirmDialog
        open={askExit}
        title="Thoát hoàn toàn TikTok Affiliate Report?"
        confirmLabel="Thoát ứng dụng"
        busy={exiting}
        onCancel={() => setAskExit(false)}
        onConfirm={() => void handleExit()}
      >
        <p>Backend sẽ dừng hẳn. Bạn có thể mở lại từ Desktop hoặc Start Menu bất cứ lúc nào.</p>
      </ConfirmDialog>
    </main>
  );
}

export function AuthCard({ message }: { message: string }) {
  return (
    <main className="auth-shell">
      <section className="auth-card panel">
        <div className="brand-badge">AFF</div>
        <h1>TikTok Affiliate Report</h1>
        <p>Vui lòng đăng nhập để mở trung tâm báo cáo vận hành.</p>
        <a className="button-link" href={`${apiUrl()}/auth/login`}>Đăng nhập</a>
        <p className="hint">{message}</p>
      </section>
    </main>
  );
}
