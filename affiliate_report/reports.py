from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from statistics import median
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import func, or_, select
from sqlalchemy.engine import Engine

from .db import accounts as account_registry
from .db import import_batches, monthly_targets, order_line_versions


MONTHLY_KPI_COLUMNS = [
    "month", "account", "daily_target", "days_in_scope", "monthly_target",
    "actual_commission", "gap", "target_achievement",
    # "Hiệu suất gộp": hoa hồng ước tính kể cả đơn Không đủ điều kiện — cho thấy sức bán thật sự,
    # KHÔNG dùng để quyết định đã đạt mục tiêu (đơn ineligible sẽ không được TikTok trả tiền).
    "combined_commission", "combined_gap", "combined_target_achievement", "ineligible_commission", "ineligible_rate",
    "order_lines",
]


def _active_account_codes(engine: Engine) -> list[str]:
    stmt = (
        select(account_registry.c.code)
        .where(account_registry.c.active.is_(True))
        .order_by(account_registry.c.display_order, account_registry.c.code)
    )
    with engine.connect() as conn:
        return [str(code) for code in conn.execute(stmt).scalars()]


# Report/analytics không bao giờ đọc raw_json (blob JSON gốc 47 cột mỗi dòng) hay các cột
# hạ tầng; giữ chúng ngoài truy vấn để một lần mở dashboard không kéo cả bảng về pandas.
NON_REPORT_COLUMNS = {"business_key", "normalized_hash", "raw_json", "is_current", "batch_id"}
REPORT_COLUMNS = [column for column in order_line_versions.c if column.name not in NON_REPORT_COLUMNS]
SEARCH_COLUMNS = (
    order_line_versions.c.order_id,
    order_line_versions.c.sku_id,
    order_line_versions.c.product_name,
    order_line_versions.c.shop_name,
)


def _like_needle(search: str) -> str:
    """Tìm kiếm là so khớp chuỗi nguyên văn, nên %, _ và \\ phải được thoát trước khi vào LIKE."""
    escaped = str(search).strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _current_filters(accounts=None, start=None, end=None, statuses=None, search=None) -> list:
    clauses = [order_line_versions.c.is_current.is_(True)]
    if accounts is not None:
        clauses.append(order_line_versions.c.account.in_(accounts))
    if statuses:
        clauses.append(order_line_versions.c.status.in_(statuses))
    if start:
        clauses.append(order_line_versions.c.order_date >= datetime.combine(start, time.min))
    if end:
        clauses.append(order_line_versions.c.order_date < datetime.combine(end, time.min) + timedelta(days=1))
    if search:
        needle = _like_needle(search)
        clauses.append(or_(*(column.ilike(needle, escape="\\") for column in SEARCH_COLUMNS)))
    return clauses


def _current_rows(engine: Engine, accounts=None, start=None, end=None, statuses=None) -> pd.DataFrame:
    stmt = select(*REPORT_COLUMNS).where(*_current_filters(accounts, start, end, statuses))
    df = pd.read_sql(stmt, engine)
    if not df.empty:
        df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    return df


def _days_between(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if df.empty:
        return df
    days = df["order_date"].dt.date
    return df[(days >= start) & (days <= end)]


def overview(engine: Engine, accounts=None, start=None, end=None, statuses=None) -> pd.DataFrame:
    df = _current_rows(engine, accounts, start, end, statuses)
    if df.empty:
        return pd.DataFrame(columns=["account", "orders", "order_lines", "gmv", "units_sold", "units_refunded", "initial_commission", "cancelled_gmv", "cancelled_commission", "actual_gmv", "actual_commission", "final_received"])
    df["initial_commission"] = df["estimated_commission"]
    df["cancelled_gmv"] = df["gmv"].where(df["status"] == "ineligible", 0)
    df["cancelled_commission"] = df["initial_commission"].where(df["status"] == "ineligible", 0)
    df["actual_gmv"] = df["gmv"] - df["cancelled_gmv"]
    df["actual_commission"] = df["initial_commission"] - df["cancelled_commission"]
    result = df.groupby("account", as_index=False).agg(
        orders=("order_id", "nunique"),
        order_lines=("id", "count"),
        gmv=("gmv", "sum"),
        units_sold=("units_sold", "sum"),
        units_refunded=("units_refunded", "sum"),
        initial_commission=("initial_commission", "sum"),
        cancelled_gmv=("cancelled_gmv", "sum"),
        cancelled_commission=("cancelled_commission", "sum"),
        actual_gmv=("actual_gmv", "sum"),
        actual_commission=("actual_commission", "sum"),
        final_received=("final_received", "sum"),
    ).sort_values("account")
    total = {column: result[column].sum() for column in result.columns if column not in {"account", "orders"}}
    total.update({
        "account": "ALL",
        "orders": len(df.dropna(subset=["order_id"])[["account", "order_id"]].drop_duplicates()),
    })
    return pd.concat([result, pd.DataFrame([total])], ignore_index=True)


def daily_report(engine: Engine, accounts=None, start=None, end=None, statuses=None) -> pd.DataFrame:
    df = _current_rows(engine, accounts, start, end, statuses)
    if df.empty:
        return pd.DataFrame(columns=["day", "account", "orders", "order_lines", "gross_gmv", "units_sold", "units_refunded", "initial_commission", "cancelled_rows", "cancelled_gmv", "cancelled_commission", "actual_gmv", "actual_commission", "final_received", "daily_target", "target_achievement"])
    df = df[df["order_date"].notna()].copy()
    df["day"] = df["order_date"].dt.date.astype(str)
    df["initial_commission"] = df["estimated_commission"]
    df["cancelled_rows"] = (df["status"] == "ineligible").astype(int)
    df["cancelled_gmv"] = df["gmv"].where(df["status"] == "ineligible", 0)
    df["cancelled_commission"] = df["initial_commission"].where(df["status"] == "ineligible", 0)
    df["actual_gmv"] = df["gmv"] - df["cancelled_gmv"]
    df["actual_commission"] = df["initial_commission"] - df["cancelled_commission"]
    df["order_key"] = df["account"] + "|" + df["order_id"].fillna("")
    aggregations = dict(
        orders=("order_key", "nunique"),
        order_lines=("id", "count"),
        gross_gmv=("gmv", "sum"),
        units_sold=("units_sold", "sum"),
        units_refunded=("units_refunded", "sum"),
        initial_commission=("initial_commission", "sum"),
        cancelled_rows=("cancelled_rows", "sum"),
        cancelled_gmv=("cancelled_gmv", "sum"),
        cancelled_commission=("cancelled_commission", "sum"),
        actual_gmv=("actual_gmv", "sum"),
        actual_commission=("actual_commission", "sum"),
        final_received=("final_received", "sum"),
    )
    per_account = df.groupby(["day", "account"], as_index=False).agg(**aggregations)
    totals = df.groupby("day", as_index=False).agg(**aggregations)
    totals["account"] = "ALL"
    result = pd.concat([per_account, totals], ignore_index=True)

    targets = pd.read_sql(select(monthly_targets), engine)
    target_map = {
        (account, pd.Timestamp(month).strftime("%Y-%m")): int(target)
        for account, month, target in zip(targets["account"], targets["month"], targets["daily_target_commission"])
    }
    active_accounts = _active_account_codes(engine)
    selected_accounts = active_accounts if accounts is None else accounts
    full_scope = set(selected_accounts) == set(active_accounts)

    def daily_target(row) -> int | pd.NA:
        if statuses:
            return pd.NA
        month_key = row["day"][:7]
        if row["account"] != "ALL":
            return target_map.get((row["account"], month_key), pd.NA)
        if full_scope:
            return target_map.get(("ALL", month_key), pd.NA)
        account_targets = [target_map.get((account, month_key)) for account in selected_accounts]
        return sum(account_targets) if all(target is not None for target in account_targets) else pd.NA

    result["daily_target"] = pd.Series([daily_target(row) for _, row in result.iterrows()], index=result.index, dtype="Int64")
    denominator = pd.to_numeric(result["daily_target"], errors="coerce").where(lambda values: values > 0)
    result["target_achievement"] = result["actual_commission"].div(denominator)
    return result.sort_values(["day", "account"], ascending=[False, True])


# Bảng đơn hàng cần thêm business_key để mở được lịch sử phiên bản của đúng dòng đó; các báo
# cáo tổng hợp thì không, nên khoá này chỉ nằm trong truy vấn danh sách đơn.
ORDER_ROW_COLUMNS = [*REPORT_COLUMNS, order_line_versions.c.business_key]
ORDER_COLUMNS = [
    "account", "order_id", "sku_id", "product_id", "product_name", "shop_id", "shop_name",
    "content_type", "content_id", "order_type", "commission_type", "currency", "status",
    "order_date", "settlement_date", "gmv", "actual_gmv", "units_sold", "units_refunded",
    "estimated_commission", "actual_commission", "final_received", "version", "created_at",
    "business_key",
]
# File Excel xuất ra là để người dùng đọc, không cần khoá nội bộ.
ORDER_EXPORT_COLUMNS = [column for column in ORDER_COLUMNS if column != "business_key"]


ORDER_SORT_COLUMNS = {
    name: order_line_versions.c[name]
    for name in (
        "account", "order_id", "sku_id", "product_name", "shop_name", "status",
        "order_date", "units_sold", "units_refunded", "gmv", "estimated_commission", "final_received",
    )
}


def _order_by(sort: str | None, direction: str):
    default = (
        order_line_versions.c.order_date.desc().nulls_last(),
        order_line_versions.c.order_id.asc().nulls_last(),
        order_line_versions.c.sku_id.asc().nulls_last(),
    )
    if not sort:
        return default
    if sort not in ORDER_SORT_COLUMNS:
        raise ValueError(f"sort phải là một trong: {', '.join(sorted(ORDER_SORT_COLUMNS))}")
    column = ORDER_SORT_COLUMNS[sort]
    ordered = column.desc() if direction == "desc" else column.asc()
    # Chốt thêm khoá phụ để phân trang không đổi thứ tự giữa các trang khi giá trị bằng nhau.
    return (ordered.nulls_last(), order_line_versions.c.id.asc())


def orders(engine: Engine, accounts=None, start=None, end=None, statuses=None, search=None, limit=None, offset=0, sort=None, direction="desc") -> pd.DataFrame:
    stmt = (
        select(*ORDER_ROW_COLUMNS)
        .where(*_current_filters(accounts, start, end, statuses, search))
        .order_by(*_order_by(sort, direction))
    )
    if limit is not None:
        stmt = stmt.limit(limit).offset(offset)
    df = pd.read_sql(stmt, engine)
    if df.empty:
        return pd.DataFrame(columns=ORDER_COLUMNS)
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    return _with_actuals(df)[ORDER_COLUMNS]


def count_orders(engine: Engine, accounts=None, start=None, end=None, statuses=None, search=None) -> int:
    stmt = select(func.count()).select_from(order_line_versions).where(
        *_current_filters(accounts, start, end, statuses, search)
    )
    with engine.connect() as conn:
        return int(conn.execute(stmt).scalar_one())


def import_history(engine: Engine) -> pd.DataFrame:
    from .db import import_batches
    return pd.read_sql(select(import_batches).order_by(import_batches.c.id.desc()), engine)


def monthly_kpi(engine: Engine, accounts=None, start=None, end=None, statuses=None) -> pd.DataFrame:
    active_accounts = _active_account_codes(engine)
    selected_accounts = list(active_accounts if accounts is None else accounts)
    full_scope = set(selected_accounts) == set(active_accounts)
    target_accounts = [] if statuses else [*selected_accounts, *(["ALL"] if full_scope else [])]
    targets = pd.read_sql(
        select(monthly_targets)
        .where(monthly_targets.c.account.in_(target_accounts))
        .order_by(monthly_targets.c.month, monthly_targets.c.account),
        engine,
    )[["month", "account", "daily_target_commission"]].rename(columns={"daily_target_commission": "daily_target"})
    df = _current_rows(engine, accounts, start, end, statuses)
    if df.empty:
        actual = pd.DataFrame(columns=["month", "account", "actual_commission", "combined_commission", "order_lines"])
    else:
        df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
        df = df[df["order_date"].notna()].copy()
        df["month"] = df["order_date"].dt.to_period("M").dt.to_timestamp().dt.date
        df["actual_commission"] = df["estimated_commission"].where(df["status"] != "ineligible", 0)
        # combined_commission = hoa hồng ước tính của MỌI đơn, kể cả Không đủ điều kiện — dùng cho
        # lớp "Hiệu suất gộp" (theo dõi sức bán), tách biệt với actual_commission (tiền thật sẽ nhận).
        df["combined_commission"] = df["estimated_commission"]
        per_account = df.groupby(["month", "account"], as_index=False).agg(
            actual_commission=("actual_commission", "sum"),
            combined_commission=("combined_commission", "sum"),
            order_lines=("id", "count"),
        )
        totals = df.groupby("month", as_index=False).agg(
            actual_commission=("actual_commission", "sum"),
            combined_commission=("combined_commission", "sum"),
            order_lines=("id", "count"),
        )
        totals["account"] = "ALL"
        actual = pd.concat([per_account, totals], ignore_index=True)
    out = targets.merge(actual, on=["month", "account"], how="outer")
    if out.empty:
        return pd.DataFrame(columns=MONTHLY_KPI_COLUMNS)
    out["month"] = pd.to_datetime(out["month"]).dt.date
    if start:
        out = out[out["month"] >= date(start.year, start.month, 1)]
    if end:
        out = out[out["month"] <= date(end.year, end.month, 1)]
    if out.empty:
        return pd.DataFrame(columns=MONTHLY_KPI_COLUMNS)

    def days_in_scope(month: date) -> int:
        month_end = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
        lower = max(month, start) if start else month
        upper = min(month_end, end) if end else month_end
        return max((upper - lower).days + 1, 0)

    out["daily_target"] = pd.to_numeric(out["daily_target"], errors="coerce").astype("Int64")
    if not full_scope and not statuses:
        target_lookup = {
            (account, pd.Timestamp(month).date()): int(target)
            for account, month, target in zip(targets["account"], targets["month"], targets["daily_target"])
        }

        def subset_target(month: date) -> int | pd.NA:
            account_targets = [target_lookup.get((account, month)) for account in selected_accounts]
            return sum(account_targets) if all(target is not None for target in account_targets) else pd.NA

        all_rows = out["account"] == "ALL"
        out.loc[all_rows, "daily_target"] = pd.Series(
            [subset_target(month) for month in out.loc[all_rows, "month"]],
            index=out.loc[all_rows].index,
            dtype="Int64",
        )
    out["actual_commission"] = pd.to_numeric(out["actual_commission"], errors="coerce").astype("Int64")
    out["combined_commission"] = pd.to_numeric(out["combined_commission"], errors="coerce").astype("Int64")
    out["order_lines"] = out["order_lines"].fillna(0).astype(int)
    out["days_in_scope"] = out["month"].map(days_in_scope)
    if statuses:
        out["daily_target"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    out["monthly_target"] = out["daily_target"] * out["days_in_scope"]
    out["gap"] = out["actual_commission"] - out["monthly_target"]
    denominator = pd.to_numeric(out["monthly_target"], errors="coerce").where(lambda values: values > 0)
    out["target_achievement"] = out["actual_commission"].div(denominator)
    out["combined_gap"] = out["combined_commission"] - out["monthly_target"]
    out["combined_target_achievement"] = out["combined_commission"].div(denominator)
    out["ineligible_commission"] = out["combined_commission"] - out["actual_commission"]
    combined_denominator = pd.to_numeric(out["combined_commission"], errors="coerce").where(lambda values: values > 0)
    out["ineligible_rate"] = out["ineligible_commission"].div(combined_denominator)
    return out[MONTHLY_KPI_COLUMNS].sort_values(["month", "account"])


def _sum_or_na(values: pd.Series):
    """Tổng bỏ qua ô trống, nhưng trống hết thì vẫn là trống chứ không phải 0."""
    return pd.NA if values.isna().all() else int(values.fillna(0).sum())


def collapse_kpi_to_scope(df: pd.DataFrame) -> pd.DataFrame:
    """Gộp các dòng theo tháng thành một dòng cho mỗi tài khoản, phủ đúng phạm vi đang xem.

    KPI đặt riêng cho từng tháng, nên "30 ngày qua" bắc qua ranh giới tháng sẽ ra hai dòng cho
    cùng một tài khoản. Giao diện chỉ đọc được một dòng, nên tiến độ mục tiêu lại đo một khoảng
    khác hẳn mọi con số còn lại trên cùng màn hình: hoa hồng tính đủ 30 ngày còn tiến độ chỉ
    tính phần thuộc tháng hiện tại. Mục tiêu của cả phạm vi là tổng KPI/ngày nhân số ngày của
    từng tháng, đúng theo cách days_in_scope đã làm trong phạm vi một tháng.
    """
    if df.empty:
        return df

    rows = []
    for account, group in df.groupby("account", sort=True):
        targets = group["monthly_target"]
        # Thiếu KPI của bất kỳ tháng nào trong phạm vi thì tổng mục tiêu là chưa xác định, chứ
        # không phải tổng của mấy tháng có đặt — nếu không sẽ báo vượt mục tiêu một cách giả tạo.
        monthly_target = pd.NA if targets.isna().any() else int(targets.sum())
        daily_values = group["daily_target"].dropna().unique()
        actual = _sum_or_na(group["actual_commission"])
        combined = _sum_or_na(group["combined_commission"])
        has_target = monthly_target is not pd.NA and monthly_target > 0
        ineligible = pd.NA if (actual is pd.NA or combined is pd.NA) else combined - actual
        rows.append({
            "month": min(group["month"]),
            "account": account,
            # KPI/ngày chỉ có nghĩa khi mọi tháng trong phạm vi đặt cùng một mức.
            "daily_target": int(daily_values[0]) if len(daily_values) == 1 and len(group) == len(group["daily_target"].dropna()) else pd.NA,
            "days_in_scope": int(group["days_in_scope"].sum()),
            "monthly_target": monthly_target,
            "actual_commission": actual,
            "gap": pd.NA if (actual is pd.NA or monthly_target is pd.NA) else actual - monthly_target,
            "target_achievement": actual / monthly_target if has_target and actual is not pd.NA else pd.NA,
            "combined_commission": combined,
            "combined_gap": pd.NA if (combined is pd.NA or monthly_target is pd.NA) else combined - monthly_target,
            "combined_target_achievement": combined / monthly_target if has_target and combined is not pd.NA else pd.NA,
            "ineligible_commission": ineligible,
            "ineligible_rate": ineligible / combined if (ineligible is not pd.NA and combined) else pd.NA,
            "order_lines": int(group["order_lines"].fillna(0).sum()),
        })
    return pd.DataFrame(rows, columns=MONTHLY_KPI_COLUMNS)


def sheets_output(engine: Engine, accounts=None, start=None, end=None, statuses=None) -> pd.DataFrame:
    active_accounts = _active_account_codes(engine)
    account_order = list(active_accounts if accounts is None else accounts)
    columns = ["Ngày"]
    account_metrics = [
        ("units_sold", "Số lượng bán"),
        ("gross_gmv", "Tổng DT"),
        ("initial_commission", "Tổng HH ban đầu"),
        ("cancelled_gmv", "DT huỷ"),
        ("cancelled_commission", "HH huỷ"),
        ("actual_gmv", "DT thực tế"),
        ("actual_commission", "HH thực tế"),
    ]
    for account in account_order:
        columns.extend(f"{account} - {label}" for _, label in account_metrics)
    columns.extend(["Tổng DT thực tế", "Tổng HH thực tế", "KPI/ngày", "% đạt KPI"])

    daily = daily_report(engine, account_order, start, end, statuses)
    data_days = pd.to_datetime(daily["day"], errors="coerce").dropna() if not daily.empty else pd.Series(dtype="datetime64[ns]")
    first_day = pd.Timestamp(start) if start else (data_days.min() if not data_days.empty else None)
    last_day = pd.Timestamp(end) if end else (data_days.max() if not data_days.empty else None)
    if first_day is None or last_day is None or first_day > last_day:
        return pd.DataFrame(columns=columns)

    days = pd.date_range(first_day, last_day, freq="D").strftime("%Y-%m-%d").tolist()
    output = pd.DataFrame({"Ngày": days})
    for account in account_order:
        rows = daily[daily["account"] == account].set_index("day")
        for metric, label in account_metrics:
            output[f"{account} - {label}"] = output["Ngày"].map(rows[metric]).fillna(0).astype("int64")

    totals = daily[daily["account"] == "ALL"].set_index("day")
    output["Tổng DT thực tế"] = output["Ngày"].map(totals["actual_gmv"]).fillna(0).astype("int64")
    output["Tổng HH thực tế"] = output["Ngày"].map(totals["actual_commission"]).fillna(0).astype("int64")
    targets = pd.read_sql(select(monthly_targets).where(monthly_targets.c.account == "ALL"), engine)
    target_map = {
        pd.Timestamp(month).strftime("%Y-%m"): int(target)
        for month, target in zip(targets["month"], targets["daily_target_commission"])
    }
    if set(account_order) == set(active_accounts) and not statuses:
        output["KPI/ngày"] = output["Ngày"].str[:7].map(target_map).astype("Int64")
    else:
        output["KPI/ngày"] = pd.Series(pd.NA, index=output.index, dtype="Int64")
    denominator = pd.to_numeric(output["KPI/ngày"], errors="coerce").where(lambda values: values > 0)
    output["% đạt KPI"] = output["Tổng HH thực tế"].div(denominator)
    return output[columns]


def _with_actuals(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    out["initial_commission"] = pd.to_numeric(out["estimated_commission"], errors="coerce").fillna(0)
    out["is_ineligible"] = out["status"] == "ineligible"
    out["actual_gmv"] = pd.to_numeric(out["gmv"], errors="coerce").fillna(0).where(~out["is_ineligible"], 0)
    out["actual_commission"] = out["initial_commission"].where(~out["is_ineligible"], 0)
    out["final_received_value"] = pd.to_numeric(out["final_received"], errors="coerce").fillna(0)
    out["order_key"] = out["account"].fillna("").astype(str) + "|" + out["order_id"].fillna("").astype(str)
    return out


def _safe_rate(numerator: float | int, denominator: float | int) -> float | None:
    return float(numerator) / float(denominator) if denominator else None


def _summary(df: pd.DataFrame) -> dict[str, object]:
    if df.empty:
        return {
            "orders": 0,
            "order_lines": 0,
            "gross_gmv": 0,
            "actual_gmv": 0,
            "initial_commission": 0,
            "actual_commission": 0,
            "final_received": 0,
            "units_sold": 0,
            "units_refunded": 0,
            "effective_commission_rate": None,
            "refund_rate": None,
            "ineligible_rate": None,
            "final_received_variance": 0,
            "latest_order_date": None,
        }
    work = _with_actuals(df)
    gross_gmv = int(pd.to_numeric(work["gmv"], errors="coerce").fillna(0).sum())
    actual_gmv = int(work["actual_gmv"].sum())
    initial_commission = int(work["initial_commission"].sum())
    actual_commission = int(work["actual_commission"].sum())
    final_received = int(work["final_received_value"].sum())
    units_sold = int(pd.to_numeric(work["units_sold"], errors="coerce").fillna(0).sum())
    units_refunded = int(pd.to_numeric(work["units_refunded"], errors="coerce").fillna(0).sum())
    latest_order = pd.to_datetime(work["order_date"], errors="coerce").max()
    return {
        "orders": int(work["order_key"].nunique()),
        "order_lines": int(len(work)),
        "gross_gmv": gross_gmv,
        "actual_gmv": actual_gmv,
        "initial_commission": initial_commission,
        "actual_commission": actual_commission,
        "final_received": final_received,
        "units_sold": units_sold,
        "units_refunded": units_refunded,
        "effective_commission_rate": _safe_rate(actual_commission, actual_gmv),
        "refund_rate": _safe_rate(units_refunded, units_sold),
        "ineligible_rate": _safe_rate(int(work["is_ineligible"].sum()), len(work)),
        "final_received_variance": final_received - actual_commission,
        "latest_order_date": None if pd.isna(latest_order) else latest_order.isoformat(),
    }


def _trend(df: pd.DataFrame, group_by: str) -> list[dict[str, object]]:
    if df.empty:
        return []
    work = _with_actuals(df)
    dates = pd.to_datetime(work["order_date"], errors="coerce")
    work = work[dates.notna()].copy()
    dates = dates[dates.notna()]
    if work.empty:
        return []
    if group_by == "week":
        work["period"] = dates.dt.to_period("W-SUN").dt.start_time.dt.strftime("%Y-%m-%d")
    elif group_by == "month":
        work["period"] = dates.dt.strftime("%Y-%m")
    else:
        work["period"] = dates.dt.strftime("%Y-%m-%d")
    grouped = work.groupby("period", as_index=False).agg(
        orders=("order_key", "nunique"),
        order_lines=("id", "count"),
        gross_gmv=("gmv", "sum"),
        actual_gmv=("actual_gmv", "sum"),
        actual_commission=("actual_commission", "sum"),
        final_received=("final_received_value", "sum"),
    )
    return [
        {
            "period": str(row.period),
            "orders": int(row.orders),
            "order_lines": int(row.order_lines),
            "gross_gmv": int(row.gross_gmv),
            "actual_gmv": int(row.actual_gmv),
            "actual_commission": int(row.actual_commission),
            "final_received": int(row.final_received),
        }
        for row in grouped.itertuples(index=False)
    ]


def _breakdown(df: pd.DataFrame, column: str, key: str) -> list[dict[str, object]]:
    if df.empty:
        return []
    work = _with_actuals(df)
    work[column] = work[column].fillna("unknown").astype(str).replace("", "unknown")
    grouped = work.groupby(column, as_index=False).agg(
        orders=("order_key", "nunique"),
        order_lines=("id", "count"),
        gross_gmv=("gmv", "sum"),
        initial_commission=("initial_commission", "sum"),
        actual_gmv=("actual_gmv", "sum"),
        actual_commission=("actual_commission", "sum"),
    )
    total_orders = max(int(work["order_key"].nunique()), 1)
    total_gmv = int(grouped["actual_gmv"].sum())
    total_commission = int(grouped["actual_commission"].sum())
    return [
        {
            key: str(getattr(row, column)),
            "orders": int(row.orders),
            "order_lines": int(row.order_lines),
            "gross_gmv": int(row.gross_gmv),
            # Hoa hồng ước tính thô (chưa trừ đơn "Không đủ điều kiện") — actual_commission luôn
            # bằng 0 khi cả nhóm là ineligible (đúng theo thiết kế, xem docs/DATA_MAPPING.md), nên
            # UI cần trường này để không hiển thị "0" gây hiểu nhầm là thiếu dữ liệu.
            "initial_commission": int(row.initial_commission),
            "actual_gmv": int(row.actual_gmv),
            "actual_commission": int(row.actual_commission),
            "order_share": int(row.orders) / total_orders,
            "gmv_share": _safe_rate(int(row.actual_gmv), total_gmv),
            "commission_share": _safe_rate(int(row.actual_commission), total_commission),
            "share": _safe_rate(int(row.actual_commission), total_commission),
        }
        for row in grouped.sort_values("actual_commission", ascending=False).itertuples(index=False)
    ]


def _dimension(df: pd.DataFrame, dimension: str, top: int) -> list[dict[str, object]]:
    if df.empty:
        return []
    work = _with_actuals(df)
    if dimension == "product":
        id_column, label_column = "product_id", "product_name"
    elif dimension == "shop":
        id_column, label_column = "shop_id", "shop_name"
    else:
        id_column, label_column = "content_id", "content_type"
    for column in (id_column, label_column):
        if column not in work:
            work[column] = None
        work[column] = work[column].fillna("unknown").astype(str).replace("", "unknown")
    work["ineligible_order_key"] = work["order_key"].where(work["is_ineligible"])
    grouped = work.groupby([id_column, label_column], as_index=False).agg(
        orders=("order_key", "nunique"),
        order_lines=("id", "count"),
        units_sold=("units_sold", "sum"),
        units_refunded=("units_refunded", "sum"),
        gross_gmv=("gmv", "sum"),
        actual_gmv=("actual_gmv", "sum"),
        actual_commission=("actual_commission", "sum"),
        ineligible_rows=("is_ineligible", "sum"),
        cancelled_orders=("ineligible_order_key", "nunique"),
    ).sort_values(["actual_commission", "actual_gmv"], ascending=False).head(top)
    return [
        {
            "id": str(getattr(row, id_column)),
            # Nội dung không có tên, chỉ có content_type — mà mọi dòng đều là "Video", nên
            # bảng xếp hạng nội dung hiện 20 dòng mang nhãn giống hệt nhau, không phân biệt
            # được gì. Đo trên dữ liệu thật: 343 content_id khác nhau, đúng một content_type.
            # Với nội dung thì chính ID mới là thứ nhận diện được.
            "label": str(getattr(row, id_column if dimension == "content" else label_column)),
            "orders": int(row.orders),
            "order_lines": int(row.order_lines),
            "units_sold": int(row.units_sold),
            "units_refunded": int(row.units_refunded),
            "gross_gmv": int(row.gross_gmv),
            "actual_gmv": int(row.actual_gmv),
            "actual_commission": int(row.actual_commission),
            "ineligible_rate": _safe_rate(int(row.ineligible_rows), int(row.order_lines)),
            "cancelled_orders": int(row.cancelled_orders),
            "cancellation_rate": _safe_rate(int(row.cancelled_orders), int(row.orders)),
        }
        for row in grouped.itertuples(index=False)
    ]


def _settlement(df: pd.DataFrame, today: date) -> dict[str, object]:
    if df.empty:
        return {"median_lag_days": None, "settled_lines": 0, "pending_lines": 0, "pending_aging": []}
    work = df.copy()
    order_dates = pd.to_datetime(work["order_date"], errors="coerce")
    settlement_dates = pd.to_datetime(work["settlement_date"], errors="coerce")
    settled = (work["status"] == "settled") & order_dates.notna() & settlement_dates.notna()
    lags = (settlement_dates[settled] - order_dates[settled]).dt.days.tolist()
    non_negative_lags = [int(value) for value in lags if value >= 0]
    pending = work["status"] == "pending"
    buckets = {"0-7": 0, "8-14": 0, "15-30": 0, "31+": 0, "unknown": 0}
    for value in order_dates[pending]:
        if pd.isna(value):
            buckets["unknown"] += 1
            continue
        age = max((today - value.date()).days, 0)
        bucket = "0-7" if age <= 7 else "8-14" if age <= 14 else "15-30" if age <= 30 else "31+"
        buckets[bucket] += 1
    return {
        "median_lag_days": None if not non_negative_lags else float(median(non_negative_lags)),
        "settled_lines": int((work["status"] == "settled").sum()),
        "pending_lines": int(pending.sum()),
        "pending_aging": [{"bucket": name, "count": count} for name, count in buckets.items()],
    }


def _data_quality(engine: Engine, df: pd.DataFrame, accounts: list[str] | None) -> dict[str, object]:
    work = df.copy()
    order_dates = pd.to_datetime(work.get("order_date"), errors="coerce") if not work.empty else pd.Series(dtype="datetime64[ns]")
    settlement_dates = pd.to_datetime(work.get("settlement_date"), errors="coerce") if not work.empty else pd.Series(dtype="datetime64[ns]")
    currencies = work.get("currency", pd.Series(index=work.index, dtype="object")).fillna("").astype(str).str.upper()
    stmt = select(import_batches)
    if accounts is not None:
        stmt = stmt.where(import_batches.c.account.in_(accounts))
    # KHÔNG lọc import_batches theo khoảng ngày đang xem, dù nhìn thì có vẻ nên làm. Bộ lọc
    # trên trang lọc theo NGÀY ĐẶT ĐƠN, còn created_at là LÚC NHẬP TỆP — hai trục khác nhau,
    # nhập dữ liệu tháng 3 vào tháng 8 là chuyện thường. Riêng dòng bị từ chối thì còn không có
    # ngày đặt đơn nào cả vì chúng chưa từng phân tích được. Vì vậy các số import_* ở đây là
    # số toàn thời gian, và giao diện phải nói rõ như vậy thay vì trộn vào chỉ số theo kỳ.
    imports = pd.read_sql(stmt, engine)
    latest_import = pd.to_datetime(imports["created_at"], errors="coerce").max() if not imports.empty else pd.NaT
    return {
        "unknown_status_rows": int((work.get("status", pd.Series(index=work.index, dtype="object")) == "unknown").sum()),
        "non_vnd_rows": int(((currencies != "") & (currencies != "VND")).sum()),
        "missing_order_date_rows": int(order_dates.isna().sum()),
        "missing_settlement_date_rows": int(settlement_dates.isna().sum()),
        "settled_missing_settlement_rows": int(((work.get("status") == "settled") & settlement_dates.isna()).sum()) if not work.empty else 0,
        "negative_settlement_lag_rows": int(((settlement_dates - order_dates).dt.days < 0).sum()) if not work.empty else 0,
        "import_batches": int(len(imports)),
        "import_inserted": int(imports["inserted"].sum()) if not imports.empty else 0,
        "import_updated": int(imports["updated"].sum()) if not imports.empty else 0,
        "import_unchanged": int(imports["unchanged"].sum()) if not imports.empty else 0,
        "import_rejected": int(imports["rejected"].sum()) if not imports.empty else 0,
        "latest_import_at": None if pd.isna(latest_import) else latest_import.isoformat(),
    }


def _target_snapshot(
    engine: Engine,
    accounts: list[str] | None,
    start: date | None,
    end: date | None,
    statuses: list[str] | None,
    actual_commission: int,
    today: date,
) -> dict[str, object] | None:
    if statuses or not start or not end or (start.year, start.month) != (end.year, end.month):
        return None
    rows = monthly_kpi(engine, accounts, start, end, statuses)
    if rows.empty:
        return None
    total = rows[(rows["account"] == "ALL") & (rows["month"] == date(start.year, start.month, 1))]
    if total.empty:
        return None
    row = total.iloc[0]
    target = None if pd.isna(row["monthly_target"]) else int(row["monthly_target"])
    achievement = None if pd.isna(row["target_achievement"]) else float(row["target_achievement"])
    remaining = None if target is None else max(target - actual_commission, 0)
    is_current_month = (today.year, today.month) == (start.year, start.month)
    elapsed_end = min(today, end)
    elapsed_days = max((elapsed_end - start).days + 1, 0) if elapsed_end >= start else 0
    scope_days = (end - start).days + 1
    projected = round(actual_commission / elapsed_days * scope_days) if is_current_month and elapsed_days else None
    remaining_days = max((end - max(today, start)).days, 0) if is_current_month else 0
    return {
        "monthly_target": target,
        "actual_commission": actual_commission,
        "remaining": remaining,
        "achievement": achievement,
        "elapsed_days": elapsed_days,
        "scope_days": scope_days,
        "remaining_days": remaining_days,
        "required_per_remaining_day": None if remaining is None or remaining_days == 0 else round(remaining / remaining_days),
        "projected_month_end": projected,
        "projected_achievement": None if projected is None or not target else projected / target,
    }


def analytics(
    engine: Engine,
    accounts: list[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    statuses: list[str] | None = None,
    group_by: str = "day",
    top: int = 20,
    today: date | None = None,
) -> dict[str, object]:
    if group_by not in {"day", "week", "month"}:
        raise ValueError("group_by must be day, week or month")
    if start and end and start > end:
        raise ValueError("start must not be after end")
    if not 1 <= top <= 100:
        raise ValueError("top must be between 1 and 100")
    today = today or datetime.now(ZoneInfo("Asia/Bangkok")).date()
    previous_summary = None
    previous_range = None
    if start and end:
        duration = (end - start).days + 1
        previous_end = start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=duration - 1)
        # Một truy vấn phủ cả kỳ này lẫn kỳ trước, rồi cắt trong bộ nhớ.
        scope = _current_rows(engine, accounts, previous_start, end, statuses)
        current = _days_between(scope, start, end)
        previous_summary = _summary(_days_between(scope, previous_start, previous_end))
        previous_range = {"start": previous_start.isoformat(), "end": previous_end.isoformat()}
    else:
        current = _current_rows(engine, accounts, start, end, statuses)
    summary = _summary(current)
    return {
        "filters": {
            "accounts": list(accounts or []),
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "statuses": list(statuses or []),
            "group_by": group_by,
            "top": top,
        },
        "summary": summary,
        "previous_period": None if previous_summary is None else {"range": previous_range, "summary": previous_summary},
        "target": _target_snapshot(engine, accounts, start, end, statuses, int(summary["actual_commission"]), today),
        "trend": _trend(current, group_by),
        "status_breakdown": _breakdown(current, "status", "status"),
        "account_breakdown": _breakdown(current, "account", "account"),
        "products": _dimension(current, "product", top),
        "shops": _dimension(current, "shop", top),
        "content": _dimension(current, "content", top),
        "settlement": _settlement(current, today),
        "data_quality": _data_quality(engine, current, accounts),
    }
