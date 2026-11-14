import i18n from "./i18n";

/** Texts for products (code + name, product page), shifts, and the merged customers page. */
const en = {
  nav: { shifts: "Shifts" },
  navHint: { shifts: "Night, morning and evening: sales, branches, live POS vs files", customers: "Everyone who bought + your customer lists" },
  col: { code: "Product code", item: "Product name", units: "Units", branches: "Branches", avg_days_between: "Re-buys every", shift: "Shift", purchases: "Purchases", last_bought: "Last bought", units_per_day: "Units / day", pct: "% of its invoices", hour: "Hour" },
  cust: { tabBought: "Customers who bought", tabBase: "Everyone in customer lists", tabsHelp: "The first tab is built from sales (invoices). The second shows every phone in the customer lists you uploaded, including people who never bought." },
  prod: {
    noName: "(no name in file)",
    namesMissing: "{{n}} product codes have no name in any uploaded file, so they show only their code.",
    namesFix: "Upload a product list (an Excel with item code + item name) from Data upload - every sale with that code gets the name automatically.",
    open: "Click a product to see its branches, months, hours, shifts and buyers.",
    days: "{{n}} days",
  },
  pd: {
    back: "All products", units: "Units sold", sales: "Sales", invoices: "Invoices", customers: "Buyers", avgPrice: "Average price", perInvoice: "Units per invoice",
    interval: "Customers re-buy every", intervalSub: "median days between two purchases of the same customer", repeat: "Repeat buyers",
    firstLast: "Sold between", byBranch: "Where it sells - branches", topBranch: "Best branch", byMonth: "Units by month", byWeekday: "Units by weekday",
    byHour: "Units by hour of day", byShift: "Units by shift", branchShift: "Branch × shift (units)", intervals: "How long until customers buy it again",
    topCustomers: "Top buyers", together: "Often bought together with it", otherNames: "Names used for this code in your files", noTime: "Your files have no time for these sales, so hours and shifts can't be shown.",
    buckets: ["≤ 7 days", "8–14 days", "15–30 days", "31–60 days", "61–90 days", "> 90 days"], catalogue: { file: "Name from product list", sales: "Name learnt from sales files" },
  },
  shift: {
    title: "Shifts", subtitle: "When do customers buy? Night, morning and evening shifts - per branch, per hour, live POS vs uploaded files",
    night: "Night", morning: "Morning", evening: "Evening", unknown: "No time recorded",
    range: { night: "{{a}} – {{b}}", morning: "{{a}} – {{b}}", evening: "{{a}} – 24:00" },
    share: "of sales", invoices: "invoices", customers: "customers", avgInvoice: "avg invoice", units: "units",
    byBranch: "Branches by shift", busiest: "Busiest shift", source: "Live POS vs uploaded files", live: "Live POS", file: "Uploaded files",
    hourly: "Invoices by hour", weekday: "Invoices by weekday and shift", prefer: "Customers who usually buy in this shift", topItems: "Top products per shift",
    unknownNote: "{{n}} invoices have no time in the file (only a date), so they can't be placed in a shift. Map the time column when uploading to fix this.",
    settings: "Shift times", settingsHelp: "Night starts at midnight. Choose when the morning and evening shifts start.", morningStart: "Morning shift starts", eveningStart: "Evening shift starts",
    fav: "Usual shift",
  },
  imp: {
    kinds: { products: "Product list (codes + names)" },
    kindReason: { codes_names: "Detected: product codes + names, no phones or dates → product list (fills product names in all sales)" },
    modes: { upsert_products: "Add / update products", replace_all_products: "Replace the whole product list" },
  },
};

const ar = {
  nav: { shifts: "الورديات" },
  navHint: { shifts: "الليل والصباح والمساء: المبيعات والفروع والكاشير المباشر مقابل الملفات", customers: "كل من اشترى + قوائم العملاء المرفوعة" },
  col: { code: "كود الصنف", item: "اسم الصنف", units: "الوحدات", branches: "الفروع", avg_days_between: "يعيد الشراء كل", shift: "الوردية", purchases: "مرات الشراء", last_bought: "آخر شراء", units_per_day: "وحدات / يوم", pct: "% من فواتيره", hour: "الساعة" },
  cust: { tabBought: "العملاء اللي اشتروا", tabBase: "كل العملاء في القوائم", tabsHelp: "التبويب الأول مبني من المبيعات (الفواتير). التاني فيه كل رقم في قوائم العملاء اللي رفعتها، حتى اللي لسه ما اشتروش." },
  prod: {
    noName: "(بدون اسم في الملف)",
    namesMissing: "{{n}} كود صنف ملهمش اسم في أي ملف مرفوع، فبيظهر الكود بس.",
    namesFix: "ارفع قائمة أصناف (إكسيل فيه كود الصنف + اسم الصنف) من رفع البيانات - كل مبيعات الكود ده هتاخد الاسم تلقائياً.",
    open: "اضغط على أي صنف لتشوف فروعه وشهوره وساعاته وورديات بيعه والمشترين.",
    days: "{{n}} يوم",
  },
  pd: {
    back: "كل الأصناف", units: "الوحدات المباعة", sales: "المبيعات", invoices: "الفواتير", customers: "المشترين", avgPrice: "متوسط السعر", perInvoice: "وحدات لكل فاتورة",
    interval: "العملاء بيعيدوا شراءه كل", intervalSub: "الوسيط بالأيام بين مرتين شراء لنفس العميل", repeat: "عملاء كرروا الشراء",
    firstLast: "اتباع في الفترة", byBranch: "بيتباع فين - الفروع", topBranch: "أعلى فرع", byMonth: "الوحدات بالشهر", byWeekday: "الوحدات بأيام الأسبوع",
    byHour: "الوحدات بساعات اليوم", byShift: "الوحدات بالوردية", branchShift: "الفرع × الوردية (وحدات)", intervals: "العميل بيرجع يشتريه بعد قد إيه",
    topCustomers: "أكثر المشترين", together: "بيتشترى معاه غالباً", otherNames: "الأسماء المستخدمة للكود ده في ملفاتك", noTime: "ملفاتك مفيهاش وقت للمبيعات دي، فمش هينفع نعرض الساعات والورديات.",
    buckets: ["≤ 7 أيام", "8–14 يوم", "15–30 يوم", "31–60 يوم", "61–90 يوم", "> 90 يوم"], catalogue: { file: "الاسم من قائمة الأصناف", sales: "الاسم من ملفات المبيعات" },
  },
  shift: {
    title: "الورديات", subtitle: "العملاء بيشتروا إمتى؟ وردية الليل والصباح والمساء - لكل فرع ولكل ساعة، والكاشير المباشر مقابل الملفات المرفوعة",
    night: "الليل", morning: "الصباح", evening: "المساء", unknown: "بدون وقت مسجل",
    range: { night: "{{a}} – {{b}}", morning: "{{a}} – {{b}}", evening: "{{a}} – 24:00" },
    share: "من المبيعات", invoices: "فاتورة", customers: "عميل", avgInvoice: "متوسط الفاتورة", units: "وحدة",
    byBranch: "الفروع حسب الوردية", busiest: "الوردية الأعلى", source: "الكاشير المباشر مقابل الملفات المرفوعة", live: "الكاشير المباشر", file: "الملفات المرفوعة",
    hourly: "الفواتير بالساعة", weekday: "الفواتير بأيام الأسبوع والوردية", prefer: "عملاء بيشتروا غالباً في الوردية دي", topItems: "أعلى الأصناف في كل وردية",
    unknownNote: "{{n}} فاتورة ملهاش وقت في الملف (تاريخ بس)، فمش هينفع نحطها في وردية. اختار عمود الوقت وانت بترفع الملف عشان تتحل.",
    settings: "مواعيد الورديات", settingsHelp: "وردية الليل بتبدأ من 12 بالليل. اختار إمتى تبدأ وردية الصباح ووردية المساء.", morningStart: "بداية وردية الصباح", eveningStart: "بداية وردية المساء",
    fav: "الوردية المعتادة",
  },
  imp: {
    kinds: { products: "قائمة أصناف (أكواد + أسماء)" },
    kindReason: { codes_names: "تم التعرف: أكواد وأسماء أصناف من غير موبايلات أو تواريخ ← قائمة أصناف (بتكمل أسماء الأصناف في كل المبيعات)" },
    modes: { upsert_products: "إضافة / تحديث الأصناف", replace_all_products: "استبدال قائمة الأصناف بالكامل" },
  },
};

i18n.addResourceBundle("en", "translation", en, true, false);
i18n.addResourceBundle("ar", "translation", ar, true, false);
