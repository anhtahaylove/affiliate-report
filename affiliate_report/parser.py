from __future__ import annotations

import hashlib
import json
import re
import warnings
from datetime import datetime
from typing import Any

import pandas as pd

EXPECTED_HEADERS = [
    "ID đơn hàng", "ID SKU", "Tên sản phẩm", "ID sản phẩm", "Giá", "Số món bán ra",
    "Số món đã hoàn tiền", "Tên cửa hàng", "Mã cửa hàng", "Đối tác liên kết", "Agency",
    "Đơn vị tiền tệ", "Loại đơn hàng", "Trạng thái quyết toán đơn hàng", "Gián tiếp",
    "Loại hoa hồng", "Loại nội dung", "Id nội dung", "Tiêu chuẩn", "Quảng cáo cửa hàng",
    "TikTok thưởng", "Đối tác thưởng", "Phần chia doanh thu", "GMV", "Cơ sở hoa hồng ước tính",
    "Hoa hồng tiêu chuẩn ước tính", "Hoa hồng Quảng cáo cửa hàng ước tính", "Thưởng ước tính",
    "Thưởng ước tính của đối tác liên kết", "IVA ước tính", "ISR ước tính", "Est. CedularTax",
    "PIT ước tính", "Ước tính phần chia doanh thu", "Cơ sở hoa hồng thực tế", "Hoa hồng tiêu chuẩn",
    "Hoa hồng Quảng cáo cửa hàng", "Thưởng", "Thưởng của đối tác liên kết", "Thuế - ISR",
    "Thuế - IVA", "cedular_tax", "Thuế - PIT", "Đã chia sẻ với đối tác",
    "Tổng số tiền nhận được cuối cùng", "Ngày đặt hàng", "Ngày quyết toán hoa hồng",
]

MAX_IMPORT_ROWS = 50_000
ID_FIELDS = {"ID đơn hàng", "ID SKU", "ID sản phẩm", "Mã cửa hàng", "Id nội dung"}
INT_FIELDS = {
    "Giá", "Số món bán ra", "Số món đã hoàn tiền", "Tiêu chuẩn", "Quảng cáo cửa hàng", "TikTok thưởng",
    "Đối tác thưởng", "Phần chia doanh thu", "GMV", "Cơ sở hoa hồng ước tính",
    "Hoa hồng tiêu chuẩn ước tính", "Hoa hồng Quảng cáo cửa hàng ước tính", "Thưởng ước tính",
    "Thưởng ước tính của đối tác liên kết", "IVA ước tính", "ISR ước tính", "Est. CedularTax",
    "PIT ước tính", "Ước tính phần chia doanh thu", "Cơ sở hoa hồng thực tế", "Hoa hồng tiêu chuẩn",
    "Hoa hồng Quảng cáo cửa hàng", "Thưởng", "Thưởng của đối tác liên kết", "Thuế - ISR",
    "Thuế - IVA", "cedular_tax", "Thuế - PIT", "Đã chia sẻ với đối tác",
    "Tổng số tiền nhận được cuối cùng",
}
DATE_FIELDS = {"Ngày đặt hàng", "Ngày quyết toán hoa hồng"}
COMMISSION_EST_FIELDS = [
    "Hoa hồng tiêu chuẩn ước tính",
    "Hoa hồng Quảng cáo cửa hàng ước tính",
    "Thưởng ước tính",
    "Thưởng ước tính của đối tác liên kết",
    "Ước tính phần chia doanh thu",
]

STATUS_MAP = {
    "đã quyết toán": "settled",
    "da quyet toan": "settled",
    "settled": "settled",
    "không đủ điều kiện": "ineligible",
    "khong du dieu kien": "ineligible",
    "đã hủy": "ineligible",
    "da huy": "ineligible",
    "ineligible": "ineligible",
    "đang chờ": "pending",
    "dang cho": "pending",
    "pending": "pending",
    "chờ xử lý": "pending",
    "cho xu ly": "pending",
    "chờ thanh toán": "pending",
    "cho thanh toan": "pending",
    "awaiting payment": "pending",
    "awaitingpayment": "pending",
}


# Tên tệp export TikTok luôn ở dạng affiliate_orders<phần đuôi đổi mỗi lần xuất>.xlsx (vd.
# affiliate_orders_7674048855708600085.xlsx). Thư mục Download trên điện thoại lẫn cả tệp không
# liên quan (ảnh, tệp app khác) — lọc theo tiền tố này ở MỌI điểm nhận tệp (upload tay, ghép cặp
# điện thoại) để bắt sớm khi người dùng chọn nhầm tệp, báo rõ lý do thay vì im lặng bỏ qua.
FILENAME_PATTERN = re.compile(r"^affiliate_orders.*\.xlsx$", re.IGNORECASE)
FILENAME_REJECT_MESSAGE = (
    'Chỉ nhận tệp export TikTok dạng .xlsx có tên bắt đầu bằng "affiliate_orders" '
    "(vd. affiliate_orders_1234567890.xlsx)."
)


def is_valid_export_filename(filename: str) -> bool:
    return bool(FILENAME_PATTERN.match((filename or "").strip()))


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def nullish(value: Any) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() in {"", "/"}


def parse_int(value: Any) -> int | None:
    if nullish(value):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip().replace("₫", "").replace("VND", "").replace(",", "")
    sign = -1 if text.startswith("-") else 1
    digits = re.sub(r"\D", "", text)
    return sign * int(digits) if digits else None


def parse_date(value: Any, field: str | None = None) -> datetime | None:
    if nullish(value):
        return None
    if isinstance(value, datetime):
        return value.replace(microsecond=0)
    text = str(value).strip()
    try:
        return datetime.strptime(text, "%d/%m/%Y %H:%M:%S")
    except ValueError as exc:
        label = f"{field}: " if field else ""
        raise ValueError(f"{label}ngày {text!r} không đúng định dạng dd/mm/yyyy hh:mm:ss") from exc


def normalize_status(value: Any) -> str:
    if nullish(value):
        return "unknown"
    text = str(value).strip().lower()
    return STATUS_MAP.get(text, "unknown")


def normalize_row(row: dict[str, Any], account: str) -> dict[str, Any]:
    account = account.strip().upper()
    if not account:
        raise ValueError("Affiliate account không được để trống")
    out: dict[str, Any] = {"account": account}
    for header in EXPECTED_HEADERS:
        value = row.get(header)
        if header in ID_FIELDS:
            out[header] = None if nullish(value) else str(value).strip()
        elif header in INT_FIELDS:
            out[header] = parse_int(value)
        elif header in DATE_FIELDS:
            out[header] = parse_date(value, header)
        else:
            out[header] = None if nullish(value) else str(value).strip()
    out["status"] = normalize_status(out["Trạng thái quyết toán đơn hàng"])
    if not out["ID đơn hàng"] or not out["ID SKU"]:
        raise ValueError("Thiếu ID đơn hàng hoặc ID SKU")
    out["estimated_commission"] = sum(out.get(field) or 0 for field in COMMISSION_EST_FIELDS)
    out["gmv"] = out.get("GMV") or 0
    out["units_sold"] = out.get("Số món bán ra") or 0
    out["units_refunded"] = out.get("Số món đã hoàn tiền") or 0
    out["final_received"] = out.get("Tổng số tiền nhận được cuối cùng")
    out["product_id"] = out.get("ID sản phẩm")
    out["shop_id"] = out.get("Mã cửa hàng")
    out["shop_name"] = out.get("Tên cửa hàng")
    out["content_type"] = out.get("Loại nội dung")
    out["content_id"] = out.get("Id nội dung")
    out["order_type"] = out.get("Loại đơn hàng")
    out["commission_type"] = out.get("Loại hoa hồng")
    out["currency"] = out.get("Đơn vị tiền tệ")
    out["business_key"] = f"{account}|{out.get('ID đơn hàng') or ''}|{out.get('ID SKU') or ''}"
    out["normalized_hash"] = hashlib.sha256(
        json.dumps(out, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return out


def read_xlsx(path_or_buffer: Any, account: str) -> list[dict[str, Any]]:
    """Đọc file export TikTok. Dòng hỏng trả về dưới dạng `{"_rejected": {...}}` để phần còn
    lại của file vẫn được nhập; chỉ file thiếu cột hoặc quá dài mới bị từ chối toàn bộ."""
    df = pd.read_excel(path_or_buffer, dtype=str, keep_default_na=False)
    if len(df) > MAX_IMPORT_ROWS:
        raise ValueError(f"File có {len(df):,} dòng, vượt giới hạn {MAX_IMPORT_ROWS:,} dòng")
    headers = list(df.columns)
    missing = [h for h in EXPECTED_HEADERS if h not in headers]
    if missing:
        raise ValueError(f"Export phải có đủ 47 cột TikTok. Thiếu={missing}")
    unknown = [h for h in headers if h not in EXPECTED_HEADERS]
    if unknown:
        warnings.warn(f"Bỏ qua {len(unknown)} cột lạ ngoài 47 cột TikTok: {unknown}", stacklevel=2)
    rows = []
    for offset, row in enumerate(df.to_dict(orient="records")):
        row_number = offset + 2  # dòng 1 của file Excel là header
        try:
            normalized = normalize_row(row, account)
        except ValueError as exc:
            rows.append({"_row_number": row_number, "_rejected": {"row_number": row_number, "reason": str(exc)}})
            continue
        normalized["_raw"] = row
        normalized["_row_number"] = row_number
        rows.append(normalized)
    return rows
