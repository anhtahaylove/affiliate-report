"use client";

import { ChevronDown } from "lucide-react";
import { useId, type ComponentProps, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import styles from "./styles.module.css";

export function Field({
  label,
  hint,
  error,
  optional = false,
  className,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  optional?: boolean;
  className?: string;
  children: (props: { id: string; describedBy?: string; invalid: boolean }) => ReactNode;
}) {
  const id = useId();
  const messageId = hint || error ? `${id}-message` : undefined;
  return (
    <div data-slot="field" className={cn(styles.field, className)} data-invalid={Boolean(error) || undefined}>
      <label className={styles.fieldLabel} htmlFor={id}>
        {label}
        {optional ? <span>Tuỳ chọn</span> : null}
      </label>
      {children({ id, describedBy: messageId, invalid: Boolean(error) })}
      {error || hint ? (
        <small id={messageId} className={error ? styles.fieldError : styles.fieldHint} aria-live={error ? "polite" : undefined}>
          {error || hint}
        </small>
      ) : null}
    </div>
  );
}

export function TextInput({ className, ...props }: ComponentProps<"input">) {
  return <input data-slot="input" className={cn(styles.control, className)} {...props} />;
}

export function TextArea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea data-slot="textarea" className={cn(styles.control, styles.textarea, className)} {...props} />;
}

export function NativeSelect({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <span className={styles.selectWrap}>
      <select data-slot="select" className={cn(styles.control, styles.select, className)} {...props}>{children}</select>
      <ChevronDown size={16} aria-hidden="true" />
    </span>
  );
}
