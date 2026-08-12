"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CapabilityState, UpdateStatus, checkUpdate } from "@/lib/api";
import { Download, X } from "lucide-react";

const DISMISS_KEY = "tiktok-affiliate-update-postponed";

/**
 * Kiểm tra đúng một lần cho mỗi lần mở ứng dụng. Biến ở tầng module nên chuyển trang qua lại
 * không gọi lại feed công khai; tải lại trang mới là một lần mở mới.
 */
let sessionCheck: Promise<UpdateStatus | null> | null = null;

function checkOnce(): Promise<UpdateStatus | null> {
  if (!sessionCheck) sessionCheck = checkUpdate().catch(() => null);
  return sessionCheck;
}

/** Cho phép bỏ qua trạng thái đã hoãn sau khi cài xong, để lần sau còn nhắc lại. */
export function forgetPostponedUpdate() {
  sessionCheck = null;
  try {
    window.localStorage.removeItem(DISMISS_KEY);
  } catch {
    // Trình duyệt chặn localStorage thì thôi, đây chỉ là tiện ích nhắc việc.
  }
}

/**
 * Trước đây chỉ trang Cài đặt > Cập nhật mới biết có bản mới, nên người dùng phải tự nhớ đi tìm.
 * Banner này hiện ở mọi trang ngay khi mở ứng dụng, và hoãn thì im cho tới khi có bản mới hơn.
 */
export function UpdateBanner({ capability, onUpdatePage }: { capability: CapabilityState; onUpdatePage: boolean }) {
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [postponed, setPostponed] = useState(true);

  useEffect(() => {
    if (!capability.available || onUpdatePage) return;
    let active = true;
    void checkOnce().then((result) => {
      if (!active || !result?.available) return;
      setStatus(result);
      let stored: string | null = null;
      try {
        stored = window.localStorage.getItem(DISMISS_KEY);
      } catch {
        stored = null;
      }
      setPostponed(stored === result.latest_version);
    });
    return () => {
      active = false;
    };
  }, [capability.available, onUpdatePage]);

  if (!status || postponed) return null;

  function postpone() {
    try {
      window.localStorage.setItem(DISMISS_KEY, status?.latest_version ?? "");
    } catch {
      // Không lưu được thì banner sẽ hiện lại ở lần mở sau; vẫn tốt hơn là chặn thao tác.
    }
    setPostponed(true);
  }

  return (
    <section className="update-banner" role="status">
      <Download size={18} aria-hidden="true" />
      <p>
        <strong>Có bản {status.latest_version}</strong>
        <span>
          {status.installable
            ? `Bạn đang dùng bản ${status.current_version}. Cài ngay trong ứng dụng, dữ liệu giữ nguyên.`
            : `Bạn đang dùng bản ${status.current_version}. Bản này cần cài thủ công.`}
        </span>
      </p>
      <Link className="button-link" href={status.installable ? "/settings/update#install" : "/settings/update"}>
        {status.installable ? "Cập nhật ngay" : "Xem chi tiết"}
      </Link>
      <button type="button" className="update-banner-dismiss" onClick={postpone} aria-label={`Để sau, không nhắc lại bản ${status.latest_version}`}>
        <X size={16} aria-hidden="true" />
        Để sau
      </button>
    </section>
  );
}
