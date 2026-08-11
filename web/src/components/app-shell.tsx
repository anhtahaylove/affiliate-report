"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { apiUrl, CurrentUser, exitApplication, logout } from "@/lib/api";
import { ConfirmDialog } from "@/components/ui";
import { ThemeToggle } from "@/components/theme-toggle";
import { roleLabel } from "@/lib/format";

type NavItem = { href: string; label: string; desc: string; icon: string; roles?: Array<CurrentUser["role"]> };

// Đường dẫn SVG 24x24, vẽ tay thay vì kéo cả một thư viện icon vào chỉ để có bảy hình.
// Gom nhóm vì bảy mục phẳng bắt phải đọc hết cả danh sách mới biết mục nào làm gì; dòng mô tả
// tách "Mục tiêu" khỏi "Tài khoản" mà không cần bấm thử.
const navGroups: Array<{ title: string; items: NavItem[] }> = [
  {
    title: "Báo cáo",
    items: [
      { href: "/", label: "Tổng quan", desc: "Hoa hồng và tiến độ mục tiêu", icon: "M3 13h6v8H3zM10 3h6v18h-6zM17 9h4v12h-4z" },
      { href: "/analytics", label: "Phân tích", desc: "Xu hướng, sản phẩm, quyết toán", icon: "M3 18l6-6 4 4 8-8M15 8h6v6" },
      { href: "/orders", label: "Đơn hàng", desc: "Tra cứu và xuất Excel", icon: "M4 6h16M4 12h16M4 18h10" },
    ],
  },
  {
    title: "Dữ liệu",
    items: [
      { href: "/imports", label: "Nhập dữ liệu", desc: "Tải file TikTok .xlsx", icon: "M12 3v12M7 10l5 5 5-5M4 20h16", roles: ["operator", "owner"] },
      { href: "/targets", label: "Mục tiêu", desc: "KPI mỗi ngày theo tháng", icon: "M12 3a9 9 0 100 18 9 9 0 000-18zM12 8a4 4 0 100 8 4 4 0 000-8z" },
      { href: "/accounts", label: "Tài khoản", desc: "Thêm, sửa, lưu trữ tài khoản", icon: "M12 12a4 4 0 100-8 4 4 0 000 8zM4 20a8 8 0 0116 0", roles: ["owner"] },
    ],
  },
  {
    title: "Hệ thống",
    items: [
      { href: "/settings/data", label: "Cài đặt", desc: "Sao lưu, cập nhật, người dùng", icon: "M12 15a3 3 0 100-6 3 3 0 000 6zM4 12h2m12 0h2M12 4v2m0 12v2M6.3 6.3l1.4 1.4m8.6 8.6l1.4 1.4m0-11.4l-1.4 1.4M7.7 16.3l-1.4 1.4", roles: ["owner"] },
    ],
  },
];

function NavIcon({ path }: { path: string }) {
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={path} />
    </svg>
  );
}

export function AppShell({ user, apiError, appVersion, heading, children }: { user: CurrentUser; apiError?: string; appVersion?: string; heading?: ReactNode; children: ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [exiting, setExiting] = useState(false);
  const [exitError, setExitError] = useState("");
  const [askExit, setAskExit] = useState(false);
  const apiBaseLabel = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "Nội bộ ứng dụng";

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
          <Image className="brand-mark" src="/icon-192.png" alt="" width={38} height={38} priority />
          <div>
            <strong>TikTok Affiliate</strong>
            <span>{appVersion ? `v${appVersion}` : "Trung tâm vận hành"}</span>
          </div>
        </div>
        <nav>
          {navGroups.map((group) => {
            const items = group.items.filter((item) => !item.roles || item.roles.includes(user.role));
            if (!items.length) return null;
            return (
              <div className="nav-group" key={group.title}>
                <p className="nav-group-title">{group.title}</p>
                {items.map((item) => {
                  const active = item.href === "/settings/data" ? pathname.startsWith("/settings") : pathname === item.href;
                  return (
                    <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined} onClick={() => setOpen(false)}>
                      <NavIcon path={item.icon} />
                      <span><strong>{item.label}</strong><small>{item.desc}</small></span>
                    </Link>
                  );
                })}
              </div>
            );
          })}
        </nav>
        {/* Ghim xuống đáy: thoát ứng dụng là thao tác nguy hiểm nhất nhưng trước đây nằm ngay
            cạnh email người dùng ở đầu trang, chỗ dễ bấm nhầm nhất. */}
        <div className="sidebar-footer">
          <div className={`health-card${apiError ? " offline" : ""}`}>
            <span>{apiError ? "API gặp lỗi" : "API hoạt động"}</span>
            <small>{apiBaseLabel}</small>
          </div>
          {exitError ? <span className="exit-error" role="alert">{exitError}</span> : null}
          <div className="sidebar-actions">
            <button type="button" onClick={handleLogout}>Đăng xuất</button>
            {user.desktop_app && user.desktop_control_token ? <button className="exit-button" type="button" onClick={() => setAskExit(true)} disabled={exiting}>{exiting ? "Đang thoát…" : "Thoát ứng dụng"}</button> : null}
          </div>
        </div>
      </aside>
      <button className="sidebar-backdrop" type="button" aria-label="Đóng menu điều hướng" onClick={() => setOpen(false)} />

      <section className="cockpit-main">
        <header className="cockpit-header">
          <button className="drawer-button" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-controls="mobile-navigation" aria-label={open ? "Đóng menu điều hướng" : "Mở menu điều hướng"}>
            {open ? "Đóng menu" : "Menu"}
          </button>
          {heading}
          <div className="user-menu" role="group" aria-label="Tài khoản hiện tại">
            <span className="user-email" title={user.email}>{user.email}</span>
            <strong>{roleLabel(user.role)}</strong>
            <ThemeToggle />
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
