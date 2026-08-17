"use client";

import { Dialog, DropdownMenu, Toast, Tooltip } from "radix-ui";
import { X } from "lucide-react";
import type { ComponentProps, ReactNode, RefObject } from "react";
import { cn } from "@/lib/cn";
import styles from "./styles.module.css";

export function AppDialog({ open, onOpenChange, title, description, children, footer, className }: { open: boolean; onOpenChange: (open: boolean) => void; title: string; description?: string; children: ReactNode; footer?: ReactNode; className?: string }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className={styles.overlay} />
        <Dialog.Content className={cn(styles.dialog, className)}>
          <div className={styles.dialogHeader}>
            <div><Dialog.Title>{title}</Dialog.Title>{description ? <Dialog.Description>{description}</Dialog.Description> : null}</div>
            <Dialog.Close className={styles.closeButton} aria-label="Đóng"><X size={18} aria-hidden="true" /></Dialog.Close>
          </div>
          <div className={styles.dialogBody}>{children}</div>
          {footer ? <div className={styles.dialogFooter}>{footer}</div> : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function Sheet({ open, onOpenChange, title, description, children, restoreFocusRef, className }: { open: boolean; onOpenChange: (open: boolean) => void; title: string; description?: string; children: ReactNode; restoreFocusRef?: RefObject<HTMLElement | null>; className?: string }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className={styles.overlay} />
        <Dialog.Content
          className={cn(styles.sheet, className)}
          onCloseAutoFocus={(event) => {
            if (!restoreFocusRef?.current) return;
            event.preventDefault();
            restoreFocusRef.current.focus();
          }}
        >
          <div className={styles.sheetGrabber} aria-hidden="true" />
          <div className={styles.dialogHeader}>
            <div><Dialog.Title>{title}</Dialog.Title>{description ? <Dialog.Description>{description}</Dialog.Description> : null}</div>
            <Dialog.Close className={styles.closeButton} aria-label="Đóng"><X size={18} aria-hidden="true" /></Dialog.Close>
          </div>
          <div className={styles.dialogBody}>{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function AppTooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Tooltip.Provider delayDuration={500}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
        <Tooltip.Portal><Tooltip.Content className={styles.tooltip} sideOffset={7}>{label}<Tooltip.Arrow className={styles.tooltipArrow} /></Tooltip.Content></Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}

export const MenuRoot = DropdownMenu.Root;
export const MenuTrigger = DropdownMenu.Trigger;

export function MenuContent({ className, children, ...props }: ComponentProps<typeof DropdownMenu.Content>) {
  return <DropdownMenu.Portal><DropdownMenu.Content className={cn(styles.menu, className)} sideOffset={7} {...props}>{children}</DropdownMenu.Content></DropdownMenu.Portal>;
}

export function MenuItem({ className, ...props }: ComponentProps<typeof DropdownMenu.Item>) {
  return <DropdownMenu.Item className={cn(styles.menuItem, className)} {...props} />;
}

export const ToastProvider = Toast.Provider;

export function ToastViewport() {
  return <Toast.Viewport className={styles.toastViewport} aria-label="Thông báo" />;
}

export function ToastMessage({ open, onOpenChange, title, description, action }: { open: boolean; onOpenChange: (open: boolean) => void; title: string; description?: string; action?: ReactNode }) {
  return (
    <Toast.Root className={styles.toast} open={open} onOpenChange={onOpenChange}>
      <div><Toast.Title className={styles.toastTitle}>{title}</Toast.Title>{description ? <Toast.Description className={styles.toastDescription}>{description}</Toast.Description> : null}</div>
      {action}
      <Toast.Close className={styles.closeButton} aria-label="Đóng thông báo"><X size={17} aria-hidden="true" /></Toast.Close>
    </Toast.Root>
  );
}
