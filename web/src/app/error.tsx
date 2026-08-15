"use client";

export default function Error({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="auth-shell">
      <section className="auth-card panel" role="alert">
        <div className="brand-badge">AFF</div>
        <h1>Không thể hiển thị trang</h1>
        {/* error.message gần như luôn là lỗi JS/React chưa lường trước (mọi lỗi API đã được các
            trang tự bắt và dịch tiếng Việt riêng) — không hiện thẳng câu tiếng Anh/kỹ thuật đó
            cho người dùng không chuyên, luôn dùng câu cố định dễ hiểu. */}
        <p>Đã xảy ra lỗi ngoài dự kiến. Hãy thử tải lại; nếu vẫn còn lỗi, đóng và mở lại ứng dụng.</p>
        <button className="primary" type="button" onClick={reset}>Thử lại</button>
      </section>
    </main>
  );
}
