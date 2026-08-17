"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminUser, CurrentUser, IdentityPolicy, loadUsers, updateUser } from "@/lib/api";
import { errorMessage, integer, roleLabel } from "@/lib/format";
import { ConfirmDialog } from "@/components/ui";
import { KeyRound, ShieldCheck } from "lucide-react";
import { AccountIdentity } from "@/components/account-identity";
import type { AccountDirectory } from "@/lib/account-directory";
import styles from "./settings-commerce.module.css";

export function UsersSettingsPage({ currentUser, accounts, directory, identityPolicy }: { currentUser: CurrentUser; accounts: string[]; directory: AccountDirectory; identityPolicy: IdentityPolicy }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState<number | null>(null);
  const [pendingRoleChange, setPendingRoleChange] = useState<{ user: AdminUser; role: AdminUser["role"] } | null>(null);
  const refresh = useCallback(async () => {
    const data = await loadUsers();
    setUsers(data.items);
  }, []);
  useEffect(() => {
    async function load() {
      try { await refresh(); }
      catch (reason) { setMessage(errorMessage(reason, "Không thể tải danh sách người dùng.")); }
    }
    void load();
  }, [refresh]);
  const activeUsers = useMemo(() => users.filter((user) => user.active), [users]);
  const archivedUsers = useMemo(() => users.filter((user) => !user.active), [users]);
  async function patch(user: AdminUser, changes: Partial<AdminUser>) {
    setSaving(user.id);
    try {
      await updateUser(user.id, changes);
      setMessage(`Đã cập nhật ${user.email}.`);
      await refresh();
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể cập nhật người dùng."));
    } finally {
      setSaving(null);
    }
  }
  function toggleAccount(user: AdminUser, account: string) {
    const next = user.accounts.includes(account) ? user.accounts.filter((item) => item !== account) : [...user.accounts, account];
    void patch(user, { accounts: next });
  }
  // Đổi thành/từ "owner" (toàn quyền) áp dụng ngay lập tức không có cách xem lại — khác mọi thao
  // tác nhạy cảm khác trong app đều có ConfirmDialog. Đổi qua lại operator/viewer vẫn tức thời vì
  // rủi ro thấp hơn nhiều.
  function requestRoleChange(user: AdminUser, role: AdminUser["role"]) {
    if (role === "owner" || user.role === "owner") setPendingRoleChange({ user, role });
    else void patch(user, { role });
  }
  async function confirmRoleChange() {
    if (!pendingRoleChange) return;
    await patch(pendingRoleChange.user, { role: pendingRoleChange.role });
    setPendingRoleChange(null);
  }
  return (
    <section className={`${styles.surface} section ${styles.section} panel wide ${styles.wide} users-settings-page ${styles.usersSettingsPage}`}>
      <div className={`section-heading ${styles.sectionHeading}`}>
        <div>
          <p className={`section-label ${styles.sectionLabel}`}>Phân quyền truy cập</p>
          <h2>Người dùng, vai trò và phạm vi tài khoản</h2>
          <p>Chủ sở hữu không thể tự hạ quyền hoặc tự ngừng kích hoạt tài khoản của mình.</p>
        </div>
      </div>
      <section className={`settings-summary-row ${styles.settingsSummaryRow}`} aria-labelledby="permissions-summary-title">
        <h3 className={`sr-only`} id="permissions-summary-title">Tổng quan phân quyền</h3>
        <span><strong>{integer.format(activeUsers.length)}</strong> đang hoạt động</span>
        <span><strong>{integer.format(archivedUsers.length)}</strong> đã lưu trữ</span>
        <span><strong>{integer.format(accounts.length)}</strong> tài khoản có thể gán</span>
      </section>
      {identityPolicy.oidc_allowlist_enforced ? (
        <aside className={`identity-policy ${styles.identityPolicy}`} aria-labelledby="identity-policy-title">
          <KeyRound size={20} aria-hidden="true" />
          <div>
            <h3 id="identity-policy-title">Chỉ email được cấp phép mới đăng nhập được</h3>
            <p>Hệ thống chỉ cho những email đã được người quản trị cấp phép đăng nhập. Quy định này áp dụng cho cả lượt đăng nhập mới lẫn người đang dùng ứng dụng.</p>
            <p className={`hint ${styles.hint}`}><ShieldCheck size={15} aria-hidden="true" /> Bật &quot;Đang hoạt động&quot; cho một người dùng chưa chắc đủ để họ đăng nhập được — email của họ còn phải nằm trong danh sách được cấp phép. Nếu người quản trị vừa cập nhật danh sách này, những người không còn được phép sẽ bị đăng xuất trong lượt thao tác kế tiếp.</p>
          </div>
        </aside>
      ) : null}
      <div className={`target-list ${styles.targetList} user-management-list ${styles.userManagementList}`}>
        {users.map((user) => {
          const lockedSelf = user.email === currentUser.email;
          return (
            <article className={`user-card ${styles.userCard}`} key={user.id} data-state={user.active ? "active" : "archived"}>
              <div className={`record-title ${styles.recordTitle}`}>
                <div><strong>{user.display_name || user.email}</strong><span>{user.email}</span></div>
                <span className={`status-badge`} data-status={user.active ? "active" : "archived"}>{user.active ? "Đang hoạt động" : "Đã lưu trữ"}</span>
              </div>
              <div className={`user-permission-grid ${styles.userPermissionGrid}`}>
                <div className={`field ${styles.field}`}>
                  <label htmlFor={`role-${user.id}`}>Vai trò</label>
                  <select id={`role-${user.id}`} value={user.role} onChange={(event) => requestRoleChange(user, event.target.value as AdminUser["role"])} disabled={saving === user.id || lockedSelf}>
                    <option value="owner">{roleLabel("owner")}</option>
                    <option value="operator">{roleLabel("operator")}</option>
                    <option value="viewer">{roleLabel("viewer")}</option>
                  </select>
                </div>
                <div className={`row-actions ${styles.rowActions}`}>
                  <button type="button" onClick={() => void patch(user, { active: !user.active })} disabled={saving === user.id || lockedSelf}>{user.active ? "Lưu trữ" : "Kích hoạt lại"}</button>
                </div>
              </div>
              {user.role !== "owner" ? (
                <fieldset className={`filter-stack`}>
                  <legend className={`field-label`}>Tài khoản được truy cập ({integer.format(user.accounts.length)}/{integer.format(accounts.length)})</legend>
                  <div className={`account-options`}>{accounts.map((account) => <label className={`account-option`} key={account}><input type="checkbox" checked={user.accounts.includes(account)} onChange={() => toggleAccount(user, account)} disabled={saving === user.id} /><AccountIdentity directory={directory} code={account} /></label>)}</div>
                </fieldset>
              ) : <p className={`hint ${styles.hint}`}>Chủ sở hữu có quyền truy cập tất cả tài khoản.</p>}
              {lockedSelf ? <p className={`hint ${styles.hint}`}>Đang đăng nhập bằng người dùng này nên các thao tác tự hạ quyền/tự khóa đã bị chặn.</p> : null}
            </article>
          );
        })}
        {!users.length ? <p className={`empty`}>Chưa có người dùng nào.</p> : null}
      </div>
      {message ? <p className={`upload-result`} role="status">{message}</p> : null}
      <ConfirmDialog
        open={pendingRoleChange !== null}
        title={`Đổi vai trò của ${pendingRoleChange?.user.email ?? ""} thành "${roleLabel(pendingRoleChange?.role)}"?`}
        confirmLabel="Đổi vai trò"
        busy={saving === pendingRoleChange?.user.id}
        onCancel={() => setPendingRoleChange(null)}
        onConfirm={() => void confirmRoleChange()}
      >
        <p>{pendingRoleChange?.role === "owner"
          ? "Chủ sở hữu có toàn quyền quản lý tài khoản, người dùng và dữ liệu của cửa hàng."
          : "Người này sẽ mất toàn quyền quản lý tài khoản, người dùng và dữ liệu của cửa hàng."}</p>
      </ConfirmDialog>
    </section>
  );
}
