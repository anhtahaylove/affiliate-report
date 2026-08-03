from __future__ import annotations

import calendar
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.engine import Engine

from .db import monthly_targets, order_line_versions
from .parser import DEFAULT_ACCOUNTS


MONTHLY_KPI_COLUMNS = ["month", "account", "daily_target", "days_in_scope", "monthly_target", "actual_commission", "gap", "target_achievement", "order_lines"]


def _current_rows(engine: Engine) -> pd.DataFrame:
    stmt = select(order_line_versions).where(order_line_versions.c.is_current.is_(True))
    return pd.read_sql(stmt, engine)


def _apply_filters(df: pd.DataFrame, accounts=None, start=None, end=None, statuses=None) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    if accounts is not None:
        df = df[df["account"].isin(accounts)]
    if statuses:
        df = df[df["status"].isin(statuses)]
    if start:
        df = df[df["order_date"].dt.date >= start]
    if end:
        df = df[df["order_date"].dt.date <= end]
    return df


def overview(engine: Engine, accounts=None, start=None, end=None, statuses=None) -> pd.DataFrame:
    df = _apply_filters(_current_rows(engine), accounts, start, end, statuses)
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
    df = _apply_filters(_current_rows(engine), accounts, start, end, statuses)
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
        for account, month, target in zip(targets["account"], targets["month"], targets["target_commission"])
    }
    selected_accounts = DEFAULT_ACCOUNTS if accounts is None else accounts

    def daily_target(row) -> int | pd.NA:
        if statuses:
            return pd.NA
        month_key = row["day"][:7]
        if row["account"] != "ALL":
            return target_map.get((row["account"], month_key), pd.NA)
        if set(selected_accounts) == set(DEFAULT_ACCOUNTS):
            return target_map.get(("ALL", month_key), pd.NA)
        account_targets = [target_map.get((account, month_key)) for account in selected_accounts]
        return sum(account_targets) if all(target is not None for target in account_targets) else pd.NA

    result["daily_target"] = pd.Series([daily_target(row) for _, row in result.iterrows()], index=result.index, dtype="Int64")
    denominator = pd.to_numeric(result["daily_target"], errors="coerce").where(lambda values: values > 0)
    result["target_achievement"] = result["actual_commission"].div(denominator)
    return result.sort_values(["day", "account"], ascending=[False, True])


def orders(engine: Engine, accounts=None, start=None, end=None, statuses=None, search=None) -> pd.DataFrame:
    df = _apply_filters(_current_rows(engine), accounts, start, end, statuses)
    cols = ["account", "order_id", "sku_id", "product_name", "shop_name", "status", "order_date", "gmv", "units_sold", "units_refunded", "estimated_commission", "final_received", "version", "created_at"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    if search:
        needle = str(search).strip()
        matches = pd.Series(False, index=df.index)
        for column in ("order_id", "sku_id", "product_name", "shop_name"):
            matches |= df[column].fillna("").astype(str).str.contains(needle, case=False, regex=False)
        df = df[matches]
    return df.sort_values(["order_date", "order_id", "sku_id"], ascending=[False, True, True])[cols]


def import_history(engine: Engine) -> pd.DataFrame:
    from .db import import_batches
    return pd.read_sql(select(import_batches).order_by(import_batches.c.id.desc()), engine)


def monthly_kpi(engine: Engine, accounts=None, start=None, end=None, statuses=None) -> pd.DataFrame:
    selected_accounts = list(DEFAULT_ACCOUNTS if accounts is None else accounts)
    full_scope = set(selected_accounts) == set(DEFAULT_ACCOUNTS)
    target_accounts = [] if statuses else [*selected_accounts, *(["ALL"] if full_scope else [])]
    targets = pd.read_sql(
        select(monthly_targets)
        .where(monthly_targets.c.account.in_(target_accounts))
        .order_by(monthly_targets.c.month, monthly_targets.c.account),
        engine,
    )[["month", "account", "target_commission"]].rename(columns={"target_commission": "daily_target"})
    df = _apply_filters(_current_rows(engine), accounts, start, end, statuses)
    if df.empty:
        actual = pd.DataFrame(columns=["month", "account", "actual_commission", "order_lines"])
    else:
        df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
        df = df[df["order_date"].notna()].copy()
        df["month"] = df["order_date"].dt.to_period("M").dt.to_timestamp().dt.date
        df["actual_commission"] = df["estimated_commission"].where(df["status"] != "ineligible", 0)
        per_account = df.groupby(["month", "account"], as_index=False).agg(
            actual_commission=("actual_commission", "sum"),
            order_lines=("id", "count"),
        )
        totals = df.groupby("month", as_index=False).agg(
            actual_commission=("actual_commission", "sum"),
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
    out["order_lines"] = out["order_lines"].fillna(0).astype(int)
    out["days_in_scope"] = out["month"].map(days_in_scope)
    if statuses:
        out["daily_target"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    out["monthly_target"] = out["daily_target"] * out["days_in_scope"]
    out["gap"] = out["actual_commission"] - out["monthly_target"]
    denominator = pd.to_numeric(out["monthly_target"], errors="coerce").where(lambda values: values > 0)
    out["target_achievement"] = out["actual_commission"].div(denominator)
    return out[MONTHLY_KPI_COLUMNS].sort_values(["month", "account"])


def sheets_output(engine: Engine, accounts=None, start=None, end=None, statuses=None) -> pd.DataFrame:
    account_order = list(DEFAULT_ACCOUNTS if accounts is None else accounts)
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
        for month, target in zip(targets["month"], targets["target_commission"])
    }
    if set(account_order) == set(DEFAULT_ACCOUNTS) and not statuses:
        output["KPI/ngày"] = output["Ngày"].str[:7].map(target_map).astype("Int64")
    else:
        output["KPI/ngày"] = pd.Series(pd.NA, index=output.index, dtype="Int64")
    denominator = pd.to_numeric(output["KPI/ngày"], errors="coerce").where(lambda values: values > 0)
    output["% đạt KPI"] = output["Tổng HH thực tế"].div(denominator)
    return output[columns]
