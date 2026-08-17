"use client";

import { Tabs as RadixTabs } from "radix-ui";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/cn";
import styles from "./styles.module.css";

export function SegmentedControl({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="segmented-control" className={cn(styles.segmented, className)} role="group" {...props} />;
}

export const TabsRoot = RadixTabs.Root;

export function TabsList({ className, ...props }: ComponentProps<typeof RadixTabs.List>) {
  return <RadixTabs.List data-slot="tabs-list" className={cn(styles.tabsList, className)} {...props} />;
}

export function TabsTrigger({ className, children, ...props }: ComponentProps<typeof RadixTabs.Trigger> & { children: ReactNode }) {
  return <RadixTabs.Trigger data-slot="tabs-trigger" className={cn(styles.tabsTrigger, className)} {...props}>{children}</RadixTabs.Trigger>;
}

export function TabsContent({ className, ...props }: ComponentProps<typeof RadixTabs.Content>) {
  return <RadixTabs.Content data-slot="tabs-content" className={cn(styles.tabsContent, className)} {...props} />;
}
