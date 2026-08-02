from __future__ import annotations

from collections import Counter
from io import BytesIO

import pandas as pd
import streamlit as st

from tiktok_affiliate_report.db import get_engine, import_rows, init_db
from tiktok_affiliate_report.parser import DEFAULT_ACCOUNTS, read_xlsx
from tiktok_affiliate_report.reports import daily_report, import_history, monthly_kpi, orders, overview, sheets_output

st.set_page_config(page_title="TikTok Affiliate Report", page_icon="📊", layout="wide")

STATUS_LABELS = {
    "settled": "Đã quyết toán",
    "ineligible": "Không đủ điều kiện",
    "pending": "Chờ xử lý",
    "unknown": "Chưa nhận diện",
}

OVERVIEW_COLUMNS = {
    "account": "Tài khoản",
    "orders": "Số đơn",
    "order_lines": "Dòng đơn",
    "gmv": "Tổng DT",
    "units_sold": "Số lượng bán",
    "units_refunded": "Số lượng hoàn",
    "initial_commission": "Tổng HH ban đầu",
    "cancelled_gmv": "DT huỷ",
    "cancelled_commission": "HH huỷ",
    "actual_gmv": "DT thực tế",
    "actual_commission": "HH thực tế",
    "final_received": "TikTok thực nhận",
}

DAILY_COLUMNS = {
    "day": "Ngày",
    "account": "Tài khoản",
    "orders": "Số đơn",
    "order_lines": "Dòng đơn",
    "gross_gmv": "Tổng DT",
    "units_sold": "Số lượng bán",
    "units_refunded": "Số lượng hoàn",
    "initial_commission": "Tổng HH ban đầu",
    "cancelled_rows": "Dòng huỷ",
    "cancelled_gmv": "DT huỷ",
    "cancelled_commission": "HH huỷ",
    "actual_gmv": "DT thực tế",
    "actual_commission": "HH thực tế",
    "final_received": "TikTok thực nhận",
    "daily_target": "KPI/ngày",
    "target_achievement": "% đạt KPI",
}


def format_integer(value: object) -> str:
    return f"{int(value or 0):,}".replace(",", ".")


def format_vnd(value: object) -> str:
    return f"{format_integer(value)} ₫"


@st.cache_resource
def database():
    engine = get_engine()
    init_db(engine)
    return engine


@st.cache_data(show_spinner=False)
def parse_upload(data: bytes, account: str):
    return read_xlsx(BytesIO(data), account)


engine = database()

st.title("TikTok Affiliate Report")
st.caption("Dashboard local từ các file TikTok export • dữ liệu chỉ lưu trên máy này")

with st.sidebar:
    st.header("Bộ lọc báo cáo")
    accounts = st.pills(
        "Tài khoản affiliate",
        DEFAULT_ACCOUNTS,
        selection_mode="multi",
        default=DEFAULT_ACCOUNTS,
        width="stretch",
    )
    statuses = st.pills(
        "Trạng thái",
        list(STATUS_LABELS),
        selection_mode="multi",
        format_func=STATUS_LABELS.get,
        help="Để trống nghĩa là lấy tất cả trạng thái.",
        width="stretch",
    )
    start = st.date_input("Từ ngày", value=None)
    end = st.date_input("Đến ngày", value=None)

if start and end and start > end:
    st.error("Ngày bắt đầu phải nhỏ hơn hoặc bằng ngày kết thúc.")
    st.stop()

tab_overview, tab_daily, tab_sheets, tab_orders, tab_upload, tab_history = st.tabs(
    ["Tổng quan", "Báo cáo ngày", "Google Sheets output", "Đơn hàng", "Upload", "Lịch sử import"]
)

with tab_upload:
    st.subheader("Import file TikTok .xlsx")
    account = st.selectbox(
        "Chọn affiliate account / workspace label bắt buộc",
        DEFAULT_ACCOUNTS,
        index=None,
        placeholder="Chọn account trước khi import",
    )
    st.caption("File TikTok không chứa affiliate account; hệ thống không suy account từ tên file hoặc tên cửa hàng.")
    uploaded = st.file_uploader("File export TikTok Affiliate", type=["xlsx"])
    if uploaded and uploaded.size > 20 * 1024 * 1024:
        st.error("File vượt giới hạn 20 MB.")
    elif uploaded and not account:
        st.warning("Hãy chọn đúng affiliate account trước khi import.")
    elif uploaded:
        data = uploaded.getvalue()
        try:
            rows = parse_upload(data, account)
            order_dates = [row["Ngày đặt hàng"] for row in rows if row.get("Ngày đặt hàng")]
            status_counts = Counter(row["status"] for row in rows)
            with st.container(horizontal=True):
                st.metric("Dòng hợp lệ", format_integer(len(rows)), border=True, width=220)
                st.metric(
                    "Đơn hàng",
                    format_integer(len({row.get("ID đơn hàng") for row in rows if row.get("ID đơn hàng")})),
                    border=True,
                    width=220,
                )
                st.metric(
                    "Khoảng ngày",
                    f"{min(order_dates):%d/%m/%Y} – {max(order_dates):%d/%m/%Y}" if order_dates else "Không có",
                    border=True,
                    width=320,
                )
            st.caption(
                "Trạng thái: "
                + " • ".join(f"{STATUS_LABELS.get(status, status)} {format_integer(count)}" for status, count in status_counts.items())
            )
            if st.button("Import vào báo cáo", type="primary", icon=":material/upload:"):
                result = import_rows(
                    engine,
                    filename=uploaded.name,
                    file_bytes=data,
                    account=account,
                    rows=rows,
                    uploaded_by_label="Local PC",
                    auth_method="local",
                )
                if result["duplicate"]:
                    st.info("File này đã được import cho account đã chọn; dữ liệu không bị ghi trùng.")
                else:
                    st.success(
                        f"Batch #{result['batch_id']}: thêm {result['inserted']}, cập nhật {result['updated']}, "
                        f"không đổi {result['unchanged']}, lỗi {result['rejected']}."
                    )
                unknown_statuses = sorted({
                    str(row.get("Trạng thái quyết toán đơn hàng") or "(trống)")
                    for row in rows
                    if row["status"] == "unknown"
                })
                if unknown_statuses:
                    st.warning(f"Có status TikTok chưa map: {', '.join(unknown_statuses[:5])}")
                if result.get("rejected_rows"):
                    st.warning("Có dòng bị reject. Kiểm tra số dòng bên dưới.")
                    st.dataframe(result["rejected_rows"], width="stretch", hide_index=True)
        except Exception as exc:
            st.error(f"Không đọc/import được file: {exc}")

with tab_overview:
    st.subheader("Tổng quan theo bộ lọc")
    summary = overview(engine, accounts, start, end, statuses)
    if summary.empty:
        st.info("Chưa có dữ liệu trong bộ lọc. Hãy đổi bộ lọc hoặc mở tab Upload để nhập file TikTok.")
    else:
        total = summary[summary["account"] == "ALL"].iloc[0]
        with st.container(horizontal=True):
            st.metric(
                "Đơn hàng",
                format_integer(total["orders"]),
                help="Số ID đơn hàng duy nhất trong từng tài khoản.",
                border=True,
                width=180,
            )
            st.metric("Số món bán", format_integer(total["units_sold"]), border=True, width=180)
            st.metric("Doanh thu thực tế", format_vnd(total["actual_gmv"]), border=True, width=180)
            st.metric("Hoa hồng thực tế", format_vnd(total["actual_commission"]), border=True, width=180)
            st.metric("Doanh thu huỷ", format_vnd(total["cancelled_gmv"]), border=True, width=180)

        unknown_rows = orders(engine, accounts, start, end, ["unknown"])
        if not unknown_rows.empty:
            st.warning(f"Có {format_integer(len(unknown_rows))} dòng mang trạng thái chưa nhận diện trong phạm vi đang xem.")

        st.markdown("#### So sánh theo account")
        overview_display = summary.rename(columns=OVERVIEW_COLUMNS)
        st.dataframe(
            overview_display,
            width="stretch",
            hide_index=True,
            column_config={
                column: st.column_config.NumberColumn(format="%,d")
                for column in overview_display.columns
                if column != "Tài khoản"
            },
        )

    st.markdown("#### KPI hoa hồng theo tháng")
    kpi = monthly_kpi(engine, accounts, start, end, statuses)
    if kpi.empty:
        st.info("Không có tháng nào trong phạm vi đã chọn.")
    else:
        if set(accounts or DEFAULT_ACCOUNTS) != set(DEFAULT_ACCOUNTS) or statuses:
            st.info("KPI là mục tiêu tổng của ba account; KPI được để trống khi lọc bớt account hoặc trạng thái.")
        kpi_display = kpi.copy()
        kpi_display.insert(
            1,
            "data_status",
            kpi_display["actual_commission"].notna().map({True: "Đã có dữ liệu", False: "Chưa import"}),
        )
        kpi_display["month"] = kpi_display["month"].astype(str).str[:7]
        for column in ("daily_target", "actual_commission", "monthly_target", "gap"):
            kpi_display[column] = kpi_display[column].map(
                lambda value: "—" if pd.isna(value) else format_integer(value)
            )
        kpi_display["target_achievement"] = kpi_display["target_achievement"].map(
            lambda value: "—" if pd.isna(value) else f"{value:.1%}"
        )
        kpi_display = kpi_display.rename(columns={
            "month": "Tháng",
            "data_status": "Dữ liệu",
            "daily_target": "KPI/ngày",
            "actual_commission": "HH thực tế",
            "order_lines": "Dòng đơn",
            "days_in_scope": "Số ngày KPI",
            "monthly_target": "KPI tháng",
            "gap": "Chênh lệch",
            "target_achievement": "% đạt KPI",
        })
        st.dataframe(
            kpi_display,
            width="stretch",
            hide_index=True,
            column_config={
                column: st.column_config.NumberColumn(format="%,d")
                for column in kpi_display.columns
                if column not in {
                    "Tháng", "Dữ liệu", "KPI/ngày", "HH thực tế", "KPI tháng", "Chênh lệch", "% đạt KPI"
                }
            },
        )
        st.caption("Tháng chưa có file import được để trống, không được tính là hoa hồng bằng 0.")

with tab_daily:
    st.subheader("Xu hướng theo ngày")
    df = daily_report(engine, accounts, start, end, statuses)
    if df.empty:
        st.info("Chưa có dữ liệu trong bộ lọc đã chọn.")
    else:
        chart_metrics = {
            "actual_commission": "Hoa hồng thực tế",
            "actual_gmv": "Doanh thu thực tế",
            "units_sold": "Số lượng bán",
        }
        chart_metric = st.segmented_control(
            "Chỉ số trên biểu đồ",
            list(chart_metrics),
            default="actual_commission",
            format_func=chart_metrics.get,
            width="stretch",
        )
        chart_rows = df[df["account"] != "ALL"].sort_values("day")
        st.bar_chart(chart_rows, x="day", y=chart_metric, color="account", width="stretch")
        total_rows = df[df["account"] == "ALL"]
        if not total_rows.empty and total_rows["daily_target"].isna().any():
            st.caption("KPI trống khi tháng chưa được cấu hình hoặc bộ lọc không còn đủ ba account/trạng thái.")
        daily_display = df.rename(columns=DAILY_COLUMNS)
        st.dataframe(
            daily_display,
            width="stretch",
            hide_index=True,
            column_config={
                **{
                    column: st.column_config.NumberColumn(format="%,d")
                    for column in daily_display.columns
                    if column not in {"Ngày", "Tài khoản", "% đạt KPI"}
                },
                "% đạt KPI": st.column_config.NumberColumn(format="percent"),
            },
        )
    st.download_button("Tải CSV báo cáo ngày", df.to_csv(index=False).encode("utf-8-sig"), "daily-report.csv", "text/csv")

with tab_sheets:
    st.subheader("Output Google Sheets")
    st.caption(
        "Bố cục và công thức đã mapping từ REPORT AFF.xlsx; số tiền lấy chính xác từ export hiện hành, "
        "không sao chép các ô legacy đã làm tròn hoặc điều chỉnh thủ công."
    )
    sheet_df = sheets_output(engine, accounts, start, end, statuses)
    if sheet_df.empty:
        st.info("Chưa có dữ liệu trong bộ lọc đã chọn.")
    st.dataframe(
        sheet_df,
        width="stretch",
        hide_index=True,
        column_config={
            **{
                column: st.column_config.NumberColumn(format="%,d")
                for column in sheet_df.columns
                if column not in {"Ngày", "% đạt KPI"}
            },
            "% đạt KPI": st.column_config.NumberColumn(format="percent"),
        },
    )
    st.download_button("Tải CSV cho Google Sheets", sheet_df.to_csv(index=False).encode("utf-8-sig"), "google-sheets-output.csv", "text/csv")

with tab_orders:
    st.subheader("Đơn hàng hiện tại")
    search = st.text_input("Tìm ID đơn hàng, SKU, sản phẩm hoặc cửa hàng")
    order_df = orders(engine, accounts, start, end, statuses, search)
    visible_orders = order_df.head(1000)
    if len(order_df) > len(visible_orders):
        st.caption(
            f"Đang hiển thị {format_integer(len(visible_orders))}/{format_integer(len(order_df))} dòng để giao diện nhẹ; file CSV chứa đầy đủ."
        )
    else:
        st.caption(f"{format_integer(len(order_df))} dòng phù hợp.")
    order_display = visible_orders.rename(columns={
        "account": "Tài khoản",
        "order_id": "ID đơn hàng",
        "sku_id": "ID SKU",
        "product_name": "Sản phẩm",
        "shop_name": "Cửa hàng",
        "status": "Trạng thái",
        "order_date": "Ngày đặt hàng",
        "gmv": "GMV",
        "units_sold": "Số lượng bán",
        "units_refunded": "Số lượng hoàn",
        "estimated_commission": "HH ban đầu",
        "final_received": "TikTok thực nhận",
        "version": "Phiên bản",
        "created_at": "Ngày import",
    })
    order_display["Trạng thái"] = order_display["Trạng thái"].map(STATUS_LABELS).fillna(order_display["Trạng thái"])
    st.dataframe(
        order_display,
        width="stretch",
        hide_index=True,
        column_config={
            column: st.column_config.NumberColumn(format="%,d")
            for column in ("GMV", "Số lượng bán", "Số lượng hoàn", "HH ban đầu", "TikTok thực nhận", "Phiên bản")
        },
    )
    st.download_button("Tải CSV đơn hàng đầy đủ", order_df.to_csv(index=False).encode("utf-8-sig"), "orders.csv", "text/csv")

with tab_history:
    st.subheader("Lịch sử import")
    history = import_history(engine)
    if history.empty:
        st.info("Chưa có batch import nào.")
    history_display = history.rename(columns={
        "id": "Batch",
        "file_sha": "SHA-256",
        "filename": "Tên file",
        "account": "Tài khoản",
        "uploaded_by_label": "Nguồn upload",
        "auth_method": "Chế độ",
        "auth_subject": "Định danh",
        "inserted": "Thêm",
        "updated": "Cập nhật",
        "unchanged": "Không đổi",
        "rejected": "Lỗi",
        "created_at": "Thời gian",
    })
    st.dataframe(history_display, width="stretch", hide_index=True)
