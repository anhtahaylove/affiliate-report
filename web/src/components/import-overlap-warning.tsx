import type { ImportWarning } from "@/lib/api";

export function ImportOverlapWarning({
  warnings,
  footer = "File vẫn được nhập để không làm mất dữ liệu. Hãy kiểm tra lại account trước khi dùng báo cáo tổng.",
}: {
  warnings: ImportWarning[];
  footer?: string;
}) {
  if (!warnings.length) return null;

  return (
    <div className="import-overlap-warning" role="alert">
      <strong>Cảnh báo dữ liệu có thể bị gắn nhầm tài khoản</strong>
      <ul>
        {warnings.map((warning, index) => (
          <li key={`${warning.code}-${warning.other_account ?? index}`}>{warning.message}</li>
        ))}
      </ul>
      <span>{footer}</span>
    </div>
  );
}
