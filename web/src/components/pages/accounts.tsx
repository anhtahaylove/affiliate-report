"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AccountDeletePreview, AccountItem, createAccount, deleteAccount, loadAccounts, previewDeleteAccount, updateAccount } from "@/lib/api";
import { ConfirmDialog } from "@/components/ui";
import { invalidateApiCache } from "@/lib/use-api";
import { countsText, errorMessage, formatDateTime, integer } from "@/lib/format";

export function AccountsPage({ onAccountsChanged }: { onAccountsChanged: () => Promise<void> }) {
  const [records, setRecords] = useState<AccountItem[]>([]);
  const [hardDeleteSupported, setHardDeleteSupported] = useState(false);
  const [draft, setDraft] = useState({ code: "", display_name: "" });
  const [accountDrafts, setAccountDrafts] = useState<Record<string, { display_name: string; display_order: string }>>({});
  const [deletePreview, setDeletePreview] = useState<AccountDeletePreview | null>(null);
  const [message, setMessage] = useState("");
  // Trạng thái riêng thay vì suy luận tone từ nội dung message (kiểu regex-đoán-theo-chữ-đầu ở
  // targets.tsx) — cách đó dễ vỡ khi đổi câu chữ. State tường minh không mơ hồ.
  const [messageTone, setMessageTone] = useState<"success" | "danger">("success");
  const [syncWarning, setSyncWarning] = useState("");
  function report(tone: "success" | "danger", text: string) {
    setMessageTone(tone);
    setMessage(text);
  }
  const refreshAccounts = useCallback(async () => {
    const data = await loadAccounts();
    setRecords(data.items);
    setAccountDrafts(Object.fromEntries(data.items.map((item) => [item.code, { display_name: item.display_name, display_order: String(item.display_order) }])));
    setHardDeleteSupported(data.hard_delete_supported);
  }, []);
  useEffect(() => {
    async function load() {
      try { await refreshAccounts(); }
      catch (reason) { report("danger", errorMessage(reason, "Không thể tải danh sách tài khoản.")); }
    }
    void load();
  }, [refreshAccounts]);
  const activeRecords = useMemo(() => records.filter((record) => record.active), [records]);
  const archivedRecords = useMemo(() => records.filter((record) => !record.active), [records]);

  function keepCommittedRecord(record: AccountItem) {
    setRecords((current) => current.some((item) => item.code === record.code)
      ? current.map((item) => item.code === record.code ? record : item)
      : [...current, record]);
    setAccountDrafts((current) => ({
      ...current,
      [record.code]: { display_name: record.display_name, display_order: String(record.display_order) },
    }));
  }

  async function syncAfterMutation() {
    invalidateApiCache();
    try { await refreshAccounts(); }
    catch { /* Kết quả đã commit vẫn được giữ trong state cục bộ. */ }
    try {
      await onAccountsChanged();
      setSyncWarning("");
    } catch {
      setSyncWarning("Thay đổi đã được lưu, nhưng nhãn tài khoản ở các trang khác chưa đồng bộ. Hãy thử đồng bộ lại.");
    }
  }

  async function retryMetadataSync() {
    try {
      await onAccountsChanged();
      setSyncWarning("");
      report("success", "Đã đồng bộ tên tài khoản trên toàn ứng dụng.");
    } catch (reason) {
      setSyncWarning(errorMessage(reason, "Chưa đồng bộ được thông tin tài khoản trên các trang khác."));
    }
  }

  async function create() {
    const code = draft.code.trim().toUpperCase();
    if (!code) return report("danger", "Hãy nhập mã tài khoản.");
    // Khớp đúng ACCOUNT_CODE_RE ở backend (accounts.py) — chỉ chữ HOA vì `code` ở trên đã qua
    // .toUpperCase(), đúng dạng ACCOUNT_CODE_RE thật sự kiểm (giá trị sau chuẩn hoá). Bắt lỗi
    // tại chỗ thay vì đi một vòng API rồi mới biết: trước đây thiếu bước này, gõ dấu cách vào
    // mã tài khoản khiến Pydantic từ chối với lỗi 422 dạng mảng mà request() chưa giải mã được,
    // nên bấm Tạo không thấy phản hồi gì.
    if (!/^[A-Z0-9_.-]{1,64}$/.test(code)) return report("danger", "Mã tài khoản chỉ gồm A-Z, 0-9, _, - hoặc dấu chấm, tối đa 64 ký tự.");
    const displayName = draft.display_name.trim() || code;
    try {
      const created = await createAccount({ code, display_name: displayName });
      keepCommittedRecord(created);
      setDraft({ code: "", display_name: "" });
      report("success", `Đã tạo tài khoản ${code}.`);
      await syncAfterMutation();
    } catch (reason) {
      report("danger", errorMessage(reason, "Không thể tạo tài khoản."));
    }
  }
  async function patch(record: AccountItem, changes: Partial<AccountItem>) {
    try {
      const updated = await updateAccount(record.code, {
        display_name: changes.display_name,
        display_order: changes.display_order,
        active: changes.active,
      });
      keepCommittedRecord(updated);
      report("success", `Đã cập nhật ${record.code}.`);
      await syncAfterMutation();
    } catch (reason) {
      report("danger", errorMessage(reason, "Không thể cập nhật tài khoản."));
    }
  }

  async function saveAccount(record: AccountItem) {
    const current = accountDrafts[record.code];
    if (!current) return;
    const displayName = current.display_name.trim();
    if (!displayName) return report("danger", "Tên hiển thị không được để trống.");
    const order = Number(current.display_order);
    if (!Number.isInteger(order)) return report("danger", "Thứ tự hiển thị phải là số nguyên.");
    await patch(record, { display_name: displayName, display_order: order });
  }
  async function previewDelete(record: AccountItem) {
    try {
      const preview = await previewDeleteAccount(record.code);
      setDeletePreview(preview);
      report("success", `Ảnh hưởng khi xóa ${record.code}: ${countsText(preview.dependency_counts)}.`);
    } catch (reason) {
      report("danger", errorMessage(reason, "Không thể xem trước ảnh hưởng khi xóa tài khoản."));
    }
  }
  async function confirmDelete() {
    if (!deletePreview) return;
    try {
      const result = await deleteAccount(deletePreview.code, `XOA ${deletePreview.code}`);
      if (result.hard_deleted) {
        setRecords((current) => current.filter((record) => record.code !== result.code));
        setAccountDrafts((current) => {
          const next = { ...current };
          delete next[result.code];
          return next;
        });
      } else if (result.account) keepCommittedRecord(result.account);
      else setRecords((current) => current.map((record) => record.code === result.code ? { ...record, active: false } : record));
      report("success", result.hard_deleted ? `Đã xóa vĩnh viễn ${result.code}. Hệ thống đã tự tạo một bản sao lưu an toàn trước khi xóa.` : `Đã lưu trữ ${result.code}.`);
      setDeletePreview(null);
      await syncAfterMutation();
    } catch (reason) {
      report("danger", errorMessage(reason, "Không thể xóa tài khoản."));
    }
  }

  function accountCard(record: AccountItem) {
    const rowDraft = accountDrafts[record.code] ?? { display_name: record.display_name, display_order: String(record.display_order) };
    return (
      <article className="account-card" key={record.code} data-state={record.active ? "active" : "archived"}>
        <div className="record-title">
          <div><strong>{record.display_name}</strong><span>Mã: {record.code} · {record.active ? "Sẵn sàng lọc, nhập tệp và gán người dùng" : "Đã ẩn khỏi luồng vận hành mặc định"}</span></div>
          <span className="status-badge" data-status={record.active ? "active" : "archived"}>{record.active ? "Đang hoạt động" : "Đã lưu trữ"}</span>
        </div>
        <dl className="account-meta">
          <div><dt>Thứ tự</dt><dd>{integer.format(record.display_order)}</dd></div>
          <div><dt>Tạo lúc</dt><dd>{formatDateTime(record.created_at)}</dd></div>
          <div><dt>Cập nhật</dt><dd>{formatDateTime(record.updated_at)}</dd></div>
        </dl>
        <div className="account-edit-grid">
          <div className="field"><label htmlFor={`account-name-${record.code}`}>Tên hiển thị</label><input id={`account-name-${record.code}`} maxLength={128} value={rowDraft.display_name} onChange={(event) => setAccountDrafts((current) => ({ ...current, [record.code]: { ...rowDraft, display_name: event.target.value } }))} /></div>
          <div className="field"><label htmlFor={`account-order-${record.code}`}>Thứ tự hiển thị</label><input id={`account-order-${record.code}`} type="number" step="1" value={rowDraft.display_order} onChange={(event) => setAccountDrafts((current) => ({ ...current, [record.code]: { ...rowDraft, display_order: event.target.value } }))} /></div>
        </div>
        <div className="row-actions">
          <button type="button" onClick={() => void saveAccount(record)}>Lưu thay đổi</button>
          <button type="button" onClick={() => void patch(record, { active: !record.active })}>{record.active ? "Lưu trữ" : "Kích hoạt lại"}</button>
          <button type="button" className="danger-button" onClick={() => void previewDelete(record)}>Xem trước khi xóa</button>
        </div>
      </article>
    );
  }

  return (
    <section className="section panel accounts-workflow-page">
      <div className="section-heading">
        <div>
          <p className="section-label">Danh sách tài khoản</p>
          <h2>Quản lý tài khoản đang dùng và đã lưu trữ</h2>
          <p>{hardDeleteSupported ? "Có thể xóa vĩnh viễn sau khi tạo bản sao lưu." : "Dữ liệu dùng chung chỉ cho phép lưu trữ tài khoản; lịch sử vẫn được giữ lại."}</p>
        </div>
      </div>
      <div className="account-create-panel upload-form">
        <div className="field"><label htmlFor="new-account-code">Mã tài khoản mới</label><input id="new-account-code" value={draft.code} onChange={(event) => setDraft((current) => ({ ...current, code: event.target.value }))} placeholder="Ví dụ: SHOP_1 hoặc tên đăng nhập TikTok (vd. sarah.reign)" /></div>
        <div className="field"><label htmlFor="new-account-name">Tên hiển thị mới (không bắt buộc)</label><input id="new-account-name" maxLength={128} value={draft.display_name} onChange={(event) => setDraft((current) => ({ ...current, display_name: event.target.value }))} placeholder="Để trống sẽ dùng mã tài khoản" /></div>
        <button type="button" onClick={() => void create()}>Tạo tài khoản</button>
      </div>
      {/* Ngay dưới panel tạo tài khoản, không phải cuối trang: trước đây thông báo lỗi nằm sau
          toàn bộ danh sách account, nên với vài chục account đã tồn tại, bấm Tạo thất bại trông
          y hệt như không có phản hồi gì — phải cuộn hết xuống mới thấy dòng chữ giải thích. */}
      {message ? <p className="upload-result" data-tone={messageTone} role={messageTone === "danger" ? "alert" : "status"}>{message}</p> : null}
      <section className="account-summary-row" aria-labelledby="account-summary-title">
        <h3 className="sr-only" id="account-summary-title">Tổng quan tài khoản</h3>
        <span><strong>{integer.format(activeRecords.length)}</strong> đang hoạt động</span>
        <span><strong>{integer.format(archivedRecords.length)}</strong> đã lưu trữ</span>
      </section>
      <div className="account-sections">
        <section className="account-section" aria-labelledby="active-accounts-title">
          <div className="section-heading compact"><div><p className="section-label">Đang dùng</p><h3 id="active-accounts-title">Tài khoản đang vận hành</h3></div></div>
          {activeRecords.map(accountCard)}
          {!activeRecords.length ? <p className="empty">Chưa có tài khoản đang hoạt động.</p> : null}
        </section>
        <section className="account-section" aria-labelledby="archived-accounts-title">
          <div className="section-heading compact"><div><p className="section-label">Lưu trữ</p><h3 id="archived-accounts-title">Tài khoản đã lưu trữ</h3></div></div>
          {archivedRecords.map(accountCard)}
          {!archivedRecords.length ? <p className="empty">Chưa có tài khoản lưu trữ.</p> : null}
        </section>
      </div>
      {deletePreview ? <div className="delete-preview panel-muted" role="status"><strong>Xem trước {deletePreview.code}</strong><span>{deletePreview.action === "hard_delete" ? "Sẽ xóa vĩnh viễn sau khi sao lưu" : "Sẽ chuyển vào danh sách lưu trữ"} · {countsText(deletePreview.dependency_counts)}</span></div> : null}
      {syncWarning ? <div className="sync-warning" role="alert"><span>{syncWarning}</span><button type="button" onClick={() => void retryMetadataSync()}>Thử đồng bộ lại</button></div> : null}
      {!records.length ? <p className="empty">Chưa có tài khoản. Hãy tạo tài khoản đầu tiên để bắt đầu nhập dữ liệu.</p> : null}
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
