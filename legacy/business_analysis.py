import pandas as pd
from datetime import datetime


# =========================================================
# SAFE MODE
# =========================================================
def safe_mode(series):
    try:
        s = series.dropna().astype(str)
        if s.empty:
            return ""
        return s.mode().iloc[0]
    except Exception:
        return ""


# =========================================================
# SEASONS
# =========================================================
SEASON_MONTHS = {
    "Winter": {12, 1, 2},
    "Spring": {3, 4, 5},
    "Summer": {6, 7, 8},
    "Autumn": {9, 10, 11},
}


def month_to_season(month):
    try:
        m = int(month)
    except Exception:
        return None
    for s, months in SEASON_MONTHS.items():
        if m in months:
            return s
    return None


# =========================================================
# FULL CUSTOMER BUSINESS SUMMARY (FIXED)
# =========================================================
def full_customer_business(df, colmap, loyalty_threshold=10000, min_visits_loyalty=5):
    phone_col = colmap.get("phone")
    name_col = colmap.get("name")
    branch_col = colmap.get("branch")
    price_col = colmap.get("item_price")
    mat_col = colmap.get("material_group")
    cat_col = colmap.get("item_category")
    type_col = colmap.get("invoice_type")
    date_col = colmap.get("invoice_date")

    if not phone_col or phone_col not in df.columns:
        return pd.DataFrame()

    tmp = df.copy()

    # -------- DATE --------
    if date_col and date_col in tmp.columns:
        tmp[date_col] = pd.to_datetime(tmp[date_col], errors="coerce")

    # -------- VISITS (SAFE INT) --------
    if date_col and date_col in tmp.columns:
        visits = (
            tmp.groupby(phone_col)[date_col]
            .apply(lambda s: s.dropna().dt.date.nunique())
            .astype(int)
        )
    else:
        visits = tmp.groupby(phone_col).size().astype(int)

    # -------- TOTAL SPENT --------
    if price_col and price_col in tmp.columns:
        total_spent = tmp.groupby(phone_col)[price_col].sum().astype(float)
    else:
        total_spent = tmp.groupby(phone_col).size().astype(float)

    grouped = pd.DataFrame({
        "total_spent": total_spent,
        "visits": visits
    })

    # -------- SAFE TEXT COLUMNS --------
    def safe(col):
        return (
            tmp.groupby(phone_col)[col].agg(safe_mode)
            if col and col in tmp.columns
            else ""
        )

    grouped["name"] = safe(name_col)
    grouped["branch"] = safe(branch_col)
    grouped["top_material"] = safe(mat_col)
    grouped["top_category"] = safe(cat_col)
    grouped["top_sales_type"] = safe(type_col)

    # -------- SEASON --------
    if date_col and date_col in tmp.columns:
        tmp["season"] = tmp[date_col].dt.month.map(month_to_season)
        grouped["top_season"] = tmp.groupby(phone_col)["season"].agg(safe_mode)
    else:
        grouped["top_season"] = ""

    # -------- LOYALTY FLAG (SAFE) --------
    grouped["loyalty_flag"] = (
        (grouped["total_spent"] >= loyalty_threshold) |
        (grouped["visits"] >= min_visits_loyalty)
    ).map({True: "YES", False: "NO"})

    grouped = grouped.reset_index().rename(columns={phone_col: "phone"})
    grouped["total_spent_display"] = grouped["total_spent"].apply(
        lambda x: f"{x:,.2f}"
    )

    return grouped[
        [
            "phone",
            "name",
            "branch",
            "total_spent",
            "total_spent_display",
            "visits",
            "top_material",
            "top_category",
            "top_sales_type",
            "top_season",
            "loyalty_flag",
        ]
    ]
