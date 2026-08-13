import type { DataQuality } from "@/lib/api";

/**
 * Nguồn duy nhất cho câu hỏi "dữ liệu có bao nhiêu vấn đề".
 *
 * Trước đây trang Phân tích và trang Tổng quan mỗi nơi tự cộng một công thức riêng, còn tab
 * Chất lượng dữ liệu lại liệt kê một danh sách khác — nên con số ở đầu trang không bao giờ
 * bằng tổng các mục bên dưới. Gom về một chỗ để chúng không thể lệch nhau nữa.
 */
export type QualityIssue = {
  label: string;
  value: number;
  help: string;
};

/**
 * Đơn CHƯA quyết toán không phải là vấn đề.
 *
 * TikTok để trống ngày quyết toán cho mọi đơn chưa được trả tiền — đó là đúng thiết kế, không
 * phải dữ liệu bẩn. Đếm chúng là "vấn đề" biến mọi đơn đang chờ thành lỗi, và trên dữ liệu
 * thật nó chiếm gần hết con số cảnh báo. Dấu hiệu bất thường thật là đơn ĐÃ quyết toán mà vẫn
 * thiếu ngày — tức `settled_missing_settlement_rows`.
 */
export function qualityIssues(quality: DataQuality): QualityIssue[] {
  return [
    { label: "Trạng thái chưa xác định", value: quality.unknown_status_rows, help: "Trạng thái TikTok trả về chưa có trong bảng quy đổi." },
    { label: "Không phải VND", value: quality.non_vnd_rows, help: "Tách riêng trước khi cộng vào báo cáo VND." },
    { label: "Thiếu ngày đơn", value: quality.missing_order_date_rows, help: "Không xếp được vào kỳ báo cáo nào." },
    { label: "Đã quyết toán nhưng thiếu ngày", value: quality.settled_missing_settlement_rows, help: "Trạng thái và ngày không khớp nhau." },
    { label: "Độ trễ quyết toán âm", value: quality.negative_settlement_lag_rows, help: "Ngày quyết toán trước ngày đặt đơn." },
  ];
}

export function qualityIssueCount(quality: DataQuality): number {
  return qualityIssues(quality).reduce((tong, issue) => tong + issue.value, 0);
}

/**
 * Dòng bị từ chối khi nhập KHÔNG thuộc về kỳ nào.
 *
 * Chúng chưa bao giờ phân tích được nên không có ngày đặt đơn để xếp vào phạm vi đang xem, và
 * import_batches.created_at là lúc nhập tệp — khác trục với bộ lọc ngày trên trang. Vì vậy đây
 * là con số toàn thời gian, phải hiện riêng kèm nhãn rõ ràng thay vì cộng vào chỉ số theo kỳ.
 */
export function rejectedAllTime(quality: DataQuality): number {
  return quality.import_rejected;
}
