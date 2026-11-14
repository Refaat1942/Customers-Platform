"""Authorization matrix: permissions x roles. Roles are editable in the UI (except admin).
Each permission shows or hides a page (or a sensitive ability) for everyone with that role."""

PERMISSIONS = [
    # key, English, Arabic, group
    ("dashboard", "Dashboard", "لوحة التحكم", "today"),
    ("live", "Live POS", "الكاشير المباشر", "today"),
    ("customers", "Customers & profiles", "العملاء وملفاتهم", "customers"),
    ("customer_base", "Customer base (uploaded lists)", "قاعدة العملاء", "customers"),
    ("phones", "See full phone numbers", "رؤية أرقام الموبايل كاملة", "customers"),
    ("recommendations", "Call lists", "قوائم الاتصال", "act"),
    ("refills", "Refill reminders", "تذكير إعادة الشراء", "act"),
    ("insights", "Smart insights", "التحليلات الذكية", "analysis"),
    ("business", "Business analysis", "تحليل الأعمال", "analysis"),
    ("products", "Products", "الأصناف", "analysis"),
    ("area", "Areas", "المناطق", "analysis"),
    ("transactions", "Transactions", "المعاملات", "analysis"),
    ("ai", "AI analyst", "المحلل الذكي", "analysis"),
    ("export", "Download Excel reports", "تحميل تقارير Excel", "data"),
    ("import", "Upload / delete data", "رفع وحذف البيانات", "data"),
    ("data_check", "Data check", "فحص البيانات", "data"),
    ("users", "Users & roles", "المستخدمون والصلاحيات", "admin"),
    ("settings", "Settings, branding, POS keys & AI key", "الإعدادات والهوية ومفاتيح الربط", "admin"),
    ("audit", "Audit log", "سجل التدقيق", "admin"),
]

ALL = [p[0] for p in PERMISSIONS]

# permissions added later inherit from the one that used to cover that page,
# so existing roles keep seeing exactly what they saw before
DERIVED = {"live": "dashboard", "customer_base": "customers", "refills": "recommendations",
           "products": "business", "data_check": "import"}

VIEW = ["dashboard", "live", "insights", "customers", "customer_base", "phones", "business",
        "products", "recommendations", "refills", "area", "transactions"]

DEFAULT_ROLES = {
    "admin": ("Full access", ALL),
    "manager": ("Managers: all reports, exports and AI", VIEW + ["ai", "export"]),
    "branch_staff": ("Branch staff: call lists only", ["dashboard", "live", "customers", "phones",
                                                       "recommendations", "refills"]),
    "viewer": ("Read-only, phone numbers hidden", ["dashboard", "insights", "customers",
                                                    "business", "products", "area"]),
}
