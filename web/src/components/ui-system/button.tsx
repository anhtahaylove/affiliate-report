"use client";

import { Slot } from "@radix-ui/react-slot";
import { LoaderCircle } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";
import styles from "./styles.module.css";

export type ButtonTone = "primary" | "secondary" | "quiet" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

export function Button({
  asChild = false,
  tone = "secondary",
  size = "md",
  loading = false,
  leading,
  trailing,
  className,
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  asChild?: boolean;
  tone?: ButtonTone;
  size?: ButtonSize;
  loading?: boolean;
  leading?: ReactNode;
  trailing?: ReactNode;
}) {
  const Component = asChild ? Slot : "button";
  return (
    <Component
      data-slot="button"
      data-tone={tone}
      data-size={size}
      aria-busy={loading || undefined}
      className={cn(styles.button, className)}
      disabled={asChild ? undefined : disabled || loading}
      {...props}
    >
      {loading ? <LoaderCircle className={styles.spinner} size={17} aria-hidden="true" /> : leading}
      <span>{children}</span>
      {trailing}
    </Component>
  );
}

export function IconButton({
  label,
  tone = "quiet",
  size = "md",
  className,
  children,
  ...props
}: Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
  label: string;
  tone?: ButtonTone;
  size?: ButtonSize;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      data-slot="icon-button"
      data-tone={tone}
      data-size={size}
      className={cn(styles.button, styles.iconButton, className)}
      aria-label={label}
      title={label}
      {...props}
    >
      {children}
    </button>
  );
}
