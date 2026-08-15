"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { ReactNode, type RefObject } from "react";

export function BottomSheet({ open, onOpenChange, title, description, restoreFocusRef, children }: { open: boolean; onOpenChange: (open: boolean) => void; title: string; description?: string; restoreFocusRef?: RefObject<HTMLElement | null>; children: ReactNode }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="sheet-overlay" />
        <Dialog.Content
          className="bottom-sheet"
          aria-describedby={description ? undefined : undefined}
          onCloseAutoFocus={(event) => {
            if (!restoreFocusRef?.current) return;
            event.preventDefault();
            restoreFocusRef.current.focus();
          }}
        >
          <div className="sheet-grabber" aria-hidden="true" />
          <div className="sheet-header">
            <div>
              <Dialog.Title>{title}</Dialog.Title>
              {description ? <Dialog.Description>{description}</Dialog.Description> : null}
            </div>
            <Dialog.Close className="sheet-close" aria-label="Đóng">
              <X size={18} aria-hidden="true" />
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
