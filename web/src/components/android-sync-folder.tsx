"use client";

import { useEffect, useRef, useState } from "react";
import { pickAndroidSyncFolder, requestAndroidSyncFolderState, triggerAndroidSync } from "@/lib/android-native";
import { errorMessage, integer } from "@/lib/format";

type FolderState = { picked: boolean; label?: string };
type SyncResult = { imported: number; duplicate: number; rejected: number; message?: string };

/** Thư mục đồng bộ liên tục cho Android: người dùng chọn một thư mục qua Storage Access Framework
 * (mặc định gợi ý Download) một lần; từ đó app tự quét tệp affiliate_orders*.xlsx trong đó mỗi khi
 * mở app và khi bấm "Đồng bộ ngay", không cần chuyển tệp qua máy tính hay ghép cặp Wi-Fi.
 *
 * Toàn bộ việc quét/import/dời tệp chạy phía Java (MainActivity.AndroidDownloadBridge); component
 * này chỉ gọi bridge rồi lắng nghe kết quả qua CustomEvent — không tự gọi location.reload() hay tự
 * tạo CustomEvent (guard tĩnh account-directory-static.test.mjs cấm cả hai ngoài các file cho phép). */
export function AndroidSyncFolder({ account, onSynced }: { account: string; onSynced?: () => void }) {
  const [folder, setFolder] = useState<FolderState | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SyncResult | null>(null);
  const [error, setError] = useState("");

  function runSync(forAccount: string) {
    if (!forAccount) return setError("Hãy chọn tài khoản trước khi đồng bộ.");
    setBusy(true);
    setError("");
    try {
      triggerAndroidSync(forAccount);
    } catch (reason) {
      setBusy(false);
      setError(errorMessage(reason, "Không thể đồng bộ."));
    }
  }

  // Đọc qua ref (cập nhật trong effect riêng bên dưới, không phải lúc render — React 19 cấm sửa
  // ref trong render) thay vì đưa vào dependency array của effect mount: effect đó chỉ chạy một
  // lần ("quét khi mở app"), nhưng vẫn phải dùng account/onSynced/runSync mới nhất tại thời điểm
  // sự kiện native thực sự bắn về (có thể sau khi người dùng đã đổi account đang chọn).
  const latestRef = useRef({ account, onSynced, runSync });
  useEffect(() => {
    latestRef.current = { account, onSynced, runSync };
  });
  const autoSyncedRef = useRef(false);

  useEffect(() => {
    let active = true;
    function onFolderState(event: Event) {
      const detail = (event as CustomEvent<{ picked?: boolean; label?: string; error?: string }>).detail;
      setFolder({ picked: Boolean(detail?.picked), label: detail?.label });
      if (detail?.error) setError(detail.error);
      const { account: currentAccount, runSync: currentRunSync } = latestRef.current;
      if (detail?.picked && currentAccount && !autoSyncedRef.current) {
        autoSyncedRef.current = true;
        currentRunSync(currentAccount);
      }
    }
    function onSyncResult(event: Event) {
      const detail = (event as CustomEvent<{ imported?: number; duplicate?: number; rejected?: number; message?: string }>).detail;
      setBusy(false);
      setResult({
        imported: Number(detail?.imported ?? 0),
        duplicate: Number(detail?.duplicate ?? 0),
        rejected: Number(detail?.rejected ?? 0),
        message: detail?.message,
      });
      latestRef.current.onSynced?.();
    }
    window.addEventListener("affiliate-report-sync-folder", onFolderState);
    window.addEventListener("affiliate-report-sync-result", onSyncResult);
    // Bọc trong microtask để lỗi ném đồng bộ (bridge Android chưa sẵn sàng) rơi vào .catch() thay
    // vì setState ngay trong thân effect — cùng cách update-settings.tsx xử lý load trạng thái lúc mount.
    Promise.resolve()
      .then(() => requestAndroidSyncFolderState())
      .catch((reason: unknown) => {
        if (active) setError(errorMessage(reason, "Không thể kiểm tra thư mục đồng bộ."));
      });
    return () => {
      active = false;
      window.removeEventListener("affiliate-report-sync-folder", onFolderState);
      window.removeEventListener("affiliate-report-sync-result", onSyncResult);
    };
  }, []);

  function pick() {
    setError("");
    try {
      pickAndroidSyncFolder();
    } catch (reason) {
      setError(errorMessage(reason, "Không thể mở trình chọn thư mục."));
    }
  }

  return (
    <div className="inbox-hint android-sync-folder" role="note">
      <p><strong>Hoặc đồng bộ liên tục từ một thư mục trên máy</strong></p>
      <p>Android không cho chọn thẳng thư mục Download (giới hạn quyền riêng tư từ Android 11) — hãy chọn hoặc tạo mới một thư mục con bên trong Download, vd. <code>Download/TikTok</code>. Mỗi lần mở app hoặc bấm &quot;Đồng bộ ngay&quot;, hệ thống tự tìm tệp tên bắt đầu <code>affiliate_orders</code> trong thư mục đó, nhập vào tài khoản đang chọn rồi dời sang <code>.done</code>/<code>.failed</code>.</p>
      <p className="subtle">Vào Chrome → Cài đặt → Tải xuống → bật &quot;Hỏi vị trí lưu mỗi lần&quot; để chọn đúng thư mục con đó khi tải file TikTok, khỏi phải tự chuyển tệp vào sau.</p>
      <div className="android-sync-folder-row">
        <span className="status-badge" data-status={folder?.picked ? "active" : undefined}>
          {folder === null ? "Đang kiểm tra…" : folder.picked ? (folder.label ?? "Đã chọn thư mục") : "Chưa chọn thư mục"}
        </span>
        <button type="button" onClick={pick} disabled={busy}>{folder?.picked ? "Đổi thư mục" : "Chọn thư mục"}</button>
        <button type="button" onClick={() => runSync(account)} disabled={busy || !folder?.picked || !account}>{busy ? "Đang đồng bộ…" : "Đồng bộ ngay"}</button>
      </div>
      {result ? (
        <div className="android-sync-folder-row">
          <span className="status-badge" data-outcome="imported">{integer.format(result.imported)} đã nhập</span>
          <span className="status-badge" data-outcome="duplicate">{integer.format(result.duplicate)} trùng</span>
          <span className="status-badge" data-outcome="failed">{integer.format(result.rejected)} lỗi</span>
          {result.message ? <span className="subtle">{result.message}</span> : null}
        </div>
      ) : null}
      {error ? <p className="upload-result" data-tone="danger" role="alert">{error}</p> : null}
    </div>
  );
}
