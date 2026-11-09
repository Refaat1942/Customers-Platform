"""All analytics as SQL over the `sales` table.

One definition of every metric, shared by every page:
  * visit / invoice  = distinct invoice_no, or (phone, day, branch) when the file has no invoice number
  * total spend      = SUM(item_price)
  * days since visit = reference date - last visit day, where the reference date is the end of the
                       selected date range, or the latest date in the data (not "today", so an old
                       import does not make everybody look inactive)
  * status           = active / attention / inactive from the Settings thresholds
"""

from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from .. import db

SEASON_ORDER = ["Winter", "Spring", "Summer", "Autumn"]


@dataclass
class Filters:
    date_from: date | None = None
    date_to: date | None = None
    branches: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    districts: list[str] = field(default_factory=list)
    seasons: list[str] = field(default_factory=list)
    allowed_branches: list[str] | None = None  # set from the user's account

    def where(self, alias: str = "") -> tuple[str, list]:
        p = f"{alias}." if alias else ""
        parts, params = ["TRUE"], []
        if self.date_from:
            parts.append(f"{p}day >= ?")
            params.append(self.date_from)
        if self.date_to:
            parts.append(f"{p}day <= ?")
            params.append(self.date_to)

        branches = list(self.branches)
        if self.allowed_branches:
            branches = [b for b in branches if b in self.allowed_branches] if branches \
                else list(self.allowed_branches)
            if not branches:
                parts.append("FALSE")
        for col, values in (("branch", branches), ("invoice_type", self.types),
                            ("district", self.districts), ("season", self.seasons)):
            if values:
                parts.append(f"{p}{col} IN (SELECT unnest(?::VARCHAR[]))")
                params.append(values)
        return " AND ".join(parts), params


def reference_date(cur, f: Filters) -> date | None:
    if f.date_to:
        return f.date_to
    return cur.execute("SELECT max(day) FROM sales").fetchone()[0]


# ====================================================================== customers
CUSTOMER_SORTS = {
    "priority": "status_rank ASC, total_spent DESC",
    "total_spent": "total_spent", "visits": "visits", "last_visit": "last_visit",
    "first_visit": "first_visit", "days_since": "days_since", "name": "name",
    "phone": "phone", "branch": "branch", "avg_per_visit": "avg_per_visit",
    "avg_days_between": "avg_days_between",
}


def customers_cte(f: Filters, settings: dict, ref: date | None) -> tuple[str, list]:
    w, params = f.where()
    sql = f"""
    cust AS (
      SELECT *,
        CASE WHEN days_since IS NULL THEN 'unknown'
             WHEN days_since <= ? THEN 'active'
             WHEN days_since <= ? THEN 'attention'
             ELSE 'inactive' END AS status,
        CASE WHEN days_since IS NULL THEN 3 WHEN days_since <= ? THEN 2
             WHEN days_since <= ? THEN 1 ELSE 0 END AS status_rank,
        total_spent >= ? AS high_value,
        (total_spent >= ? OR visits >= ?) AS loyal
      FROM (
        SELECT phone,
          arg_max(name, invoice_date) FILTER (WHERE name IS NOT NULL) AS name,
          mode(branch) AS branch,
          mode(district) AS district,
          round(sum(item_price), 2) AS total_spent,
          count(DISTINCT visit_key) AS visits,
          sum(quantity) AS quantity,
          min(day)::DATE AS first_visit,
          max(day)::DATE AS last_visit,
          count(DISTINCT day) AS visit_days,
          mode(invoice_type) AS top_sales_type,
          mode(material_group) AS top_material,
          mode(item_category) AS top_category,
          mode(season) AS top_season,
          bool_or(phone_valid) AS phone_valid
        FROM sales WHERE phone IS NOT NULL AND {w}
        GROUP BY phone
      ) base
      CROSS JOIN LATERAL (SELECT
        round(total_spent / nullif(visits, 0), 2) AS avg_per_visit,
        CASE WHEN visit_days > 1
             THEN round(date_diff('day', first_visit, last_visit) / (visit_days - 1), 1) END
             AS avg_days_between,
        date_diff('day', last_visit, ?::DATE) AS days_since)
    )"""
    s = settings
    head = [s["active_days"], s["attention_days"], s["active_days"], s["attention_days"],
            s["high_value_spend"], s["loyalty_spend"], s["loyalty_visits"]]
    return sql, head + params + [ref]


def list_customers(f: Filters, settings: dict, *, q=None, status=None, flag=None,
                   sort="priority", desc=True, page=1, page_size=50, limit_all=False) -> dict:
    cur = db.cursor()
    ref = reference_date(cur, f)
    cte, params = customers_cte(f, settings, ref)
    conds, cparams = ["TRUE"], []
    if q:
        conds.append("(phone ILIKE ? OR name ILIKE ?)")
        cparams += [f"%{q}%", f"%{q}%"]
    if status:
        conds.append("status IN (SELECT unnest(?::VARCHAR[]))")
        cparams.append(status if isinstance(status, list) else [status])
    if flag == "high_value":
        conds.append("high_value")
    elif flag == "loyal":
        conds.append("loyal")
    elif flag == "invalid_phone":
        conds.append("NOT phone_valid")

    order = CUSTOMER_SORTS.get(sort, CUSTOMER_SORTS["priority"])
    if sort != "priority":
        order = f"{order} {'DESC' if desc else 'ASC'} NULLS LAST, phone"
    where = " AND ".join(conds)

    total = cur.execute(f"WITH {cte} SELECT count(*) FROM cust WHERE {where}",
                        params + cparams).fetchone()[0]
    sql = f"WITH {cte} SELECT * EXCLUDE (status_rank, visit_days) FROM cust WHERE {where} " \
          f"ORDER BY {order}"
    if not limit_all:
        sql += f" LIMIT {int(page_size)} OFFSET {int((page - 1) * page_size)}"
    return {"rows": db.rows(cur, sql, params + cparams), "total": total, "reference_date": ref}


def customer_profile(phone: str, f: Filters, settings: dict) -> dict | None:
    cur = db.cursor()
    ref = reference_date(cur, f)
    cte, params = customers_cte(f, settings, ref)
    summary = db.one(cur, f"WITH {cte} SELECT * EXCLUDE (status_rank) FROM cust WHERE phone = ?",
                     params + [phone])
    if not summary:
        return None
    w, wp = f.where()
    base = f"FROM sales WHERE phone = ? AND {w}"
    bp = [phone] + wp
    return {
        "summary": summary,
        "reference_date": ref,
        "monthly": db.rows(cur, f"""SELECT strftime(date_trunc('month', day), '%Y-%m') AS month,
            round(sum(item_price), 2) AS sales, count(DISTINCT visit_key) AS visits
            {base} GROUP BY 1 ORDER BY 1""", bp),
        "top_items": db.rows(cur, f"""SELECT coalesce(item_name, item_code, '-') AS item,
            sum(quantity) AS quantity, round(sum(item_price), 2) AS sales,
            count(DISTINCT visit_key) AS times
            {base} GROUP BY 1 ORDER BY sales DESC LIMIT 15""", bp),
        "branches": db.rows(cur, f"""SELECT branch, round(sum(item_price), 2) AS sales,
            count(DISTINCT visit_key) AS visits {base} GROUP BY 1 ORDER BY sales DESC""", bp),
        "visits": db.rows(cur, f"""SELECT visit_key, min(invoice_date) AS date, any_value(branch) AS branch,
            any_value(invoice_type) AS sales_type, count(*) AS lines,
            round(sum(item_price), 2) AS total,
            string_agg(DISTINCT coalesce(item_name, item_code), ' · ') AS items
            {base} GROUP BY visit_key ORDER BY date DESC LIMIT 200""", bp),
    }


# ====================================================================== summary
def _kpis(cur, f: Filters) -> dict:
    w, p = f.where()
    r = db.one(cur, f"""SELECT count(DISTINCT phone) AS customers,
        count(DISTINCT visit_key) AS invoices,
        round(coalesce(sum(item_price), 0), 2) AS total_sales,
        sum(quantity) AS quantity, count(*) AS lines
        FROM sales WHERE {w}""", p)
    r["avg_per_customer"] = round(r["total_sales"] / r["customers"], 2) if r["customers"] else 0
    r["avg_invoice"] = round(r["total_sales"] / r["invoices"], 2) if r["invoices"] else 0
    return r


def summary(f: Filters, settings: dict) -> dict:
    cur = db.cursor()
    w, p = f.where()
    kpis = _kpis(cur, f)

    previous = None
    if f.date_from and f.date_to:
        span = (f.date_to - f.date_from).days + 1
        prev_f = replace(f, date_from=f.date_from - timedelta(days=span),
                         date_to=f.date_from - timedelta(days=1))
        previous = _kpis(cur, prev_f)
        previous["date_from"], previous["date_to"] = prev_f.date_from, prev_f.date_to

    new_customers = None
    if f.date_from:
        # first purchase ever (within the user's allowed branches) falls inside the range
        aw, ap = Filters(allowed_branches=f.allowed_branches).where()
        new_customers = cur.execute(f"""
            SELECT count(*) FROM (SELECT phone FROM sales WHERE phone IS NOT NULL AND {aw}
              GROUP BY phone HAVING min(day) >= ?) n
            WHERE phone IN (SELECT DISTINCT phone FROM sales WHERE {w})""",
            ap + [f.date_from] + p).fetchone()[0]

    def top(col):
        r = cur.execute(f"""SELECT {col}, sum(item_price) s FROM sales
            WHERE {w} AND {col} IS NOT NULL GROUP BY 1 ORDER BY s DESC LIMIT 1""", p).fetchone()
        return r[0] if r else None

    insights = {k: top(c) for k, c in [
        ("top_branch", "branch"), ("top_season", "season"), ("top_sales_type", "invoice_type"),
        ("top_material", "material_group"), ("top_category", "item_category"),
        ("top_district", "district"), ("top_item", "item_name")]}

    ref = reference_date(cur, f)
    cte, cp = customers_cte(f, settings, ref)
    seg = db.one(cur, f"""WITH {cte} SELECT
        count(*) FILTER (WHERE status='active') AS active,
        count(*) FILTER (WHERE status='attention') AS attention,
        count(*) FILTER (WHERE status='inactive') AS inactive,
        count(*) FILTER (WHERE high_value) AS high_value,
        count(*) FILTER (WHERE loyal) AS loyal,
        count(*) FILTER (WHERE NOT phone_valid) AS invalid_phone FROM cust""", cp)

    monthly = db.rows(cur, f"""SELECT strftime(date_trunc('month', day), '%Y-%m') AS month,
        round(sum(item_price), 2) AS sales, count(DISTINCT phone) AS customers,
        count(DISTINCT visit_key) AS invoices FROM sales WHERE {w} GROUP BY 1 ORDER BY 1""", p)
    by_branch = db.rows(cur, f"""SELECT coalesce(branch, '-') AS branch,
        round(sum(item_price), 2) AS sales, count(DISTINCT phone) AS customers,
        count(DISTINCT visit_key) AS invoices,
        round(sum(item_price) / nullif(count(DISTINCT phone), 0), 2) AS avg_per_customer
        FROM sales WHERE {w} GROUP BY 1 ORDER BY sales DESC""", p)
    by_type = db.rows(cur, f"""SELECT coalesce(invoice_type, '-') AS sales_type,
        round(sum(item_price), 2) AS sales, count(DISTINCT visit_key) AS invoices
        FROM sales WHERE {w} GROUP BY 1 ORDER BY sales DESC""", p)
    by_season = db.rows(cur, f"""SELECT season, round(sum(item_price), 2) AS sales,
        count(DISTINCT visit_key) AS invoices FROM sales WHERE {w} AND season IS NOT NULL
        GROUP BY 1""", p)
    by_season.sort(key=lambda r: SEASON_ORDER.index(r["season"]) if r["season"] in SEASON_ORDER else 9)
    top_items = db.rows(cur, f"""SELECT coalesce(item_name, item_code) AS item,
        round(sum(item_price), 2) AS sales, sum(quantity) AS quantity,
        count(DISTINCT phone) AS customers FROM sales
        WHERE {w} AND coalesce(item_name, item_code) IS NOT NULL
        GROUP BY 1 ORDER BY sales DESC LIMIT 15""", p)

    return {"kpis": kpis, "previous": previous, "new_customers": new_customers,
            "insights": insights, "segments": seg, "monthly": monthly, "by_branch": by_branch,
            "by_type": by_type, "by_season": by_season, "top_items": top_items,
            "reference_date": ref}


# ====================================================================== area
def area(f: Filters, min_customers: int = 5) -> dict:
    cur = db.cursor()
    w, p = f.where()
    districts = db.rows(cur, f"""SELECT district, round(sum(item_price), 2) AS sales,
        count(DISTINCT phone) AS customers, count(DISTINCT visit_key) AS invoices,
        round(sum(item_price) / nullif(count(DISTINCT phone), 0), 2) AS spend_per_customer,
        round(100 * sum(item_price) / nullif(sum(sum(item_price)) OVER (), 0), 2) AS share
        FROM sales WHERE {w} GROUP BY 1 ORDER BY sales DESC""", p)
    branch_district = db.rows(cur, f"""SELECT coalesce(branch, '-') AS branch, district,
        round(sum(item_price), 2) AS sales, count(DISTINCT phone) AS customers,
        round(sum(item_price) / nullif(count(DISTINCT phone), 0), 2) AS spend_per_customer,
        row_number() OVER (PARTITION BY branch ORDER BY sum(item_price) DESC) AS rank
        FROM sales WHERE {w} GROUP BY branch, district ORDER BY branch, rank""", p)
    weak = sorted(
        [d for d in districts if d["district"] != "Unknown" and d["customers"] >= min_customers],
        key=lambda d: d["spend_per_customer"] or 0)[:10]
    return {"districts": districts, "branch_district": branch_district, "weak": weak,
            "min_customers": min_customers}


# ====================================================================== raw rows
SALES_SORTS = {"invoice_date", "phone", "name", "branch", "district", "invoice_type",
               "item_name", "item_category", "material_group", "quantity", "item_price"}
SALES_COLUMNS = ["invoice_date", "phone", "name", "branch", "district", "invoice_no",
                 "invoice_type", "item_code", "item_name", "material_group", "item_category",
                 "quantity", "item_unit", "item_price"]


def list_sales(f: Filters, *, q=None, sort="invoice_date", desc=True, page=1, page_size=50,
               limit_all=False) -> dict:
    cur = db.cursor()
    w, p = f.where()
    if q:
        w += " AND (phone ILIKE ? OR name ILIKE ? OR item_name ILIKE ? OR invoice_no ILIKE ?)"
        p = p + [f"%{q}%"] * 4
    sort = sort if sort in SALES_SORTS else "invoice_date"
    agg = db.one(cur, f"SELECT count(*) AS total, round(coalesce(sum(item_price),0),2) AS sales "
                      f"FROM sales WHERE {w}", p)
    sql = (f"SELECT {', '.join(SALES_COLUMNS)} FROM sales WHERE {w} "
           f"ORDER BY {sort} {'DESC' if desc else 'ASC'} NULLS LAST")
    if not limit_all:
        sql += f" LIMIT {int(page_size)} OFFSET {int((page - 1) * page_size)}"
    else:
        sql += " LIMIT 1000000"
    return {"rows": db.rows(cur, sql, p), "total": agg["total"], "sales": agg["sales"]}


# ====================================================================== meta
def meta(allowed_branches: list[str] | None) -> dict:
    cur = db.cursor()
    w, p = Filters(allowed_branches=allowed_branches).where()

    def distinct(col):
        return [r[0] for r in cur.execute(
            f"SELECT DISTINCT {col} FROM sales WHERE {w} AND {col} IS NOT NULL ORDER BY 1", p
        ).fetchall()]

    rng = cur.execute(f"SELECT min(day)::DATE, max(day)::DATE, count(*) FROM sales WHERE {w}",
                      p).fetchone()
    return {"branches": distinct("branch"), "types": distinct("invoice_type"),
            "districts": distinct("district"), "seasons": SEASON_ORDER,
            "date_min": rng[0], "date_max": rng[1], "rows": rng[2]}
