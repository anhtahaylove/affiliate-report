"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { apiUrl, CurrentUser, logout } from "@/lib/api";

type NavItem = { href: string; label: string; roles?: Array<CurrentUser["role"]> };

const navItems: NavItem[] = [
  { href: "/", label: "Dashboard" },
  { href: "/analytics", label: "Phân tích" },
  { href: "/orders", label: "Đơn hàng" },
  { href: "/imports", label: "Import", roles: ["operator", "owner"] },
  { href: "/targets", label: "Mục tiêu" },
  { href: "/accounts", label: "Account", roles: ["owner"] },
  { href: "/settings/data", label: "Dữ liệu", roles: ["owner"] },
  { href: "/settings/update", label: "Cập nhật", roles: ["owner"] },
  { href: "/settings/users", label: "Người dùng", roles: ["owner"] },
];

export function AppShell({ user, apiError, children }: { user: CurrentUser; apiError?: string; children: ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const apiBaseLabel = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "same-origin";
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

  return (
    <main className={`cockpit-shell${open ? " nav-open" : ""}`}>
      <aside id="mobile-navigation" className="sidebar" aria-label="Điều hướng chính">
        <div className="sidebar-brand">
          <Image className="brand-mark" src="/icon-192.png" alt="" width={42} height={42} priority />
          <div>
            <strong>TikTok Affiliate</strong>
            <span>Operations Cockpit</span>
          </div>
        </div>
        <nav>
          {visibleItems.map((item) => (
            <Link key={item.href} href={item.href} aria-current={pathname === item.href ? "page" : undefined} onClick={() => setOpen(false)}>
              {item.label}
            </Link>
          ))}
        </nav>
        <div className={`health-card${apiError ? " offline" : ""}`}>
          <span>{apiError ? "API lỗi" : "API online"}</span>
          <small>{apiBaseLabel}</small>
        </div>
      </aside>

      <section className="cockpit-main">
        <header className="cockpit-header">
          <button className="drawer-button" type="button" onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-controls="mobile-navigation">
            Menu
          </button>
          <div className="user-menu" role="group" aria-label="Tài khoản hiện tại">
            <span>{user.email}</span>
            <strong>{user.role}</strong>
            <button type="button" onClick={handleLogout}>Đăng xuất</button>
          </div>
        </header>
        {children}
      </section>
    </main>
  );
}

export function AuthCard({ message }: { message: string }) {
  return (
    <main className="auth-shell">
      <section className="auth-card panel">
        <div className="brand-badge">AFF</div>
        <h1>TikTok Affiliate Report</h1>
        <p>Vui lòng đăng nhập để xem Operations Cockpit.</p>
        <a className="button-link" href={`${apiUrl()}/auth/login`}>Đăng nhập</a>
        <p className="hint">{message}</p>
      </section>
    </main>
  );
}
