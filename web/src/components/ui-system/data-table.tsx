import type { TableHTMLAttributes } from "react";
import { cn } from "@/lib/cn";
import styles from "./styles.module.css";

export function DataTable({ className, ...props }: TableHTMLAttributes<HTMLTableElement>) {
  return <div data-slot="data-table" className={styles.tableWrap}><table className={cn(styles.table, className)} {...props} /></div>;
}
