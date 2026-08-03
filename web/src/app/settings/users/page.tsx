import { Suspense } from "react";
import { OperationsPage } from "@/components/operations-page";

export default function Page() {
  return (
    <Suspense fallback={<main className="auth-shell"><section className="auth-card panel"><h1>Đang tải…</h1></section></main>}>
      <OperationsPage route="users" />
    </Suspense>
  );
}
