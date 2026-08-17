import { AlertCircle, CheckCircle2, Info, TriangleAlert, type LucideIcon } from "lucide-react";
import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";
import styles from "./styles.module.css";

export type SemanticTone = "neutral" | "info" | "success" | "warning" | "danger";

const alertIcons: Record<Exclude<SemanticTone, "neutral">, LucideIcon> = {
  info: Info,
  success: CheckCircle2,
  warning: TriangleAlert,
  danger: AlertCircle,
};

export function Badge({ tone = "neutral", className, children, ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: SemanticTone }) {
  return <span data-slot="badge" data-tone={tone} className={cn(styles.badge, className)} {...props}>{children}</span>;
}

export function Alert({
  tone = "info",
  title,
  children,
  actions,
  className,
}: {
  tone?: Exclude<SemanticTone, "neutral">;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  const Icon = alertIcons[tone];
  return (
    <section data-slot="alert" data-tone={tone} className={cn(styles.alert, className)} role={tone === "danger" ? "alert" : "status"}>
      <Icon size={19} aria-hidden="true" />
      <div><strong>{title}</strong>{children ? <div className={styles.alertBody}>{children}</div> : null}</div>
      {actions ? <div className={styles.alertActions}>{actions}</div> : null}
    </section>
  );
}

export function Progress({ value, label, detail, className }: { value: number; label: string; detail?: string; className?: string }) {
  const safeValue = Math.min(100, Math.max(0, value));
  return (
    <div data-slot="progress" className={cn(styles.progress, className)}>
      <div className={styles.progressLabel}><span>{label}</span><strong>{detail ?? `${Math.round(safeValue)}%`}</strong></div>
      <div className={styles.progressTrack} role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={safeValue}>
        <span style={{ width: `${safeValue}%` }} />
      </div>
    </div>
  );
}

export function EmptyState({ icon: Icon = Info, title, description, action, className }: { icon?: LucideIcon; title: string; description?: string; action?: ReactNode; className?: string }) {
  return (
    <section data-slot="empty-state" className={cn(styles.state, className)}>
      <span className={styles.stateIcon}><Icon size={21} aria-hidden="true" /></span>
      <div><h2>{title}</h2>{description ? <p>{description}</p> : null}</div>
      {action}
    </section>
  );
}

export function ErrorState({ title, description, action, className }: { title: string; description?: string; action?: ReactNode; className?: string }) {
  return <EmptyState icon={AlertCircle} title={title} description={description} action={action} className={cn(styles.errorState, className)} />;
}

export function LoadingState({ label, rows = 3, className }: { label: string; rows?: number; className?: string }) {
  return (
    <div data-slot="loading-state" className={cn(styles.loading, className)} role="status" aria-busy="true" aria-label={label}>
      {Array.from({ length: rows }, (_, index) => <span key={index} className={styles.skeleton} />)}
      <span className="sr-only">{label}</span>
    </div>
  );
}
