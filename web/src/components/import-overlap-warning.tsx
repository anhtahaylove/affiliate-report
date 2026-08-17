import { AlertTriangle } from "lucide-react";
import type { ImportWarning } from "@/lib/api";
import { integer, percent } from "@/lib/format";
import styles from "@/components/pages/imports.module.css";

export function ImportOverlapWarning({
  warnings,
  footer = "File vẫn được nhập để không làm mất dữ liệu. Hãy kiểm tra lại account trước khi dùng báo cáo tổng.",
}: {
  warnings: ImportWarning[];
  footer?: string;
}) {
  if (!warnings.length) return null;

  return (
    <aside className={`${styles.overlapWarning} import-overlap-warning`} role="alert" aria-label="Cảnh báo trùng dữ liệu giữa các tài khoản">
      <div className={styles.overlapHeading}>
        <AlertTriangle size={19} aria-hidden="true" />
        <div>
          <strong>Cảnh báo dữ liệu có thể bị gắn nhầm tài khoản</strong>
          <span>Order + SKU của tệp này trùng bất thường với dữ liệu đã có.</span>
        </div>
      </div>
      <ul className={styles.overlapList}>
        {warnings.map((warning, index) => (
          <li key={`${warning.code}-${warning.other_account ?? index}`}>
            <div>
              <strong>{warning.other_account ?? "Tài khoản khác"}</strong>
              {warning.overlap_count != null && warning.incoming_count != null
                ? <span>{integer.format(warning.overlap_count)}/{integer.format(warning.incoming_count)} dòng trùng</span>
                : null}
            </div>
            {warning.overlap_ratio != null ? <span className={styles.overlapRatio}>{percent(warning.overlap_ratio)}</span> : null}
            <p>{warning.message}</p>
          </li>
        ))}
      </ul>
      <p className={styles.overlapFooter}>{footer}</p>
    </aside>
  );
}
