"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminUser, CurrentUser, loadUsers, updateUser } from "@/lib/api";
import { errorMessage, roleLabel } from "@/lib/format";

export function UsersSettingsPage({ currentUser, accounts }: { currentUser: CurrentUser; accounts: string[] }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState<number | null>(null);
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
  return <section className="section panel wide"><div className="section-heading"><div><p className="section-label">Phân quyền truy cập</p><h2>Người dùng và phạm vi tài khoản</h2><p>Chủ sở hữu không thể tự hạ quyền hoặc tự ngừng kích hoạt tài khoản của mình.</p></div></div><div className="target-list">{users.map((user) => <article className="user-card" key={user.id}><div className="record-title"><div><strong>{user.display_name || user.email}</strong><span>{user.email}</span></div><span className="status-badge" data-status={user.active ? "active" : "archived"}>{user.active ? "Đang hoạt động" : "Đã lưu trữ"}</span></div><div className="row-actions"><label className="sr-only" htmlFor={`role-${user.id}`}>Vai trò của {user.email}</label><select id={`role-${user.id}`} value={user.role} onChange={(event) => void patch(user, { role: event.target.value as AdminUser["role"] })} disabled={saving === user.id || user.email === currentUser.email}><option value="owner">{roleLabel("owner")}</option><option value="operator">{roleLabel("operator")}</option><option value="viewer">{roleLabel("viewer")}</option></select><button type="button" onClick={() => void patch(user, { active: !user.active })} disabled={saving === user.id || user.email === currentUser.email}>{user.active ? "Lưu trữ" : "Kích hoạt lại"}</button></div>{user.role !== "owner" ? <fieldset className="filter-stack"><legend className="field-label">Tài khoản được truy cập</legend><div className="account-options">{accounts.map((account) => <label className="account-option" key={account}><input type="checkbox" checked={user.accounts.includes(account)} onChange={() => toggleAccount(user, account)} disabled={saving === user.id} />{account}</label>)}</div></fieldset> : <p className="hint">Chủ sở hữu có quyền truy cập tất cả tài khoản.</p>}</article>)}{!users.length ? <p className="empty">Chưa có người dùng nào.</p> : null}</div>{message ? <p className="upload-result" role="status">{message}</p> : null}</section>;
}
