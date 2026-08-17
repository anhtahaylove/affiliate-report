import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";
import styles from "./styles.module.css";

export function PageHeader({ title, description, meta, actions, className }: { title: string; description?: string; meta?: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <div data-slot="page-header" className={cn(styles.pageHeader, "page-heading", className)}>
      <div className={styles.pageTitle}>
        <h1>{title}</h1>
        {description ? <p className="subtle">{description}</p> : null}
      </div>
      {meta ? <div className={styles.pageMeta}>{meta}</div> : null}
      {actions ? <div className={styles.pageActions}>{actions}</div> : null}
    </div>
  );
}

export function Surface({ className, children, ...props }: HTMLAttributes<HTMLElement> & { children: ReactNode }) {
  return <section data-slot="surface" className={cn(styles.surface, className)} {...props}>{children}</section>;
}

export function ScopeBar({ summary, controls, actions, className }: { summary: ReactNode; controls?: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <section data-slot="scope-bar" className={cn(styles.scopeBar, className)} aria-label="Phạm vi báo cáo">
      <div className={styles.scopeSummary}>{summary}</div>
      {controls ? <div className={styles.scopeControls}>{controls}</div> : null}
      {actions ? <div className={styles.scopeActions}>{actions}</div> : null}
    </section>
  );
}
