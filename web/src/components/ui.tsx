"use client";

import { ReactNode, useEffect, useId, useRef, useState } from "react";
import { CurrentUser } from "@/lib/api";
import { statusLabel } from "@/lib/format";

export function canWrite(user: CurrentUser | null) {
  return user?.role === "operator" || user?.role === "owner";
}

export function isOwner(user: CurrentUser | null) {
  return user?.role === "owner";
}

export function Notice({ text }: { text: string }) {
  return <section className="notice" role="alert">{text}</section>;
}

/** Khung xương giữ đúng chỗ nội dung sắp hiện, thay cho một dòng chữ "Đang tải…" làm nhảy layout. */
export function Skeleton({ rows = 4, tall = false, label }: { rows?: number; tall?: boolean; label: string }) {
  return (
    <div className="skeleton-grid" role="status" aria-busy="true" aria-label={label}>
      <div className="skeleton-row">
        {Array.from({ length: rows }, (_, index) => <div className="skeleton" key={index} />)}
      </div>
      {tall ? <div className="skeleton tall" /> : null}
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function StateCard({ text }: { text: string }) {
  return <section className="section panel"><p className="empty">{text}</p></section>;
}

export function Metric({ title, value, hint, tone }: { title: string; value: string; hint: string; tone?: "good" | "warning" | "critical" }) {
  return <article className="metric panel"><span>{title}</span><strong data-tone={tone}>{value}</strong><small>{hint}</small></article>;
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  return <span className="status-badge" data-status={status ?? "unknown"}>{statusLabel(status)}</span>;
}

/**
 * Hộp xác nhận dùng chung cho mọi thao tác nguy hiểm, dựng trên thẻ `dialog` native: gộp phần
 * xem trước ảnh hưởng và ô gõ cụm xác nhận vào cùng một chỗ thay vì hộp thoại của trình duyệt.
 */
export function ConfirmDialog({
  open,
  title,
  confirmLabel = "Xác nhận",
  confirmation,
  busy = false,
  children,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  confirmLabel?: string;
  confirmation?: string;
  busy?: boolean;
  children?: ReactNode;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [phrase, setPhrase] = useState("");
  // Nhiều hộp xác nhận cùng tồn tại trong một trang, nên id phải riêng cho từng hộp.
  const id = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const ready = !confirmation || phrase.trim() === confirmation;
  return (
    <dialog
      className="confirm-dialog"
      ref={ref}
      aria-labelledby={`${id}-title`}
      onClose={() => setPhrase("")}
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <h2 id={`${id}-title`}>{title}</h2>
      {children ? <div className="confirm-body">{children}</div> : null}
      {confirmation ? (
        <div className="field">
          <label htmlFor={`${id}-phrase`}>Nhập chính xác <strong>{confirmation}</strong></label>
          <input id={`${id}-phrase`} value={phrase} autoComplete="off" onChange={(event) => setPhrase(event.target.value)} />
          {/* Không khớp thì nút Xác nhận chỉ mờ đi, không nói lý do — dễ khiến tưởng app treo. */}
          {phrase && !ready ? <small className="hint" aria-live="polite">Chưa khớp với cụm ở trên.</small> : null}
        </div>
      ) : null}
      <div className="row-actions">
        <button type="button" onClick={onCancel} disabled={busy}>Huỷ</button>
        <button type="button" className="danger-button" onClick={onConfirm} disabled={busy || !ready}>{confirmLabel}</button>
      </div>
    </dialog>
  );
}
