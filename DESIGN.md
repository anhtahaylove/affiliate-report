# Commerce Intelligence Design System

## Locked direction

Version 2 uses **Momentum Canvas** as the production App Shell and dashboard direction. It is a commerce-growth workspace, not a generic admin template.

- Use Signal Grid patterns inside operational queues, alerts, imports and order triage.
- Use Ledger Studio patterns inside finance, settlement and reconciliation views.
- Do not mix the three prototype shells. Momentum Canvas owns navigation, page framing and responsive behavior.
- Prototype routes, fixtures and picker code are development-only and must be removed before the installer build.

## Visual language

Use semantic tokens only:

- Graphite: page and high-contrast surfaces.
- Ivory: light surfaces and calm reading areas.
- Signal cyan: navigation, links, focus and primary actions.
- Performance lime: healthy growth and on-pace performance.
- Coral: loss, rejection and urgent risk.
- Amber: warning, pending and attention required.

No decorative gradients, glassmorphism or nested-card stacks. Be Vietnam Pro remains the product font; numeric output uses tabular numerals. Borders and spacing create hierarchy before shadows.

## App Shell

### Desktop

- Sidebar is 248 px expanded and 72 px collapsed.
- Sticky contextual header contains page title, freshness/status and role-allowed actions.
- The global scope bar owns account, date and status filters and keeps them in the URL.
- `Ctrl/Cmd + K` opens a role-aware command palette.

### Mobile

Mobile is a first-class composition, not the desktop grid stacked into one column.

- Full-width bottom navigation: Tổng quan, Đơn hàng, Nhập dữ liệu and Thêm.
- Thêm opens an accessible bottom action sheet for Phân tích, Mục tiêu, Account and Settings according to role.
- Global filters open in a bottom sheet with applied-filter count, clear and apply actions.
- Tables become scan-friendly cards or expandable rows; they never require the viewport itself to scroll horizontally.
- Primary actions stay reachable near the bottom thumb zone. Page content reserves bottom safe-area space so the final item is never obscured.
- Dense KPI areas use a deliberate 2-column compact grid where 390 px permits it and a single column at narrow widths when readability requires it.

## Theme preferences

- Theme values are `system`, `light` and `dark`.
- Theme is configured only in **Cài đặt > Giao diện**.
- Do not place a theme toggle in the header, sidebar, user menu or mobile navigation.
- A small local cache may prevent first-paint flash; the server preference is the source of truth after authentication.

## Page hierarchy

- Dashboard: Today Pulse, target/forecast/pace, action alerts, trend, account contribution, settlement and freshness.
- Analytics: tabs for Tài chính, Account, Sản phẩm & Nội dung, Đối soát and Chất lượng dữ liệu.
- Orders: sticky filter/action toolbar, saved views, column choice, desktop table and mobile cards.
- Imports: Account -> Files -> Queue review -> Upload, with progress and per-file outcomes.
- Targets: account/ALL planner, prior-month comparison, copy previous target and safe inline edit.
- Accounts: active/archive grouping and explicit permission-aware actions.
- Settings: Giao diện, Dữ liệu, Cập nhật and Người dùng.

## Accessibility and motion

- Target WCAG 2.2 AA.
- Every interactive control has a visible focus state and meaningful accessible name.
- Dialogs, sheets, menus, tabs and command palette support full keyboard navigation and focus restoration.
- Status is expressed with text/icon as well as color.
- Charts provide title, description and an equivalent data table.
- Motion lasts 120-220 ms, uses opacity/transform only and respects `prefers-reduced-motion`.

## Responsive acceptance

- 320 x 720: no viewport overflow; primary flows and bottom navigation remain usable.
- 390 x 844: polished phone composition with compact KPI layout and safe-area handling.
- 768 x 1024: tablet layout makes intentional use of width and does not simply stretch mobile cards.
- 1440 x 900: full Momentum Canvas shell, stable hierarchy and efficient operations density.
