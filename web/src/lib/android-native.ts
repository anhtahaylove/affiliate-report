type AffiliateReportAndroidBridge = {
  download: (url: string, filename: string, mimeType: string) => void;
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
