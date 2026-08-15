type AffiliateReportAndroidBridge = {
  download: (url: string, filename: string, mimeType: string) => void;
  pickSyncFolder: () => void;
  requestSyncFolderState: () => void;
  syncNow: (account: string) => void;
};

declare global {
  interface Window {
    AffiliateReportAndroid?: AffiliateReportAndroidBridge;
  }
}

export function requestAndroidNativeDownload(url: string, filename: string, mimeType: string) {
  const bridge = window.AffiliateReportAndroid;
  if (!bridge || typeof bridge.download !== "function") {
    throw new Error("Ứng dụng Android chưa sẵn sàng nhận tệp. Hãy đóng và mở lại ứng dụng.");
  }
  bridge.download(url, filename, mimeType);
}

const SYNC_FOLDER_UNSUPPORTED = "Phiên bản Android này chưa hỗ trợ đồng bộ thư mục. Hãy cập nhật ứng dụng.";

/** Mở trình chọn thư mục SAF của Android; kết quả báo về qua CustomEvent "affiliate-report-sync-folder". */
export function pickAndroidSyncFolder() {
  const bridge = window.AffiliateReportAndroid;
  if (!bridge || typeof bridge.pickSyncFolder !== "function") throw new Error(SYNC_FOLDER_UNSUPPORTED);
  bridge.pickSyncFolder();
}

/** Hỏi lại trạng thái thư mục đã chọn (dùng khi component vừa mount) — báo về qua cùng CustomEvent trên. */
export function requestAndroidSyncFolderState() {
  const bridge = window.AffiliateReportAndroid;
  if (!bridge || typeof bridge.requestSyncFolderState !== "function") throw new Error(SYNC_FOLDER_UNSUPPORTED);
  bridge.requestSyncFolderState();
}

/** Quét thư mục đã chọn và nhập mọi tệp affiliate_orders*.xlsx vào account này — kết quả báo về qua CustomEvent "affiliate-report-sync-result". */
export function triggerAndroidSync(account: string) {
  const bridge = window.AffiliateReportAndroid;
  if (!bridge || typeof bridge.syncNow !== "function") throw new Error(SYNC_FOLDER_UNSUPPORTED);
  bridge.syncNow(account);
}
