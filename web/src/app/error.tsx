"use client";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="auth-shell">
      <section className="auth-card panel" role="alert">
        <div className="brand-badge">AFF</div>
        <h1>Không thể hiển thị trang</h1>
        <p>{error.message || "Đã xảy ra lỗi khi tải Operations Cockpit."}</p>
        <button className="primary" type="button" onClick={reset}>Thử lại</button>
      </section>
    </main>
  );
}
