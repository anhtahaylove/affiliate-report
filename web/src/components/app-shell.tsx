"use client";

import Image from "next/image";
import Link from "next/link";
import * as Dialog from "@radix-ui/react-dialog";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { BarChart3, CircleDollarSign, Command, Database, FileSpreadsheet, Home, LogIn, LogOut, MoreHorizontal, PackageSearch, PanelLeftClose, PanelLeftOpen, RefreshCw, Search, Settings, Shield, Target, UploadCloud, Users, WifiOff, X, XCircle, type LucideIcon } from "lucide-react";
import { apiUrl, CurrentUser, exitApplication, logout, type MetaResponse } from "@/lib/api";
import { ConfirmDialog } from "@/components/ui";
import { BottomSheet } from "@/components/primitives";
import { roleLabel } from "@/lib/format";
import { routeIsActive } from "@/lib/navigation";

type NavItem = { href: string; label: string; desc: string; icon: LucideIcon; roles?: Array<CurrentUser["role"]>; mobilePrimary?: boolean; sharedDeploymentOnly?: boolean };

const navGroups: Array<{ title: string; items: NavItem[] }> = [
  {
    title: "Báo cáo",
    items: [
      { href: "/", label: "Tổng quan", desc: "Hoa hồng, mục tiêu, cảnh báo", icon: Home, mobilePrimary: true },
      { href: "/analytics", label: "Phân tích", desc: "Tài chính và xu hướng", icon: BarChart3 },
      { href: "/orders", label: "Đơn hàng", desc: "Tra cứu và xuất Excel", icon: PackageSearch, mobilePrimary: true },
    ],
  },
  {
    title: "Vận hành",
    items: [
      { href: "/imports", label: "Nhập dữ liệu", desc: "Nhập tệp TikTok .xlsx", icon: UploadCloud, roles: ["operator", "owner"], mobilePrimary: true },
      { href: "/targets", label: "Mục tiêu", desc: "Chỉ tiêu ngày và mục tiêu tháng", icon: Target },
      { href: "/accounts", label: "Tài khoản", desc: "Thêm, sửa và lưu trữ", icon: CircleDollarSign, roles: ["owner"] },
    ],
  },
  {
    title: "Hệ thống",
    items: [
      { href: "/settings/preferences", label: "Giao diện", desc: "Sáng, tối hoặc theo hệ thống", icon: Settings },
      { href: "/settings/data", label: "Dữ liệu", desc: "Xóa, sao lưu, khôi phục", icon: Database, roles: ["owner"] },
      { href: "/settings/sync", label: "Thiết bị & đồng bộ", desc: "Chuyển dữ liệu bằng gói mã hóa", icon: RefreshCw, roles: ["owner"] },
      { href: "/settings/update", label: "Cập nhật", desc: "Kiểm tra và cài bản mới", icon: FileSpreadsheet, roles: ["owner"] },
      { href: "/settings/users", label: "Người dùng", desc: "Vai trò và phạm vi tài khoản", icon: Users, roles: ["owner"], sharedDeploymentOnly: true },
    ],
  },
];

// Bản cài trên máy chỉ có đúng một danh tính: auth.py trả local_principal() bất kể session
// token, nên không có ai để phân vai và "Đăng xuất" không đăng xuất được gì — bấm xong chỉ
// tải lại trang rồi quay về đúng chỗ cũ. Ẩn cả cụm đó đi thay vì bày ra rồi không làm gì.
// Chế độ oidc dùng chung vẫn cần đủ, nên gate theo auth_method chứ không xoá.
export function isSharedDeployment(user: CurrentUser) {
  return user.auth_method !== "local";
}

function allowedItems(user: CurrentUser) {
  const shared = isSharedDeployment(user);
  return navGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => (!item.roles || item.roles.includes(user.role)) && (shared || !item.sharedDeploymentOnly)),
    }))
    .filter((group) => group.items.length);
}

function NavLink({ item, active, onClick, compact = false, iconOnly = false }: { item: NavItem; active: boolean; onClick?: () => void; compact?: boolean; iconOnly?: boolean }) {
  const Icon = item.icon;
  return (
    <Link href={item.href} aria-current={active ? "page" : undefined} aria-label={iconOnly ? item.label : undefined} title={iconOnly ? item.label : undefined} onClick={onClick} className={compact ? "mobile-nav-link" : undefined}>
      <Icon className="nav-icon" size={compact ? 20 : 18} aria-hidden="true" />
      <span><strong>{item.label}</strong>{compact ? null : <small>{item.desc}</small>}</span>
    </Link>
  );
}

export function AppShell({ user, appVersion, runtimePlatform, heading, children, collapsed = false, onCollapsedChange }: { user: CurrentUser; appVersion?: string; runtimePlatform?: MetaResponse["runtime_platform"]; heading?: ReactNode; children: ReactNode; collapsed?: boolean; onCollapsedChange?: (collapsed: boolean) => Promise<void> }) {
  const pathname = usePathname();
  const groups = useMemo(() => allowedItems(user), [user]);
  const allItems = groups.flatMap((group) => group.items);
  const primaryMobile = allItems.filter((item) => item.mobilePrimary).slice(0, 3);
  const moreItems = allItems.filter((item) => !primaryMobile.some((primary) => primary.href === item.href));
  const moreActive = moreItems.some((item) => routeIsActive(pathname, item.href));
  const [moreOpen, setMoreOpen] = useState(false);
  const [exiting, setExiting] = useState(false);
  const [exitError, setExitError] = useState("");
  const [askExit, setAskExit] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState("");
  const [savingSidebar, setSavingSidebar] = useState(false);
  const moreButtonRef = useRef<HTMLButtonElement>(null);
  const sharedDeployment = isSharedDeployment(user);
  const commandItems = allItems.filter((item) => `${item.label} ${item.desc}`.toLocaleLowerCase("vi").includes(commandQuery.trim().toLocaleLowerCase("vi")));

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen((open) => !open);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  async function toggleSidebar() {
    if (!onCollapsedChange || savingSidebar) return;
    setSavingSidebar(true);
    try {
      await onCollapsedChange(!collapsed);
    } finally {
      setSavingSidebar(false);
    }
  }

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
    <main className={`cockpit-shell${collapsed ? " sidebar-collapsed" : ""}`}>
      <aside className="sidebar" aria-label="Điều hướng chính">
        <div className="sidebar-brand">
          <Image className="brand-mark" src="/icon-192.png" alt="" width={38} height={38} priority />
          <div>
            <strong>Affiliate Report</strong>
            <span>{appVersion ? `Phiên bản ${appVersion}` : "Báo cáo vận hành"}</span>
          </div>
          <button className="sidebar-collapse" type="button" onClick={() => void toggleSidebar()} disabled={savingSidebar} aria-label={collapsed ? "Mở rộng thanh điều hướng" : "Thu gọn thanh điều hướng"} title={collapsed ? "Mở rộng" : "Thu gọn"}>
            {collapsed ? <PanelLeftOpen size={17} aria-hidden="true" /> : <PanelLeftClose size={17} aria-hidden="true" />}
          </button>
        </div>
        <nav>
          {groups.map((group) => (
            <div className="nav-group" key={group.title}>
              <p className="nav-group-title">{group.title}</p>
              {group.items.map((item) => <NavLink key={item.href} item={item} active={routeIsActive(pathname, item.href)} iconOnly={collapsed} />)}
            </div>
          ))}
        </nav>
        <div className="sidebar-footer">
          {exitError ? <span className="exit-error" role="alert">{exitError}</span> : null}
          <div className="sidebar-actions">
            {sharedDeployment ? <button type="button" onClick={handleLogout} aria-label="Đăng xuất" title={collapsed ? "Đăng xuất" : undefined}><LogOut size={16} aria-hidden="true" /><span>Đăng xuất</span></button> : null}
            {runtimePlatform !== "android" && user.desktop_app && user.desktop_control_token ? <button className="exit-button" type="button" onClick={() => setAskExit(true)} disabled={exiting} aria-label="Thoát ứng dụng" title={collapsed ? "Thoát ứng dụng" : undefined}><XCircle size={16} aria-hidden="true" /><span>{exiting ? "Đang thoát…" : "Thoát"}</span></button> : null}
          </div>
        </div>
      </aside>

      <section className="cockpit-main">
        <header className="cockpit-header">
          {heading}
          <button className="command-trigger" type="button" onClick={() => setCommandOpen(true)} aria-label="Mở tìm kiếm nhanh">
            <Search size={16} aria-hidden="true" /><span>Tìm nhanh</span><kbd>Ctrl K</kbd>
          </button>
          {sharedDeployment ? (
            <div className="user-menu" role="group" aria-label="Tài khoản hiện tại">
              <Shield size={16} aria-hidden="true" />
              <span className="user-email" title={user.email}>{user.email}</span>
              <strong>{roleLabel(user.role)}</strong>
            </div>
          ) : null}
        </header>
        {children}
      </section>

      <nav className="mobile-bottom-nav" aria-label="Điều hướng nhanh mobile">
        {primaryMobile.map((item) => <NavLink key={item.href} item={item} active={routeIsActive(pathname, item.href)} compact />)}
        <button ref={moreButtonRef} className="mobile-nav-link" type="button" aria-haspopup="dialog" aria-expanded={moreOpen} aria-current={moreActive ? "page" : undefined} onClick={() => setMoreOpen(true)}>
          <MoreHorizontal size={20} aria-hidden="true" />
          <span><strong>Thêm</strong></span>
        </button>
      </nav>

      <BottomSheet open={moreOpen} onOpenChange={setMoreOpen} restoreFocusRef={moreButtonRef} title="Thêm mục" description="Các khu vực ít dùng hơn trong trung tâm vận hành.">
        <div className="more-sheet-list">
          {moreItems.map((item) => <NavLink key={item.href} item={item} active={routeIsActive(pathname, item.href)} onClick={() => setMoreOpen(false)} />)}
          {sharedDeployment ? <button className="more-sheet-action" type="button" onClick={() => void handleLogout()}><LogOut size={18} aria-hidden="true" />Đăng xuất</button> : null}
        </div>
      </BottomSheet>

      <Dialog.Root open={commandOpen} onOpenChange={setCommandOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="sheet-overlay command-overlay" />
          <Dialog.Content className="command-palette" aria-describedby="command-description">
            <Dialog.Title><Command size={18} aria-hidden="true" />Đi đến nhanh</Dialog.Title>
            <Dialog.Description id="command-description">Tìm trang hoặc hành động bạn có quyền truy cập.</Dialog.Description>
            <label className="command-search"><Search size={18} aria-hidden="true" /><span className="sr-only">Tìm trang</span><input value={commandQuery} onChange={(event) => setCommandQuery(event.target.value)} placeholder="Nhập tên trang…" /></label>
            <div className="command-results">
              {commandItems.map((item) => {
                const Icon = item.icon;
                return <Link key={item.href} href={item.href} aria-current={routeIsActive(pathname, item.href) ? "page" : undefined} onClick={() => setCommandOpen(false)}><Icon size={18} aria-hidden="true" /><span><strong>{item.label}</strong><small>{item.desc}</small></span></Link>;
              })}
              {!commandItems.length ? <p className="empty">Không tìm thấy mục phù hợp.</p> : null}
            </div>
            <Dialog.Close className="command-close" aria-label="Đóng"><X size={18} aria-hidden="true" /></Dialog.Close>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <ConfirmDialog
        open={askExit}
        title="Thoát hoàn toàn Affiliate Report?"
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

// Chỉ dùng khi backend trả 401 — trong bản cài một danh tính, principal_from_session()
// luôn trả về local_principal() bất kể session, nên 401 KHÔNG BAO GIỜ xảy ra ở đó (trừ khi
// truy cập ngoài loopback, việc đó trả 403 riêng). 401 chỉ nổi lên ở bản triển khai OIDC
// dùng chung khi phiên hết hạn — nút Đăng nhập lúc đó thật sự làm được việc.
export function SignInCard({ message }: { message: string }) {
  return (
    <main className="auth-shell">
      <section className="auth-card panel">
        <div className="brand-badge">AFF</div>
        <h1>Affiliate Report</h1>
        <p>Phiên đăng nhập đã hết hạn hoặc chưa xác thực.</p>
        <a className="button-link" href={`${apiUrl()}/auth/login`}><LogIn size={17} aria-hidden="true" />Đăng nhập</a>
        <p className="hint">{message}</p>
      </section>
    </main>
  );
}

// Dùng khi không gọi được API — app bị Thoát, mạng đứt, hoặc backend lỗi. Trước đây các
// trường hợp này bị gộp chung với SignInCard và cùng hiện nút "Đăng nhập", dù backend đã
// chết hẳn nên bấm vào cũng gọi lại đúng chỗ không phản hồi. "Thử lại" mới là hành động có
// tác dụng thật.
export function ConnectionErrorCard({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <main className="auth-shell">
      <section className="auth-card panel">
        <div className="brand-badge brand-badge-warning"><WifiOff size={24} aria-hidden="true" /></div>
        <h1>Không kết nối được tới ứng dụng</h1>
        <p className="hint">{message}</p>
        {/* Bấm Thử lại đặt loading=true, và nhánh "if (loading)" của OperationsPage vẽ lại
            trước khi component này kịp render busy state — nên không cần disabled/nhãn riêng,
            màn hình "Đang tải…" đã là chỉ báo bận sẵn có. */}
        <button className="button-link" type="button" onClick={onRetry}><RefreshCw size={17} aria-hidden="true" />Thử lại</button>
      </section>
    </main>
  );
}
