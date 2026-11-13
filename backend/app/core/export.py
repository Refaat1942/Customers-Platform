"""Excel exports with English or Arabic headers."""

import io
from datetime import date, datetime

import pandas as pd

LABELS = {
    "phone": ("Phone", "رقم الموبايل"),
    "name": ("Customer Name", "اسم العميل"),
    "branch": ("Branch", "الفرع"),
    "district": ("District", "المنطقة"),
    "total_spent": ("Total Spend", "إجمالي المشتريات"),
    "visits": ("Visits", "عدد الزيارات"),
    "quantity": ("Quantity", "الكمية"),
    "first_visit": ("First Visit", "أول زيارة"),
    "last_visit": ("Last Visit", "آخر زيارة"),
    "days_since": ("Days Since Last Visit", "أيام منذ آخر زيارة"),
    "avg_per_visit": ("Avg Spend / Visit", "متوسط الزيارة"),
    "avg_days_between": ("Avg Days Between Visits", "متوسط الأيام بين الزيارات"),
    "top_sales_type": ("Top Sales Type", "نوع البيع الأكثر"),
    "top_material": ("Top Material Group", "مجموعة المواد الأكثر"),
    "top_category": ("Top Category", "الفئة الأكثر"),
    "top_season": ("Top Season", "الموسم الأكثر"),
    "status": ("Status", "الحالة"),
    "action": ("Recommended Action", "الإجراء المقترح"),
    "high_value": ("High Value", "قيمة عالية"),
    "loyal": ("Loyal", "عميل وفي"),
    "phone_valid": ("Valid Phone", "رقم صحيح"),
    "invoice_date": ("Date", "التاريخ"),
    "invoice_no": ("Invoice No", "رقم الفاتورة"),
    "invoice_type": ("Sales Type", "نوع البيع"),
    "item_code": ("Item Code", "كود الصنف"),
    "item_name": ("Item", "الصنف"),
    "material_group": ("Material Group", "مجموعة المواد"),
    "item_category": ("Category", "الفئة"),
    "item_unit": ("Unit", "الوحدة"),
    "item_price": ("Amount", "القيمة"),
    "sales": ("Sales", "المبيعات"),
    "customers": ("Customers", "العملاء"),
    "invoices": ("Invoices", "الفواتير"),
    "spend_per_customer": ("Spend / Customer", "الإنفاق لكل عميل"),
    "avg_per_customer": ("Avg / Customer", "متوسط لكل عميل"),
    "share": ("Share %", "النسبة %"),
    "rank": ("Rank", "الترتيب"),
    "month": ("Month", "الشهر"),
    "sales_type": ("Sales Type", "نوع البيع"),
    "season": ("Season", "الموسم"),
    "item": ("Item", "الصنف"),
    "metric": ("Metric", "المؤشر"),
    "trend": ("Spend Trend", "اتجاه الإنفاق"),
    "trend_pct": ("Trend %", "التغير %"),
    "spend_90": ("Spend Last 90 Days", "إنفاق آخر 90 يوم"),
    "spend_prev_90": ("Spend Previous 90 Days", "إنفاق الـ 90 يوم السابقة"),
    "purchases": ("Times Bought", "مرات الشراء"),
    "cycle_days": ("Refill Every (days)", "يعيد الشراء كل (يوم)"),
    "due_date": ("Due Date", "موعد إعادة الشراء"),
    "days_late": ("Days Late", "أيام التأخير"),
    "refill_status": ("Refill Status", "حالة إعادة الشراء"),
    "avg_qty": ("Usual Qty", "الكمية المعتادة"),
    "avg_amount": ("Usual Amount", "القيمة المعتادة"),
    "lifetime_amount": ("Total Spent on Item", "إجمالي إنفاقه على الصنف"),
    "unit_price": ("Unit Price", "سعر الوحدة"),
    "first_bought": ("First Bought", "أول شراء"),
    "last_bought": ("Last Bought", "آخر شراء"),
    "region": ("Region", "المحافظة"),
    "city": ("City", "المدينة"),
    "area": ("Area", "المنطقة الفرعية"),
    "address": ("Address", "العنوان"),
    "email": ("Email", "البريد"),
    "bought": ("Has Purchases", "له مشتريات"),
    "updated_at": ("Updated", "آخر تحديث"),
    "max_invoice": ("Highest Invoice", "أعلى فاتورة"),
    "min_invoice": ("Lowest Invoice", "أقل فاتورة"),
    "median_invoice": ("Typical Invoice", "الفاتورة المعتادة"),
    "items_count": ("Different Products", "عدد الأصناف المختلفة"),
    "fav_item": ("Favourite Product", "الصنف المفضل"),
    "code": ("Code", "الكود"),
    "category": ("Category", "الفئة"),
    "avg_price": ("Avg Price", "متوسط السعر"),
    "repeat_buyers": ("Repeat Buyers", "عملاء متكررون"),
    "repeat_rate": ("Repeat Rate %", "نسبة التكرار %"),
    "times_per_buyer": ("Times / Buyer", "مرات لكل عميل"),
    "top_branch": ("Top Branch", "الفرع الأعلى"),
    "first_sold": ("First Sold", "أول بيع"),
    "last_sold": ("Last Sold", "آخر بيع"),
    "products": ("Products", "الأصناف"),
    "segment": ("RFM Segment", "شريحة العميل"),
    "churn_risk": ("Churn Risk", "خطر الفقد"),
    "expected_next": ("Expected Next Visit", "الزيارة المتوقعة"),
    "overdue_days": ("Days Overdue", "أيام التأخير"),
    "item_a": ("Item A", "الصنف أ"),
    "item_b": ("Item B", "الصنف ب"),
    "together": ("Bought Together", "مرات الشراء معاً"),
    "confidence_a_b": ("A -> B %", "أ ← ب %"),
    "confidence_b_a": ("B -> A %", "ب ← أ %"),
    "lift": ("Lift", "معامل الارتباط"),
    "avg_spend": ("Avg Spend", "متوسط الإنفاق"),
    "avg_visits": ("Avg Visits", "متوسط الزيارات"),
    "avg_days_since": ("Avg Days Since Visit", "متوسط الأيام منذ الزيارة"),
    "prev_sales": ("Previous Sales", "مبيعات الفترة السابقة"),
    "sales_change": ("Sales Change %", "تغير المبيعات %"),
    "prev_customers": ("Previous Customers", "عملاء الفترة السابقة"),
    "customers_change": ("Customers Change %", "تغير العملاء %"),
    "new": ("New", "جدد"),
    "returning": ("Returning", "عائدون"),
    "top_branch": ("Top Branch", "الفرع الأعلى مبيعاً"),
    "top_district": ("Top District", "المنطقة الأعلى مبيعاً"),
    "top_item": ("Top Item", "الصنف الأعلى مبيعاً"),
    "date": ("Date", "التاريخ"),
    "lines": ("Lines", "عدد الأصناف"),
    "total": ("Total", "الإجمالي"),
    "items": ("Items", "الأصناف"),
    "times": ("Times Bought", "مرات الشراء"),
    "value": ("Value", "القيمة"),
}

VALUES = {
    "active": ("Active", "نشط"),
    "attention": ("Needs Attention", "يحتاج متابعة"),
    "inactive": ("Inactive", "غير نشط"),
    "unknown": ("Unknown", "غير معروف"),
    "keep_engaged": ("Keep engaged", "حافظ على التواصل"),
    "send_offer": ("Send an offer", "أرسل عرض"),
    "call_customer": ("Call the customer", "اتصل بالعميل"),
    "champions": ("Champions", "الأبطال"),
    "loyal": ("Loyal", "أوفياء"),
    "potential": ("Potential Loyalists", "أوفياء محتملون"),
    "new": ("New", "جدد"),
    "promising": ("Promising", "واعدون"),
    "cant_lose": ("Can't Lose", "لا يمكن خسارتهم"),
    "at_risk": ("At Risk", "معرضون للفقد"),
    "hibernating": ("Hibernating", "خاملون"),
    "lost": ("Lost", "مفقودون"),
    "growing": ("Growing", "متزايد"),
    "stable": ("Stable", "ثابت"),
    "declining": ("Declining", "متراجع"),
    "stopped": ("Stopped", "توقف"),
    "back": ("Came back", "عاد"),
    "none": ("No recent spend", "لا إنفاق حديث"),
    "due_soon": ("Due this week", "مستحق هذا الأسبوع"),
    "overdue": ("Overdue", "متأخر"),
    "lapsed": ("Lapsed", "انقطع"),
    "ok": ("Not due yet", "لم يحن موعده"),
    "high": ("High", "مرتفع"),
    "medium": ("Medium", "متوسط"),
    "low": ("Low", "منخفض"),
    True: ("Yes", "نعم"),
    False: ("No", "لا"),
    "Winter": ("Winter", "الشتاء"),
    "Spring": ("Spring", "الربيع"),
    "Summer": ("Summer", "الصيف"),
    "Autumn": ("Autumn", "الخريف"),
}

ACTIONS = {"active": "keep_engaged", "attention": "send_offer", "inactive": "call_customer",
           "unknown": "call_customer"}

TRANSLATED_COLS = {"status", "action", "high_value", "loyal", "phone_valid", "top_season", "season", "bought",
                   "segment", "churn_risk", "trend", "refill_status"}


def label(key: str, lang: str) -> str:
    pair = LABELS.get(key)
    if not pair:
        return key
    return pair[1] if lang == "ar" else pair[0]


def frame(rows: list[dict], columns: list[str], lang: str) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=columns)
    idx = 1 if lang == "ar" else 0
    for c in columns:
        if c in TRANSLATED_COLS:
            df[c] = df[c].map(lambda v: VALUES[v][idx] if v in VALUES else v)
    return df.rename(columns={c: label(c, lang) for c in columns})


def workbook(sheets: list[tuple[str, pd.DataFrame]], lang: str, title: str | None = None,
             meta: list[tuple[str, str]] | None = None) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter",
                        datetime_format="yyyy-mm-dd hh:mm", date_format="yyyy-mm-dd") as xw:
        book = xw.book
        head = book.add_format({"bold": True, "bg_color": "#1b5e20", "font_color": "#ffffff",
                                "border": 1, "text_wrap": True, "valign": "vcenter"})
        money = book.add_format({"num_format": "#,##0.00"})
        bold = book.add_format({"bold": True, "font_size": 14})

        for name, df in sheets:
            start = 0
            safe = name[:31]
            if meta and name == sheets[0][0]:
                start = len(meta) + 2
            df.to_excel(xw, sheet_name=safe, index=False, startrow=start)
            ws = xw.sheets[safe]
            if lang == "ar":
                ws.right_to_left()
            if meta and name == sheets[0][0]:
                ws.write(0, 0, title or "", bold)
                for i, (k, v) in enumerate(meta, start=1):
                    ws.write(i, 0, k)
                    ws.write(i, 1, v)
            for ci, col in enumerate(df.columns):
                ws.write(start, ci, col, head)
                sample = df[col].head(200).astype(str).str.len()
                width = min(max([len(str(col))] + sample.tolist()) + 2, 50)
                is_money = pd.api.types.is_float_dtype(df[col])
                ws.set_column(ci, ci, width, money if is_money else None)
            ws.freeze_panes(start + 1, 0)
            if len(df):
                ws.autofilter(start, 0, start + len(df), len(df.columns) - 1)
    return buf.getvalue()


def fmt_value(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, (date, datetime)):
        return v.isoformat()[:10]
    return str(v)
