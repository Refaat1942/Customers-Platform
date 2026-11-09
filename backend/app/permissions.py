"""Authorization matrix: permissions x roles. Roles are editable in the UI (except admin)."""

PERMISSIONS = [
    # key, English, Arabic
    ("dashboard", "Dashboard & summary", "لوحة التحكم والملخص"),
    ("insights", "Smart insights (RFM, cohorts, basket)", "التحليلات الذكية"),
    ("customers", "Customers & profiles", "العملاء وملفاتهم"),
    ("phones", "See full phone numbers", "رؤية أرقام الموبايل كاملة"),
    ("business", "Business analysis", "تحليل الأعمال"),
    ("recommendations", "Recommendations / call lists", "التوصيات وقوائم الاتصال"),
    ("area", "Area analytics", "تحليل المناطق"),
    ("transactions", "Transactions", "المعاملات"),
    ("ai", "AI analyst", "المحلل الذكي"),
    ("export", "Download Excel reports", "تحميل تقارير Excel"),
    ("import", "Upload / delete data", "رفع وحذف البيانات"),
    ("users", "Users & roles", "المستخدمون والصلاحيات"),
    ("settings", "Settings, branding & AI key", "الإعدادات والهوية ومفتاح AI"),
    ("audit", "Audit log", "سجل التدقيق"),
]

ALL = [p[0] for p in PERMISSIONS]

VIEW = ["dashboard", "insights", "customers", "phones", "business", "recommendations", "area",
        "transactions"]

DEFAULT_ROLES = {
    "admin": ("Full access", ALL),
    "manager": ("Managers: all reports, exports and AI", VIEW + ["ai", "export"]),
    "branch_staff": ("Branch staff: call lists only", ["dashboard", "customers", "phones",
                                                       "recommendations"]),
    "viewer": ("Read-only, phone numbers hidden", ["dashboard", "insights", "customers",
                                                    "business", "area"]),
}
