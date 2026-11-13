"""All analytics as SQL over the `sales` table (PostgreSQL).

One definition of every metric, shared by every page:
  * visit / invoice  = distinct invoice_no, or (phone, day, branch) when the file has no invoice number
  * total spend      = SUM(item_price)
  * days since visit = reference date - last visit, where the reference date is the end of the
                       selected range, or the latest date in the data (not "today", so an old
                       import does not make everybody look inactive)
  * status           = active / attention / inactive from the Settings thresholds
  * RFM segment      = recency / frequency / money quintiles -> champions, loyal, at_risk, ...
  * churn risk       = compares days since last visit with the customer's OWN visit rhythm
"""

import hashlib
import re
import threading
from collections import OrderedDict
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from .. import config, db
from .phone import is_valid_egy_mobile, normalize_egy_phone

SEASON_ORDER = ["Winter", "Spring", "Summer", "Autumn"]

# independent queries of one page run side by side (each worker thread has its own connection)
_pool = ThreadPoolExecutor(max_workers=int(os.environ.get("QUERY_WORKERS", "4")),
                           thread_name_prefix="q")


def parallel(tasks: dict) -> dict:
    futures = {k: _pool.submit(fn) for k, fn in tasks.items()}
    return {k: f.result() for k, f in futures.items()}


def q_rows(sql, params=None):
    return lambda: db.rows(db.cursor(), sql, params)


def q_one(sql, params=None):
    return lambda: db.one(db.cursor(), sql, params)


def R(expr: str) -> str:
    """Round to 2 decimals and return a float (not Decimal)."""
    return f"round(({expr})::numeric, 2)::float8"


def cid(phone: str) -> str:
    """Opaque customer id used in URLs (phone numbers never appear in links or logs)."""
    return hashlib.sha256((config.SECRET_KEY + phone).encode()).hexdigest()[:16]


def phone_for_cid(c: str) -> str | None:
    def build():
        phones = db.cursor().execute("SELECT DISTINCT phone FROM sales WHERE phone IS NOT NULL")
        return {cid(p): p for (p,) in phones.fetchall()}
    return db.cached("cid_map", build).get(c)


@dataclass
class Filters:
    date_from: date | None = None
    date_to: date | None = None
    branches: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)
    districts: list[str] = field(default_factory=list)
    seasons: list[str] = field(default_factory=list)
    allowed_branches: list[str] | None = None  # from the user's account

    def key(self):
        return (self.date_from, self.date_to, tuple(self.branches), tuple(self.types),
                tuple(self.districts), tuple(self.seasons), tuple(self.allowed_branches or ()))

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
                parts.append(f"{p}{col} = ANY(?)")
                params.append(list(values))
        return " AND ".join(parts), params

    def scope_only(self) -> "Filters":
        """Same branch restriction, no date/other filters (for 'first ever visit' logic)."""
        return Filters(allowed_branches=self.allowed_branches)


def reference_date(cur, f: Filters) -> date | None:
    if f.date_to:
        return f.date_to
    return cur.execute("SELECT max(day) FROM sales").fetchone()[0]


# ====================================================================== customers
CUSTOMER_COLUMNS = [
    "phone", "name", "branch", "district", "total_spent", "visits", "quantity", "max_invoice",
    "min_invoice", "median_invoice", "items_count", "fav_item", "first_visit",
    "last_visit", "visit_days", "branches_count", "top_sales_type", "top_material",
    "top_category", "top_season", "phone_valid", "avg_per_visit", "avg_days_between",
    "days_since", "status", "high_value", "loyal", "r_score", "f_score", "m_score", "segment",
    "expected_next", "overdue_days", "churn_risk",
]

CUSTOMER_SORTS = {
    "priority": "status_rank ASC, total_spent DESC",
    "total_spent": "total_spent", "visits": "visits", "last_visit": "last_visit",
    "first_visit": "first_visit", "days_since": "days_since", "name": "name",
    "phone": "phone", "branch": "branch", "avg_per_visit": "avg_per_visit",
    "avg_days_between": "avg_days_between", "overdue_days": "overdue_days",
    "expected_next": "expected_next", "segment": "segment", "max_invoice": "max_invoice",
    "min_invoice": "min_invoice", "items_count": "items_count", "quantity": "quantity",
}

SEGMENTS = ["champions", "loyal", "potential", "new", "promising", "cant_lose", "at_risk",
            "hibernating", "lost"]


def customers_cte(f: Filters, settings: dict, ref: date | None) -> tuple[str, list]:
    w, params = f.where()
    sql = f"""
    inv AS (
      SELECT phone, visit_key, sum(item_price) AS t
      FROM sales WHERE phone IS NOT NULL AND {w} GROUP BY phone, visit_key
    ),
    invs AS (
      SELECT phone, {R("max(t)")} AS max_invoice, {R("min(t)")} AS min_invoice,
             {R("percentile_cont(0.5) WITHIN GROUP (ORDER BY t)")} AS median_invoice
      FROM inv GROUP BY phone
    ),
    base AS (
      SELECT phone,
        (array_agg(name ORDER BY invoice_date DESC) FILTER (WHERE name IS NOT NULL))[1] AS name,
        mode() WITHIN GROUP (ORDER BY branch) AS branch,
        mode() WITHIN GROUP (ORDER BY district) AS district,
        {R("sum(item_price)")} AS total_spent,
        count(DISTINCT visit_key) AS visits,
        sum(quantity) AS quantity,
        min(day) AS first_visit,
        max(day) AS last_visit,
        count(DISTINCT day) AS visit_days,
        count(DISTINCT branch) AS branches_count,
        mode() WITHIN GROUP (ORDER BY invoice_type) AS top_sales_type,
        mode() WITHIN GROUP (ORDER BY material_group) AS top_material,
        mode() WITHIN GROUP (ORDER BY item_category) AS top_category,
        mode() WITHIN GROUP (ORDER BY season) AS top_season,
        mode() WITHIN GROUP (ORDER BY coalesce(item_name, item_code)) AS fav_item,
        count(DISTINCT coalesce(item_name, item_code)) AS items_count,
        bool_or(phone_valid) AS phone_valid
      FROM sales WHERE phone IS NOT NULL AND {w}
      GROUP BY phone
    ),
    calc AS (
      SELECT base.*, invs.max_invoice, invs.min_invoice, invs.median_invoice,
        {R("total_spent / nullif(visits, 0)")} AS avg_per_visit,
        CASE WHEN visit_days > 1
             THEN round(((last_visit - first_visit)::numeric / (visit_days - 1)), 1)::float8
        END AS avg_days_between,
        (?::date - last_visit) AS days_since
      FROM base JOIN invs USING (phone)
    ),
    scored AS (
      SELECT calc.*,
        ntile(5) OVER (ORDER BY days_since DESC NULLS FIRST, total_spent) AS r_score,
        ntile(5) OVER (ORDER BY visits, total_spent) AS f_score,
        ntile(5) OVER (ORDER BY total_spent, visits) AS m_score
      FROM calc
    ),
    cust AS (
      SELECT scored.*,
        CASE WHEN days_since IS NULL THEN 'unknown'
             WHEN days_since <= ? THEN 'active'
             WHEN days_since <= ? THEN 'attention'
             ELSE 'inactive' END AS status,
        CASE WHEN days_since IS NULL THEN 3 WHEN days_since <= ? THEN 2
             WHEN days_since <= ? THEN 1 ELSE 0 END AS status_rank,
        total_spent >= ? AS high_value,
        (total_spent >= ? OR visits >= ?) AS loyal,
        CASE
          WHEN r_score >= 4 AND f_score >= 4 THEN 'champions'
          WHEN r_score >= 3 AND f_score >= 3 THEN 'loyal'
          WHEN r_score >= 4 AND f_score <= 1 THEN 'new'
          WHEN r_score >= 4 THEN 'potential'
          WHEN r_score = 3 THEN 'promising'
          WHEN f_score >= 4 AND m_score >= 4 THEN 'cant_lose'
          WHEN f_score >= 3 THEN 'at_risk'
          WHEN r_score = 2 THEN 'hibernating'
          ELSE 'lost' END AS segment,
        CASE WHEN avg_days_between IS NOT NULL
             THEN last_visit + round(avg_days_between)::int END AS expected_next,
        CASE WHEN avg_days_between IS NOT NULL
             THEN round(days_since - avg_days_between)::int END AS overdue_days,
        CASE WHEN avg_days_between IS NULL THEN
               CASE WHEN days_since > ? THEN 'high' WHEN days_since > ? THEN 'medium' ELSE 'low' END
             WHEN days_since > 2 * greatest(avg_days_between, 7) THEN 'high'
             WHEN days_since > 1.5 * greatest(avg_days_between, 7) THEN 'medium'
             ELSE 'low' END AS churn_risk
      FROM scored
    )"""
    s = settings
    tail = [s["active_days"], s["attention_days"], s["active_days"], s["attention_days"],
            s["high_value_spend"], s["loyalty_spend"], s["loyalty_visits"],
            s["attention_days"], s["active_days"]]
    return sql, params + params + [ref] + tail


def phone_query(q: str) -> str | None:
    """'+20 101 234 5678', '1012345678', '0101-234-5678' -> '1012345678' (digits to look for)."""
    raw = re.sub(r"[\s\-+()]", "", q or "")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) < 4 or len(digits) < 0.8 * len(raw):
        return None  # not a phone number - search by name instead
    if digits.startswith("20") and len(digits) >= 12:
        digits = digits[2:]
    return digits.lstrip("0") or digits


# ---- customer statistics are computed ONCE per filter set into a small table, so search,
#      sort and paging are instant (instead of re-aggregating all sales for every keystroke)
_cc_lock = threading.Lock()
_cc_key_locks: dict[str, threading.Lock] = {}
_cc_tables: "OrderedDict[str, tuple[int, object]]" = OrderedDict()
CC_KEEP = 8


def customer_table(f: Filters, settings: dict) -> tuple[str, object]:
    ver = db._version
    name = "cc_" + hashlib.sha1(repr((ver, f.key())).encode()).hexdigest()[:16]
    with _cc_lock:
        if name in _cc_tables:
            _cc_tables.move_to_end(name)
            return name, _cc_tables[name][1]
        klock = _cc_key_locks.setdefault(name, threading.Lock())
    with klock:
        with _cc_lock:
            if name in _cc_tables:
                return name, _cc_tables[name][1]
        cur = db.cursor()
        ref = reference_date(cur, f)
        cte, params = customers_cte(f, settings, ref)
        cur.execute(f"DROP TABLE IF EXISTS {name}")
        cur.execute(f"CREATE UNLOGGED TABLE {name} AS WITH {cte} SELECT * FROM cust", params)
        cur.execute(f"CREATE INDEX ON {name} (phone)")
        cur.execute(f"ANALYZE {name}")
        with _cc_lock:
            _cc_tables[name] = (ver, ref)
            old = [n for n, (v, _) in _cc_tables.items() if v != ver]
            old += [n for n in list(_cc_tables)[:-CC_KEEP] if n not in old]
            for n in old:
                _cc_tables.pop(n, None)
                _cc_key_locks.pop(n, None)
        for n in old:
            try:
                cur.execute(f"DROP TABLE IF EXISTS {n}")
            except Exception:  # noqa: BLE001 - may still be read by a slow request
                pass
        return name, ref


def drop_customer_tables():
    cur = db.cursor()
    for (n,) in cur.execute("SELECT tablename FROM pg_tables WHERE tablename LIKE 'cc\\_%'").fetchall():
        cur.execute(f"DROP TABLE IF EXISTS {n}")
    with _cc_lock:
        _cc_tables.clear()


def _customer_where(q=None, status=None, flag=None, segment=None, churn=None, ref=None):
    conds, params = ["TRUE"], []
    if q:
        digits = phone_query(q)
        if digits:
            conds.append("phone LIKE ?")
            params.append(f"%{digits}%")
        else:
            conds.append("(name ILIKE ? OR phone ILIKE ?)")
            params += [f"%{q.strip()}%", f"%{q.strip()}%"]
    if status:
        conds.append("status = ANY(?)")
        params.append(list(status))
    if segment:
        conds.append("segment = ANY(?)")
        params.append(list(segment))
    if churn:
        conds.append("churn_risk = ANY(?)")
        params.append(list(churn))
    if flag == "high_value":
        conds.append("high_value")
    elif flag == "loyal":
        conds.append("loyal")
    elif flag == "invalid_phone":
        conds.append("NOT phone_valid")
    elif flag == "multi_branch":
        conds.append("branches_count > 1")
    elif flag == "due_soon" and ref:
        conds.append("expected_next BETWEEN ?::date AND ?::date + 7")
        params += [ref, ref]
    elif flag == "overdue":
        conds.append("overdue_days > 0")
    return " AND ".join(conds), params


def list_customers(f: Filters, settings: dict, *, q=None, status=None, flag=None, segment=None,
                   churn=None, sort="priority", desc=True, page=1, page_size=50,
                   limit_all=False) -> dict:
    table, ref = customer_table(f, settings)
    cur = db.cursor()
    where, wp = _customer_where(q, status, flag, segment, churn, ref)
    order = CUSTOMER_SORTS.get(sort, CUSTOMER_SORTS["priority"])
    if sort != "priority":
        order = f"{order} {'DESC' if desc else 'ASC'} NULLS LAST, phone"
    sql = (f"SELECT {', '.join(CUSTOMER_COLUMNS)}, count(*) OVER () AS _total "
           f"FROM {table} WHERE {where} ORDER BY {order}")
    sql += " LIMIT 1048000" if limit_all else \
        f" LIMIT {int(page_size)} OFFSET {int((page - 1) * page_size)}"
    rows = db.rows(cur, sql, wp)
    total = rows[0]["_total"] if rows else 0
    if not rows and page > 1:
        total = cur.execute(f"SELECT count(*) FROM {table} WHERE {where}", wp).fetchone()[0]
    for r in rows:
        r.pop("_total", None)
        r["cid"] = cid(r["phone"])
    return {"rows": rows, "total": total, "reference_date": ref}


def customer_profile(phone: str, f: Filters, settings: dict) -> dict | None:
    # profile = this customer over the selected period (scores relative to all customers)
    table, ref = customer_table(f, settings)
    cur = db.cursor()
    summary = db.one(cur, f"SELECT {', '.join(CUSTOMER_COLUMNS)} FROM {table} WHERE phone = ?",
                     [phone])
    if not summary:
        return None
    summary["cid"] = cid(phone)
    directory = db.one(cur, """SELECT name, first_name, last_name, address, region, city, district,
        area, email, gender, birth_date, registered_at, registered_branch, pos_customer_id, source,
        extra, updated_at FROM customer_directory WHERE phone = ?""", [phone])
    # what the sales lines themselves say about the customer (all time, not only the period)
    sales_info = db.one(cur, """SELECT
        (array_agg(address ORDER BY invoice_date DESC) FILTER (WHERE address IS NOT NULL))[1] AS address,
        array_remove(array_agg(DISTINCT name), NULL) AS names,
        array_remove(array_agg(DISTINCT branch), NULL) AS branches,
        array_remove(array_agg(DISTINCT invoice_type), NULL) AS sales_types,
        min(invoice_date) AS first_purchase, max(invoice_date) AS last_purchase,
        count(DISTINCT visit_key) AS all_time_visits, {} AS all_time_spend
        FROM sales WHERE phone = ?""".format(R("sum(item_price)")), [phone])
    w, wp = f.where()
    base = f"FROM sales WHERE phone = ? AND {w}"
    bp = [phone] + wp
    return {
        "summary": summary,
        "directory": directory,
        "sales_info": sales_info,
        "reference_date": ref,
        "monthly": db.rows(cur, f"""SELECT to_char(date_trunc('month', day), 'YYYY-MM') AS month,
            {R("sum(item_price)")} AS sales, count(DISTINCT visit_key) AS visits
            {base} GROUP BY 1 ORDER BY 1""", bp),
        "top_items": db.rows(cur, f"""SELECT coalesce(item_name, item_code, '-') AS item,
            sum(quantity) AS quantity, {R("sum(item_price)")} AS sales,
            count(DISTINCT visit_key) AS times
            {base} GROUP BY 1 ORDER BY sales DESC LIMIT 15""", bp),
        "branches": db.rows(cur, f"""SELECT coalesce(branch, '-') AS branch,
            {R("sum(item_price)")} AS sales, count(DISTINCT visit_key) AS visits
            {base} GROUP BY 1 ORDER BY sales DESC""", bp),
        "items": db.rows(cur, f"""SELECT coalesce(item_name, item_code, '-') AS item,
            min(item_code) AS code, min(coalesce(item_category, material_group)) AS category,
            sum(quantity) AS quantity, count(DISTINCT visit_key) AS times,
            {R("sum(item_price)")} AS sales, {R("avg(item_price / nullif(quantity, 0))")} AS avg_price,
            min(day) AS first_bought, max(day) AS last_bought
            {base} GROUP BY 1 ORDER BY sales DESC LIMIT 1000""", bp),
        "visits": db.rows(cur, f"""SELECT visit_key, min(invoice_no) AS invoice_no,
            min(invoice_date) AS date,
            min(branch) AS branch, min(invoice_type) AS sales_type, count(*) AS lines,
            {R("sum(item_price)")} AS total,
            string_agg(DISTINCT coalesce(item_name, item_code), ' · ') AS items
            {base} GROUP BY visit_key ORDER BY date DESC LIMIT 200""", bp),
    }


VISIT_LINE_COLUMNS = ["invoice_date", "branch", "invoice_no", "invoice_type", "item_code", "item_name",
                      "item_category", "material_group", "quantity", "item_unit", "item_price"]


def customer_lines(phone: str, f: Filters, visit_key: str | None = None, limit: int = 100000) -> list:
    """The items bought: one row per invoice line (one visit, or all visits in the period)."""
    w, wp = f.where()
    cond, p = (f"phone = ? AND visit_key = ?", [phone, visit_key]) if visit_key else \
        (f"phone = ? AND {w}", [phone] + wp)
    rows = db.rows(db.cursor(), f"""SELECT {', '.join(VISIT_LINE_COLUMNS)},
        round((item_price / nullif(quantity, 0))::numeric, 2)::float8 AS unit_price,
        extra->>'discount' AS discount, extra->>'cashier' AS cashier,
        extra->>'payment_method' AS payment
        FROM sales WHERE {cond} ORDER BY invoice_date DESC, item_name LIMIT {int(limit)}""", p)
    return rows


# ====================================================================== summary
def _kpis(cur, f: Filters) -> dict:
    w, p = f.where()
    r = db.one(cur, f"""SELECT count(DISTINCT phone) AS customers,
        count(DISTINCT visit_key) AS invoices,
        {R("coalesce(sum(item_price), 0)")} AS total_sales,
        sum(quantity) AS quantity, count(*) AS lines
        FROM sales WHERE {w}""", p)
    r["avg_per_customer"] = round(r["total_sales"] / r["customers"], 2) if r["customers"] else 0
    r["avg_invoice"] = round(r["total_sales"] / r["invoices"], 2) if r["invoices"] else 0
    return r


def previous_filters(cur, f: Filters) -> Filters:
    """Same length period right before the selected one (default: last 30 days)."""
    end = f.date_to or reference_date(cur, f)
    start = f.date_from or (end - timedelta(days=29) if end else None)
    if not start or not end:
        return f
    span = (end - start).days + 1
    return replace(f, date_from=start - timedelta(days=span), date_to=start - timedelta(days=1))


def summary(f: Filters, settings: dict) -> dict:
    cur = db.cursor()
    w, p = f.where()
    ref = reference_date(cur, f)
    tasks = {"kpis": lambda: _kpis(db.cursor(), f)}

    if f.date_from and f.date_to:
        prev_f = previous_filters(cur, f)

        def prev():
            r = _kpis(db.cursor(), prev_f)
            r["date_from"], r["date_to"] = prev_f.date_from, prev_f.date_to
            return r
        tasks["previous"] = prev

    if f.date_from:
        aw, ap = f.scope_only().where()
        tasks["new_customers"] = lambda: db.cursor().execute(f"""
            SELECT count(*) FROM (SELECT phone FROM sales WHERE phone IS NOT NULL AND {aw}
              GROUP BY phone HAVING min(day) >= ?) n
            WHERE phone IN (SELECT DISTINCT phone FROM sales WHERE {w})""",
            ap + [f.date_from] + p).fetchone()[0]

    def top(col):
        return lambda: (db.cursor().execute(f"""SELECT {col}, sum(item_price) s FROM sales
            WHERE {w} AND {col} IS NOT NULL GROUP BY 1 ORDER BY s DESC LIMIT 1""", p).fetchone()
            or [None])[0]

    top_keys = [("top_branch", "branch"), ("top_season", "season"),
                ("top_sales_type", "invoice_type"), ("top_material", "material_group"),
                ("top_category", "item_category"), ("top_district", "district"),
                ("top_item", "item_name")]
    for k, c in top_keys:
        tasks[k] = top(c)

    def segments():
        table, _ = customer_table(f, settings)
        return db.one(db.cursor(), f"""SELECT
        count(*) FILTER (WHERE status='active') AS active,
        count(*) FILTER (WHERE status='attention') AS attention,
        count(*) FILTER (WHERE status='inactive') AS inactive,
        count(*) FILTER (WHERE high_value) AS high_value,
        count(*) FILTER (WHERE loyal) AS loyal,
        count(*) FILTER (WHERE NOT phone_valid) AS invalid_phone FROM {table}""")
    tasks["segments"] = segments
    tasks["monthly"] = q_rows(f"""SELECT to_char(date_trunc('month', day), 'YYYY-MM') AS month,
        {R("sum(item_price)")} AS sales, count(DISTINCT phone) AS customers,
        count(DISTINCT visit_key) AS invoices FROM sales WHERE {w} GROUP BY 1 ORDER BY 1""", p)
    tasks["by_branch"] = q_rows(f"""SELECT coalesce(branch, '-') AS branch,
        {R("sum(item_price)")} AS sales, count(DISTINCT phone) AS customers,
        count(DISTINCT visit_key) AS invoices,
        {R("sum(item_price) / nullif(count(DISTINCT phone), 0)")} AS avg_per_customer
        FROM sales WHERE {w} GROUP BY 1 ORDER BY sales DESC""", p)
    tasks["by_type"] = q_rows(f"""SELECT coalesce(invoice_type, '-') AS sales_type,
        {R("sum(item_price)")} AS sales, count(DISTINCT visit_key) AS invoices
        FROM sales WHERE {w} GROUP BY 1 ORDER BY sales DESC""", p)
    tasks["by_season"] = q_rows(f"""SELECT season, {R("sum(item_price)")} AS sales,
        count(DISTINCT visit_key) AS invoices FROM sales WHERE {w} AND season IS NOT NULL
        GROUP BY 1""", p)
    tasks["top_items"] = q_rows(f"""SELECT coalesce(item_name, item_code) AS item,
        {R("sum(item_price)")} AS sales, sum(quantity) AS quantity,
        count(DISTINCT phone) AS customers FROM sales
        WHERE {w} AND coalesce(item_name, item_code) IS NOT NULL
        GROUP BY 1 ORDER BY sales DESC LIMIT 15""", p)

    r = parallel(tasks)
    r["by_season"].sort(
        key=lambda x: SEASON_ORDER.index(x["season"]) if x["season"] in SEASON_ORDER else 9)
    return {"kpis": r["kpis"], "previous": r.get("previous"),
            "new_customers": r.get("new_customers"),
            "insights": {k: r[k] for k, _ in top_keys}, "segments": r["segments"],
            "monthly": r["monthly"], "by_branch": r["by_branch"], "by_type": r["by_type"],
            "by_season": r["by_season"], "top_items": r["top_items"], "reference_date": ref}


# ====================================================================== smart insights
def _customer_health(f: Filters, settings: dict, ref) -> dict:
    """RFM / churn / due / pareto from ONE materialised customer table."""
    table, _ = customer_table(f, settings)
    cur = db.cursor()
    if True:
        rfm = db.rows(cur, f"""SELECT segment, count(*) AS customers,
            {R("sum(total_spent)")} AS sales,
            {R("100 * sum(total_spent) / nullif(sum(sum(total_spent)) OVER (), 0)")} AS share,
            {R("avg(total_spent)")} AS avg_spend, round(avg(visits), 1)::float8 AS avg_visits,
            round(avg(days_since))::int AS avg_days_since
            FROM {table} GROUP BY segment""")
        rfm.sort(key=lambda r: SEGMENTS.index(r["segment"]) if r["segment"] in SEGMENTS else 99)
        churn = db.rows(cur, f"""SELECT churn_risk, count(*) AS customers,
            {R("sum(total_spent)")} AS sales, {R("sum(avg_per_visit)")} AS value_per_visit
            FROM {table} GROUP BY churn_risk""")
        directory = db.one(cur, f"""SELECT count(*) AS listed,
            count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM {table} c WHERE c.phone = d.phone))
              AS never_bought
            FROM customer_directory d""")
        due = db.one(cur, f"""SELECT
            count(*) FILTER (WHERE expected_next BETWEEN ?::date AND ?::date + 7) AS due_soon,
            count(*) FILTER (WHERE overdue_days > 0) AS overdue,
            count(*) FILTER (WHERE branches_count > 1) AS multi_branch,
            count(*) AS customers FROM {table}""", [ref, ref])
        pareto = db.one(cur, f"""WITH t AS (
              SELECT total_spent, ntile(5) OVER (ORDER BY total_spent DESC) AS q FROM {table})
            SELECT {R("100 * sum(total_spent) FILTER (WHERE q = 1) / nullif(sum(total_spent), 0)")}
                   AS top20_share,
                   {R("100 * sum(total_spent) FILTER (WHERE q = 5) / nullif(sum(total_spent), 0)")}
                   AS bottom20_share FROM t""")
    return {"rfm": rfm, "churn": churn, "due": due, "pareto": pareto, "directory": directory}


def insights(f: Filters, settings: dict) -> dict:
    cur = db.cursor()
    w, p = f.where()
    ref = reference_date(cur, f)
    sw, sp = f.scope_only().where()
    prev = previous_filters(cur, f)
    cur_f = f if (f.date_from and f.date_to) else replace(
        f, date_from=prev.date_to + timedelta(days=1) if prev.date_to else None, date_to=ref)
    cw, cwp = cur_f.where()
    pw, pwp = prev.where()

    tasks = {
        "health": lambda: _customer_health(f, settings, ref),
        # cohort retention: month of first purchase (in the selected scope) vs later months
        "cohorts_raw": q_rows(f"""
            WITH m AS (SELECT DISTINCT phone, date_trunc('month', day)::date AS month
                       FROM sales WHERE phone IS NOT NULL AND {w}),
                 first AS (SELECT phone, min(month) AS cohort FROM m GROUP BY phone),
                 c AS (SELECT f.cohort, ((extract(year FROM m.month) - extract(year FROM f.cohort)) * 12
                              + extract(month FROM m.month) - extract(month FROM f.cohort))::int AS k,
                              count(*) AS n
                       FROM m JOIN first f USING (phone) GROUP BY 1, 2)
            SELECT to_char(cohort, 'YYYY-MM') AS cohort, k, n FROM c
            WHERE cohort >= (SELECT max(cohort) FROM first) - interval '11 months' AND k <= 11
            ORDER BY cohort, k""", p),
        # products bought together (market basket)
        "basket": q_rows(f"""
            WITH v AS (SELECT DISTINCT visit_key, coalesce(item_name, item_code) AS item
                       FROM sales WHERE {w} AND coalesce(item_name, item_code) IS NOT NULL),
                 small AS (SELECT visit_key FROM v GROUP BY visit_key
                           HAVING count(*) BETWEEN 2 AND 40),
                 cnt AS (SELECT item, count(*) AS c FROM v GROUP BY item),
                 top AS (SELECT item FROM cnt ORDER BY c DESC LIMIT 300),
                 vt AS (SELECT v.* FROM v JOIN small USING (visit_key) JOIN top USING (item)),
                 tot AS (SELECT count(DISTINCT visit_key)::float8 AS n FROM v),
                 pr AS (SELECT a.item AS item_a, b.item AS item_b, count(*) AS together
                        FROM vt a JOIN vt b ON a.visit_key = b.visit_key AND a.item < b.item
                        GROUP BY 1, 2 HAVING count(*) >= 3)
            SELECT item_a, item_b, together,
                   {R("100.0 * together / ca.c")} AS confidence_a_b,
                   {R("100.0 * together / cb.c")} AS confidence_b_a,
                   {R("together * tot.n / (ca.c * cb.c)")} AS lift
            FROM pr JOIN cnt ca ON ca.item = pr.item_a JOIN cnt cb ON cb.item = pr.item_b, tot
            ORDER BY (together * tot.n / (ca.c * cb.c)) * ln(together + 1) DESC LIMIT 25""", p),
        # when do customers come? (day of week x hour)
        "heatmap": q_rows(f"""SELECT extract(isodow FROM invoice_date)::int AS dow,
            extract(hour FROM invoice_date)::int AS hour, count(DISTINCT visit_key) AS visits,
            {R("sum(item_price)")} AS sales
            FROM sales WHERE {w} GROUP BY 1, 2""", p),
        # new vs returning customers per month
        "new_vs_returning": q_rows(f"""
            WITH first AS (SELECT phone, date_trunc('month', min(day)) AS fm FROM sales
                           WHERE phone IS NOT NULL AND {sw} GROUP BY phone),
                 m AS (SELECT DISTINCT phone, date_trunc('month', day) AS month FROM sales
                       WHERE phone IS NOT NULL AND {w})
            SELECT to_char(m.month, 'YYYY-MM') AS month,
                   count(*) FILTER (WHERE first.fm = m.month) AS new,
                   count(*) FILTER (WHERE first.fm < m.month) AS returning
            FROM m JOIN first USING (phone) GROUP BY 1 ORDER BY 1""", sp + p),
        # branch growth vs the previous period
        "branch_growth": q_rows(f"""
            WITH c AS (SELECT coalesce(branch, '-') AS branch, sum(item_price) AS s,
                              count(DISTINCT phone) AS cu FROM sales WHERE {cw} GROUP BY 1),
                 pv AS (SELECT coalesce(branch, '-') AS branch, sum(item_price) AS s,
                               count(DISTINCT phone) AS cu FROM sales WHERE {pw} GROUP BY 1)
            SELECT coalesce(c.branch, pv.branch) AS branch,
                   {R("coalesce(c.s, 0)")} AS sales, {R("coalesce(pv.s, 0)")} AS prev_sales,
                   coalesce(c.cu, 0) AS customers, coalesce(pv.cu, 0) AS prev_customers,
                   {R("100 * (coalesce(c.s, 0) - pv.s) / nullif(pv.s, 0)")} AS sales_change,
                   {R("100 * (coalesce(c.cu, 0) - pv.cu)::numeric / nullif(pv.cu, 0)")}
                     AS customers_change
            FROM c FULL JOIN pv ON c.branch = pv.branch
            ORDER BY sales DESC""", cwp + pwp),
    }
    r = parallel(tasks)

    cohorts: dict[str, dict] = {}
    for row in r["cohorts_raw"]:
        c = cohorts.setdefault(row["cohort"], {"cohort": row["cohort"], "size": 0,
                                               "retention": []})
        if row["k"] == 0:
            c["size"] = row["n"]
        c["retention"].append({"k": row["k"], "n": row["n"]})
    for c in cohorts.values():
        c["retention"] = [{"k": x["k"],
                           "pct": round(100 * x["n"] / c["size"], 1) if c["size"] else 0}
                          for x in c["retention"]]

    res = {"reference_date": ref, **r["health"], "cohorts": list(cohorts.values()),
           "basket": r["basket"], "heatmap": r["heatmap"],
           "has_time": any(h["hour"] != 0 for h in r["heatmap"]),
           "new_vs_returning": r["new_vs_returning"], "branch_growth": r["branch_growth"],
           "periods": {"current": [cur_f.date_from, cur_f.date_to],
                       "previous": [prev.date_from, prev.date_to]}}
    res["alerts"] = alerts(res, settings)
    return res


def alerts(ins: dict, settings: dict) -> list[dict]:
    """Rule-based 'smart alerts' in English and Arabic."""
    out = []

    def add(level, en, ar):
        out.append({"level": level, "en": en, "ar": ar})

    for g in ins["branch_growth"]:
        ch = g["sales_change"]
        if ch is not None and ch <= -15:
            add("danger", f"Sales in {g['branch']} dropped {abs(ch):.0f}% vs the previous period.",
                f"مبيعات فرع {g['branch']} انخفضت {abs(ch):.0f}% مقارنة بالفترة السابقة.")
        elif ch is not None and ch >= 20:
            add("success", f"Sales in {g['branch']} grew {ch:.0f}% vs the previous period.",
                f"مبيعات فرع {g['branch']} زادت {ch:.0f}% مقارنة بالفترة السابقة.")
        cc = g["customers_change"]
        if cc is not None and cc <= -15:
            add("warning", f"{g['branch']} lost {abs(cc):.0f}% of its active customers.",
                f"فرع {g['branch']} فقد {abs(cc):.0f}% من عملائه النشطين.")

    seg = {r["segment"]: r for r in ins["rfm"]}
    for key, en, ar in [
        ("cant_lose", "high-spending customers stopped coming (Can't lose them) - call them first.",
         "عميل من كبار العملاء توقفوا عن الشراء - اتصل بهم أولاً."),
        ("at_risk", "frequent customers are at risk of leaving - send them an offer.",
         "عميل دائم معرضون للفقد - أرسل لهم عرضاً."),
    ]:
        r = seg.get(key)
        if r and r["customers"]:
            add("warning", f"{r['customers']} {en} ({r['sales']:,.0f} EGP lifetime).",
                f"{r['customers']} {ar} ({r['sales']:,.0f} جنيه).")

    churn = {r["churn_risk"]: r for r in ins["churn"]}
    hi = churn.get("high")
    if hi and hi["customers"]:
        add("danger", f"{hi['customers']} customers are well past their usual visit rhythm "
                      f"(high churn risk).",
            f"{hi['customers']} عميل تأخروا كثيراً عن موعد زيارتهم المعتاد (خطر فقد مرتفع).")
    due = ins["due"]
    if due and due["due_soon"]:
        add("info", f"{due['due_soon']} customers are expected to visit in the next 7 days - "
                    f"a reminder message can lock it in.",
            f"{due['due_soon']} عميل متوقع زيارتهم خلال 7 أيام - رسالة تذكير تضمن الزيارة.")
    pareto = ins["pareto"]
    if pareto and pareto["top20_share"]:
        add("info", f"Top 20% of customers bring {pareto['top20_share']:.0f}% of sales.",
            f"أفضل 20% من العملاء يحققون {pareto['top20_share']:.0f}% من المبيعات.")
    strong = [b for b in ins["basket"] if (b["lift"] or 0) >= 1.2]
    if strong:
        b = strong[0]
        add("info", f"'{b['item_a']}' and '{b['item_b']}' are often bought together "
                    f"(lift {b['lift']:.1f}) - consider a bundle.",
            f"'{b['item_a']}' و '{b['item_b']}' يُشتريان معاً كثيراً (معامل {b['lift']:.1f}) - "
            f"فكّر في عرض مجمّع.")
    return out


# ====================================================================== products
PRODUCT_SORTS = {"sales", "quantity", "invoices", "customers", "repeat_rate", "avg_price", "item",
                 "last_sold", "share"}


def products(f: Filters, *, q=None, sort="sales", desc=True, page=1, page_size=50,
             limit_all=False) -> dict:
    """Per product: sales, units, invoices, unique buyers, repeat buyers, price, best branch."""
    cur = db.cursor()
    w, p = f.where()
    cond, cp = "", []
    if q:
        cond = "WHERE item ILIKE ? OR code ILIKE ? OR category ILIKE ?"
        cp = [f"%{q}%"] * 3
    sort = sort if sort in PRODUCT_SORTS else "sales"
    sql = f"""
      WITH s AS (SELECT coalesce(item_name, item_code) AS item, * FROM sales
                 WHERE {w} AND coalesce(item_name, item_code) IS NOT NULL),
           per_c AS (SELECT item, phone, count(DISTINCT visit_key) AS n FROM s
                     WHERE phone IS NOT NULL GROUP BY 1, 2),
           rep AS (SELECT item, count(*) AS buyers, count(*) FILTER (WHERE n >= 2) AS repeat_buyers,
                          round(avg(n), 2)::float8 AS times_per_buyer
                   FROM per_c GROUP BY item),
           agg AS (SELECT item, min(item_code) AS code, mode() WITHIN GROUP (ORDER BY item_category)
                          AS category, mode() WITHIN GROUP (ORDER BY material_group) AS material_group,
                          {R("sum(item_price)")} AS sales, sum(quantity) AS quantity,
                          count(DISTINCT visit_key) AS invoices,
                          {R("sum(item_price) / nullif(sum(quantity), 0)")} AS avg_price,
                          mode() WITHIN GROUP (ORDER BY branch) AS top_branch,
                          min(day) AS first_sold, max(day) AS last_sold
                   FROM s GROUP BY item),
           t AS (SELECT agg.*, coalesce(rep.buyers, 0) AS customers,
                        coalesce(rep.repeat_buyers, 0) AS repeat_buyers, rep.times_per_buyer,
                        {R("100.0 * rep.repeat_buyers / nullif(rep.buyers, 0)")} AS repeat_rate,
                        {R("100 * sales / nullif(sum(sales) OVER (), 0)")} AS share
                 FROM agg LEFT JOIN rep USING (item))
      SELECT *, count(*) OVER () AS _total FROM t {cond}
      ORDER BY {sort} {'DESC' if desc else 'ASC'} NULLS LAST, item"""
    sql += " LIMIT 1048000" if limit_all else \
        f" LIMIT {int(page_size)} OFFSET {int((page - 1) * page_size)}"
    rows = db.rows(cur, sql, p + cp)
    total = rows[0]["_total"] if rows else 0
    for r in rows:
        r.pop("_total", None)
    by_category = db.rows(cur, f"""SELECT coalesce(item_category, material_group, '-') AS category,
        {R("sum(item_price)")} AS sales, count(DISTINCT coalesce(item_name, item_code)) AS products,
        count(DISTINCT phone) AS customers FROM sales WHERE {w}
        GROUP BY 1 ORDER BY sales DESC LIMIT 30""", p) if page == 1 and not limit_all else []
    return {"rows": rows, "total": total, "by_category": by_category}


# ====================================================================== customer base (lists)
DIRECTORY_SORTS = {"name", "phone", "region", "city", "district", "area", "total_spent", "visits",
                   "last_visit", "updated_at"}


def _directory_scope(allowed_branches) -> tuple[str, list]:
    """Branch-limited users only see listed customers who bought in their branches."""
    if not allowed_branches:
        return "TRUE", []
    return "d.phone IN (SELECT phone FROM sales WHERE branch = ANY(?))", [list(allowed_branches)]


def directory_summary(allowed_branches=None) -> dict:
    cur = db.cursor()
    scope, sp = _directory_scope(allowed_branches)
    base = f"""WITH b AS (SELECT DISTINCT phone FROM sales WHERE phone IS NOT NULL),
               d AS (SELECT d.*, (b.phone IS NOT NULL) AS bought FROM customer_directory d
                     LEFT JOIN b USING (phone) WHERE {scope})"""
    k = db.one(cur, f"""{base} SELECT count(*) AS total,
        count(*) FILTER (WHERE phone_valid) AS valid_phones,
        count(*) FILTER (WHERE NOT phone_valid) AS invalid_phones,
        count(*) FILTER (WHERE name IS NOT NULL) AS with_name,
        count(*) FILTER (WHERE address IS NOT NULL) AS with_address,
        count(*) FILTER (WHERE district IS NOT NULL) AS with_district,
        count(*) FILTER (WHERE city IS NOT NULL) AS with_city,
        count(*) FILTER (WHERE email IS NOT NULL) AS with_email,
        count(*) FILTER (WHERE bought) AS bought,
        count(*) FILTER (WHERE NOT bought) AS never_bought,
        max(updated_at) AS updated_at FROM d""", sp)

    def by(col, limit=30):
        return db.rows(cur, f"""{base} SELECT coalesce({col}, '—') AS label, count(*) AS customers,
            count(*) FILTER (WHERE bought) AS bought,
            {R("100.0 * count(*) / nullif(sum(count(*)) OVER (), 0)")} AS share
            FROM d GROUP BY 1 ORDER BY customers DESC LIMIT {limit}""", sp)

    registrations = db.rows(cur, f"""{base} SELECT to_char(date_trunc('month', registered_at), 'YYYY-MM') AS month,
        count(*) AS customers FROM d WHERE registered_at IS NOT NULL GROUP BY 1 ORDER BY 1""", sp)
    reg_branch = db.rows(cur, f"""{base} SELECT coalesce(registered_branch, '—') AS label,
        count(*) AS customers,
        count(*) FILTER (WHERE registered_at >= now() - interval '30 days') AS last_30_days
        FROM d WHERE source = 'pos' GROUP BY 1 ORDER BY customers DESC""", sp)
    return {"kpis": k, "registrations": registrations[-24:], "by_registered_branch": reg_branch,
            "by_region": by("region"), "by_city": by("city"), "by_district": by("district"),
            "by_area": by("area"), "by_gender": by("gender", 10),
            "sales_rows": cur.execute("SELECT count(*) FROM sales").fetchone()[0]}


def directory_list(allowed_branches=None, *, q=None, region=None, city=None, district=None,
                   bought=None, invalid=False, sort="name", desc=False, page=1, page_size=50,
                   limit_all=False) -> dict:
    cur = db.cursor()
    scope, sp = _directory_scope(allowed_branches)
    conds, p = [scope], list(sp)
    if q:
        conds.append("(d.phone ILIKE ? OR d.name ILIKE ? OR d.address ILIKE ? OR d.district ILIKE ? "
                     "OR d.city ILIKE ? OR d.area ILIKE ?)")
        p += [f"%{q}%"] * 6
    for col, v in (("region", region), ("city", city), ("district", district)):
        if v:
            conds.append(f"d.{col} = ANY(?)")
            p.append(list(v))
    if bought is True:
        conds.append("s.phone IS NOT NULL")
    elif bought is False:
        conds.append("s.phone IS NULL")
    if invalid:
        conds.append("NOT d.phone_valid")
    sort = sort if sort in DIRECTORY_SORTS else "name"
    sql = f"""WITH s AS (SELECT phone, {R("sum(item_price)")} AS total_spent,
                   count(DISTINCT visit_key) AS visits, max(day) AS last_visit
                 FROM sales WHERE phone IS NOT NULL GROUP BY phone)
        SELECT d.phone, d.name, d.region, d.city, d.district, d.area, d.address, d.email,
               d.phone_valid, d.updated_at, s.total_spent, s.visits, s.last_visit,
               (s.phone IS NOT NULL) AS bought, count(*) OVER () AS _total
        FROM customer_directory d LEFT JOIN s USING (phone)
        WHERE {" AND ".join(conds)}
        ORDER BY {sort} {"DESC" if desc else "ASC"} NULLS LAST, d.phone"""
    sql += " LIMIT 1048000" if limit_all else \
        f" LIMIT {int(page_size)} OFFSET {int((page - 1) * page_size)}"
    rows = db.rows(cur, sql, p)
    total = rows[0]["_total"] if rows else 0
    for r in rows:
        r.pop("_total", None)
        r["cid"] = cid(r["phone"]) if r["bought"] else None
    filters = {c: [x[0] for x in cur.execute(
        f"SELECT DISTINCT {c} FROM customer_directory WHERE {c} IS NOT NULL ORDER BY 1 LIMIT 500"
    ).fetchall()] for c in ("region", "city", "district")} if page == 1 and not limit_all else None
    return {"rows": rows, "total": total, "filters": filters}


# ====================================================================== area
def area(f: Filters, min_customers: int = 5) -> dict:
    cur = db.cursor()
    w, p = f.where()
    districts = db.rows(cur, f"""SELECT district, {R("sum(item_price)")} AS sales,
        count(DISTINCT phone) AS customers, count(DISTINCT visit_key) AS invoices,
        {R("sum(item_price) / nullif(count(DISTINCT phone), 0)")} AS spend_per_customer,
        {R("100 * sum(item_price) / nullif(sum(sum(item_price)) OVER (), 0)")} AS share
        FROM sales WHERE {w} GROUP BY 1 ORDER BY sales DESC""", p)
    branch_district = db.rows(cur, f"""SELECT coalesce(branch, '-') AS branch, district,
        {R("sum(item_price)")} AS sales, count(DISTINCT phone) AS customers,
        {R("sum(item_price) / nullif(count(DISTINCT phone), 0)")} AS spend_per_customer,
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
        digits = phone_query(q)
        full = normalize_egy_phone(q)
        if digits and is_valid_egy_mobile(full):
            w += " AND phone = ?"            # indexed: instant
            p = p + [full]
        elif digits:
            w += " AND (phone LIKE ? OR invoice_no ILIKE ?)"
            p = p + [f"%{digits}%", f"%{q.strip()}%"]
        else:
            w += " AND (name ILIKE ? OR item_name ILIKE ? OR invoice_no ILIKE ?)"
            p = p + [f"%{q.strip()}%"] * 3
    sort = sort if sort in SALES_SORTS else "invoice_date"
    agg = db.one(cur, f"SELECT count(*) AS total, {R('coalesce(sum(item_price), 0)')} AS sales "
                      f"FROM sales WHERE {w}", p)
    sql = (f"SELECT {', '.join(SALES_COLUMNS)} FROM sales WHERE {w} "
           f"ORDER BY {sort} {'DESC' if desc else 'ASC'} NULLS LAST")
    sql += " LIMIT 1048000" if limit_all else \
        f" LIMIT {int(page_size)} OFFSET {int((page - 1) * page_size)}"
    rows = db.rows(cur, sql, p)
    for r in rows:
        r["cid"] = cid(r["phone"]) if r["phone"] else None
    return {"rows": rows, "total": agg["total"], "sales": agg["sales"]}


# ====================================================================== meta
def meta(allowed_branches: list[str] | None) -> dict:
    cur = db.cursor()
    w, p = Filters(allowed_branches=allowed_branches).where()

    def distinct(col):
        return [r[0] for r in cur.execute(
            f"SELECT DISTINCT {col} FROM sales WHERE {w} AND {col} IS NOT NULL ORDER BY 1", p
        ).fetchall()]

    rng = cur.execute(f"SELECT min(day), max(day), count(*) FROM sales WHERE {w}", p).fetchone()
    directory = cur.execute("SELECT count(*) FROM customer_directory").fetchone()[0]
    return {"directory_customers": directory,
            "branches": distinct("branch"), "types": distinct("invoice_type"),
            "districts": distinct("district"), "seasons": SEASON_ORDER,
            "date_min": rng[0], "date_max": rng[1], "rows": rng[2]}


# ====================================================================== live POS monitor
def live(allowed_branches=None, branch: str | None = None) -> dict:
    """Today's POS activity (Cairo time): totals, per branch status, hourly curve, live feed."""
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo
    now = _dt.now(ZoneInfo("Africa/Cairo")).replace(tzinfo=None)
    today = now.date()
    yday = today - timedelta(days=1)
    cur = db.cursor()

    conds, p = ["source = 'pos'"], []
    if allowed_branches:
        conds.append("branch = ANY(?)")
        p.append(list(allowed_branches))
    if branch:
        conds.append("branch = ?")
        p.append(branch)
    w = " AND ".join(conds)

    def kpis(day, until=None):
        extra, ep = ("AND invoice_date <= ?", [until]) if until else ("", [])
        return db.one(cur, f"""SELECT {R("coalesce(sum(item_price), 0)")} AS sales,
            count(DISTINCT ext_key) AS invoices, count(DISTINCT phone) AS customers,
            count(*) AS lines, max(invoice_date) AS last_invoice
            FROM sales WHERE {w} AND day = ? {extra}""", p + [day] + ep)

    k = kpis(today)
    k["avg_invoice"] = round(k["sales"] / k["invoices"], 2) if k["invoices"] else 0
    same_time_yday = kpis(yday, now - timedelta(days=1))

    rw, rp = "source = 'pos'", []
    if branch:
        rw += " AND registered_branch = ?"
        rp.append(branch)
    k["new_customers"] = cur.execute(
        f"SELECT count(*) FROM customer_directory WHERE {rw} AND registered_at >= ? AND registered_at < ?",
        rp + [today, today + timedelta(days=1)]).fetchone()[0]

    hourly = db.rows(cur, f"""SELECT extract(hour FROM invoice_date)::int AS hour,
        {R("sum(item_price) FILTER (WHERE day = ?)")} AS today,
        {R("sum(item_price) FILTER (WHERE day = ?)")} AS yesterday,
        count(DISTINCT ext_key) FILTER (WHERE day = ?) AS invoices
        FROM sales WHERE {w} AND day IN (?, ?) GROUP BY 1 ORDER BY 1""",
        [today, yday, today] + p + [today, yday])
    by_hour = {h["hour"]: h for h in hourly}
    hours = [{"hour": f"{h:02d}:00", "today": (by_hour.get(h) or {}).get("today") or 0,
              "yesterday": (by_hour.get(h) or {}).get("yesterday") or 0,
              "invoices": (by_hour.get(h) or {}).get("invoices") or 0}
             for h in range(0, 24) if h <= now.hour or (by_hour.get(h) or {}).get("yesterday")]

    bw, bp = "TRUE", []
    if allowed_branches:
        bw, bp = "branch = ANY(?)", [list(allowed_branches)]
    branches = db.rows(cur, f"""
        WITH t AS (SELECT branch, {R("sum(item_price)")} AS sales, count(DISTINCT ext_key) AS invoices,
                          count(DISTINCT phone) AS customers, max(invoice_date) AS last_invoice
                   FROM sales WHERE source = 'pos' AND day = ? AND {bw} GROUP BY branch),
             y AS (SELECT branch, {R("sum(item_price)")} AS sales FROM sales
                   WHERE source = 'pos' AND day = ? AND invoice_date <= ? AND {bw} GROUP BY branch),
             ever AS (SELECT branch, max(invoice_date) AS last_ever FROM sales
                      WHERE source = 'pos' AND {bw} GROUP BY branch),
             k AS (SELECT branch, max(last_used_at) AS last_seen FROM api_keys
                   WHERE active AND branch IS NOT NULL GROUP BY branch)
        SELECT b.branch, coalesce(t.sales, 0) AS sales, coalesce(t.invoices, 0) AS invoices,
               coalesce(t.customers, 0) AS customers, t.last_invoice, ever.last_ever, k.last_seen,
               coalesce(y.sales, 0) AS yesterday_sales
        FROM (SELECT branch FROM ever UNION SELECT branch FROM k) b
        LEFT JOIN t USING (branch) LEFT JOIN y USING (branch) LEFT JOIN ever USING (branch)
        LEFT JOIN k USING (branch)
        WHERE {"b.branch = ANY(?)" if allowed_branches else "TRUE"}
        ORDER BY sales DESC, b.branch""",
        [today] + bp + [yday, now - timedelta(days=1)] + bp + bp
        + ([list(allowed_branches)] if allowed_branches else []))
    from datetime import datetime as _d2
    for b in branches:
        # last_seen (UTC, from the API key) is converted to Cairo time for display
        seen = b["last_seen"]
        if seen:
            seen = seen.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Africa/Cairo")).replace(tzinfo=None)
            b["last_seen"] = seen
        last = max([x for x in (seen, b["last_invoice"], b["last_ever"]) if x], default=None)
        mins = (now - last).total_seconds() / 60 if isinstance(last, _d2) else None
        b["minutes_since"] = round(mins) if mins is not None else None
        b["state"] = "online" if mins is not None and mins <= 15 else \
            "idle" if mins is not None and mins <= 120 else "offline"
    spark = db.rows(cur, f"""SELECT branch, extract(hour FROM invoice_date)::int AS hour,
        {R("sum(item_price)")} AS sales FROM sales WHERE source = 'pos' AND day = ? AND {bw}
        GROUP BY 1, 2""", [today] + bp)
    for b in branches:
        pts = {x["hour"]: x["sales"] for x in spark if x["branch"] == b["branch"]}
        b["hourly"] = [pts.get(h, 0) for h in range(0, now.hour + 1)]

    feed = db.rows(cur, f"""SELECT ext_key, min(invoice_no) AS invoice_no, min(branch) AS branch,
        min(invoice_date) AS time, min(phone) AS phone, min(name) AS name, count(*) AS lines,
        {R("sum(item_price)")} AS total, min(invoice_type) AS sales_type,
        min(extra->>'cashier') AS cashier, min(extra->>'payment_method') AS payment,
        string_agg(DISTINCT coalesce(item_name, item_code), ' · ') AS items
        FROM sales WHERE {w} AND day >= ?
        GROUP BY ext_key ORDER BY time DESC LIMIT 40""", p + [yday])
    for f in feed:
        f["cid"] = cid(f["phone"]) if f["phone"] else None

    nw, np_ = "source = 'pos' AND registered_at IS NOT NULL", []
    if branch:
        nw += " AND registered_branch = ?"
        np_.append(branch)
    newc = db.rows(cur, f"""SELECT phone, name, registered_branch AS branch, registered_at AS time,
        city, district FROM customer_directory WHERE {nw}
        ORDER BY registered_at DESC LIMIT 15""", np_)

    top_items = db.rows(cur, f"""SELECT coalesce(item_name, item_code) AS item,
        {R("sum(item_price)")} AS sales, sum(quantity) AS quantity FROM sales
        WHERE {w} AND day = ? GROUP BY 1 ORDER BY sales DESC LIMIT 8""", p + [today])

    return {"now": now, "today": today, "kpis": k, "same_time_yesterday": same_time_yday,
            "hourly": hours, "branches": branches, "feed": feed, "new_customers": newc,
            "top_items": top_items,
            "has_pos": bool(cur.execute("SELECT 1 FROM sales WHERE source = 'pos' LIMIT 1").fetchone()
                            or cur.execute("SELECT 1 FROM api_keys LIMIT 1").fetchone())}


# ====================================================================== totals & data check
def filter_totals(f: Filters) -> dict:
    """Totals for the current filters + breakdown by sales type (Customers page summary)."""
    w, p = f.where()
    tasks = {
        "totals": q_one(f"""SELECT count(DISTINCT phone) AS customers, count(DISTINCT visit_key) AS invoices,
            {R("coalesce(sum(item_price), 0)")} AS sales, count(*) AS lines,
            min(day) AS date_from, max(day) AS date_to FROM sales WHERE {w}""", p),
        "by_type": q_rows(f"""SELECT coalesce(invoice_type, '—') AS sales_type,
            count(DISTINCT phone) AS customers, count(DISTINCT visit_key) AS invoices,
            {R("sum(item_price)")} AS sales,
            {R("100 * sum(item_price) / nullif(sum(sum(item_price)) OVER (), 0)")} AS share
            FROM sales WHERE {w} GROUP BY 1 ORDER BY sales DESC NULLS LAST""", p),
    }
    return parallel(tasks)


def data_check() -> dict:
    """Everything that is stored right now - to verify that uploads reached the database."""
    tasks = {
        "totals": q_one(f"""SELECT count(*) AS lines, count(DISTINCT phone) AS customers,
            count(DISTINCT visit_key) AS invoices, {R("coalesce(sum(item_price), 0)")} AS sales,
            min(day) AS date_from, max(day) AS date_to,
            count(*) FILTER (WHERE source = 'pos') AS pos_lines,
            count(*) FILTER (WHERE phone IS NULL) AS lines_without_phone FROM sales"""),
        "directory": q_one("SELECT count(*) AS customers, max(updated_at) AS updated_at FROM customer_directory"),
        "imports": q_rows(f"""SELECT i.id, i.filename, i.kind, i.status, i.mode, i.rows_read,
            i.rows_imported, i.rows_skipped, i.finished_at,
            CASE WHEN i.kind = 'customers'
                 THEN (SELECT count(*) FROM customer_directory d WHERE d.import_id = i.id)
                 ELSE coalesce(s.lines, 0) END AS rows_now,
            s.sales, s.date_from, s.date_to, s.upload_day_lines
            FROM imports i LEFT JOIN (
              SELECT x.import_id, count(*) AS lines, {R("sum(x.item_price)")} AS sales,
                     min(x.day) AS date_from, max(x.day) AS date_to,
                     count(*) FILTER (WHERE x.day = im.created_at::date) AS upload_day_lines
              FROM sales x JOIN imports im ON im.id = x.import_id
              GROUP BY x.import_id) s ON s.import_id = i.id
            WHERE i.status IN ('done', 'running') ORDER BY i.id DESC LIMIT 200"""),
        "by_month": q_rows(f"""SELECT to_char(date_trunc('month', day), 'YYYY-MM') AS month, count(*) AS lines,
            count(DISTINCT phone) AS customers, count(DISTINCT visit_key) AS invoices,
            {R("sum(item_price)")} AS sales FROM sales GROUP BY 1 ORDER BY 1 DESC"""),
        "by_type": q_rows(f"""SELECT coalesce(invoice_type, '—') AS sales_type, count(*) AS lines,
            count(DISTINCT phone) AS customers, {R("sum(item_price)")} AS sales
            FROM sales GROUP BY 1 ORDER BY sales DESC NULLS LAST"""),
        "by_branch": q_rows(f"""SELECT coalesce(branch, '—') AS branch, count(*) AS lines,
            count(DISTINCT phone) AS customers, {R("sum(item_price)")} AS sales,
            min(day) AS date_from, max(day) AS date_to
            FROM sales GROUP BY 1 ORDER BY sales DESC NULLS LAST"""),
    }
    return parallel(tasks)
