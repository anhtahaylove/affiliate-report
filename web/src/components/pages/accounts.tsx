"use client";

import { useCallback, useEffect, useState } from "react";
import { AccountDeletePreview, AccountItem, createAccount, deleteAccount, loadAccounts, previewDeleteAccount, updateAccount } from "@/lib/api";
import { ConfirmDialog } from "@/components/ui";
import { invalidateApiCache } from "@/lib/use-api";
import { countsText, errorMessage } from "@/lib/format";

export function AccountsPage() {
  const [records, setRecords] = useState<AccountItem[]>([]);
  const [hardDeleteSupported, setHardDeleteSupported] = useState(false);
  const [draft, setDraft] = useState({ code: "" });
  const [accountDrafts, setAccountDrafts] = useState<Record<string, { display_order: string }>>({});
  const [deletePreview, setDeletePreview] = useState<AccountDeletePreview | null>(null);
  const [message, setMessage] = useState("");
  const refreshAccounts = useCallback(async () => {
    const data = await loadAccounts();
    setRecords(data.items);
    setAccountDrafts(Object.fromEntries(data.items.map((item) => [item.code, { display_order: String(item.display_order) }])));
    setHardDeleteSupported(data.hard_delete_supported);
  }, []);
  useEffect(() => {
    async function load() {
      try { await refreshAccounts(); }
      catch (reason) { setMessage(errorMessage(reason, "Không thể tải danh sách tài khoản.")); }
    }
    void load();
  }, [refreshAccounts]);
  async function create() {
    const code = draft.code.trim().toUpperCase();
    if (!code) return setMessage("Hãy nhập mã tài khoản.");
    try {
      // Mỗi account chỉ có một định danh — mã tài khoản. display_name vẫn tồn tại trong DB
      // (không đổi schema) nhưng luôn khớp code, không cho người dùng đặt riêng nữa.
      await createAccount({ code, display_name: code });
      invalidateApiCache();
      setDraft({ code: "" });
      setMessage(`Đã tạo tài khoản ${code}.`);
      await refreshAccounts();
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể tạo tài khoản."));
    }
  }
  async function patch(record: AccountItem, changes: Partial<AccountItem>) {
    try {
      invalidateApiCache();
      await updateAccount(record.code, {
        display_order: changes.display_order,
        active: changes.active,
      });
      setMessage(`Đã cập nhật ${record.code}.`);
      await refreshAccounts();
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể cập nhật tài khoản."));
    }
  }

  async function saveAccount(record: AccountItem) {
    const current = accountDrafts[record.code];
    if (!current) return;
    const order = Number(current.display_order);
    if (!Number.isInteger(order)) return setMessage("Thứ tự hiển thị phải là số nguyên.");
    await patch(record, { display_order: order });
  }
  async function previewDelete(record: AccountItem) {
    try {
      const preview = await previewDeleteAccount(record.code);
      setDeletePreview(preview);
      setMessage(`Ảnh hưởng khi xóa ${record.code}: ${countsText(preview.dependency_counts)}.`);
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể xem trước ảnh hưởng khi xóa tài khoản."));
    }
  }
  async function confirmDelete() {
    if (!deletePreview) return;
    try {
      const result = await deleteAccount(deletePreview.code, `XOA ${deletePreview.code}`);
      invalidateApiCache();
      setMessage(result.hard_deleted ? `Đã xóa vĩnh viễn ${result.code}. Bản sao lưu: ${result.backup_path}.` : `Đã lưu trữ ${result.code}.`);
      setDeletePreview(null);
      await refreshAccounts();
    } catch (reason) {
      setMessage(errorMessage(reason, "Không thể xóa tài khoản."));
    }
  }
  return (
    <section className="section panel">
      <div className="section-heading">
        <div>
          <p className="section-label">Danh sách tài khoản</p>
          <h2>Thêm và quản lý tài khoản</h2>
          <p>{hardDeleteSupported ? "Có thể xóa vĩnh viễn sau khi tạo bản sao lưu." : "Dữ liệu dùng chung chỉ cho phép lưu trữ tài khoản; lịch sử vẫn được giữ lại."}</p>
        </div>
      </div>
      <div className="upload-form">
        <div className="field"><label htmlFor="new-account-code">Mã tài khoản</label><input id="new-account-code" value={draft.code} onChange={(event) => setDraft({ code: event.target.value })} placeholder="SHOP_1 hoặc username TikTok" /></div>
        <button type="button" onClick={() => void create()}>Tạo tài khoản</button>
        {records.map((record) => {
          const rowDraft = accountDrafts[record.code] ?? { display_order: String(record.display_order) };
          return (
            <article className="import-item" key={record.code}>
              <div className="record-title"><strong>{record.code}</strong><span className="status-badge" data-status={record.active ? "active" : "archived"}>{record.active ? "Đang hoạt động" : "Đã lưu trữ"}</span></div>
              <span>Thứ tự {record.display_order}</span>
              <div className="account-edit-grid">
                <div className="field"><label htmlFor={`account-order-${record.code}`}>Thứ tự hiển thị</label><input id={`account-order-${record.code}`} type="number" step="1" value={rowDraft.display_order} onChange={(event) => setAccountDrafts((current) => ({ ...current, [record.code]: { display_order: event.target.value } }))} /></div>
              </div>
              <div className="row-actions"><button type="button" onClick={() => void saveAccount(record)}>Lưu thay đổi</button><button type="button" onClick={() => void patch(record, { active: !record.active })}>{record.active ? "Lưu trữ" : "Kích hoạt lại"}</button><button type="button" className="danger-button" onClick={() => void previewDelete(record)}>Xem trước khi xóa</button></div>
            </article>
          );
        })}
        {message ? <p className="upload-result" role="status">{message}</p> : null}
        {!records.length ? <p className="empty">Chưa có tài khoản. Hãy tạo tài khoản đầu tiên để bắt đầu nhập dữ liệu.</p> : null}
      </div>
      <ConfirmDialog
        open={deletePreview !== null}
        title={deletePreview?.action === "hard_delete" ? `Xóa vĩnh viễn tài khoản ${deletePreview?.code}?` : `Lưu trữ tài khoản ${deletePreview?.code}?`}
        confirmLabel={deletePreview?.action === "hard_delete" ? "Xóa vĩnh viễn" : "Lưu trữ"}
        confirmation={deletePreview ? `XOA ${deletePreview.code}` : undefined}
        onCancel={() => setDeletePreview(null)}
        onConfirm={() => void confirmDelete()}
      >
        <p>{deletePreview?.action === "hard_delete" ? "Hệ thống tạo bản sao lưu rồi mới xóa." : "Lịch sử vẫn được giữ lại; tài khoản chỉ bị ẩn khỏi danh sách đang hoạt động."}</p>
        <p className="hint">Ảnh hưởng: {deletePreview ? countsText(deletePreview.dependency_counts) : ""}</p>
      </ConfirmDialog>
    </section>
  );
}
