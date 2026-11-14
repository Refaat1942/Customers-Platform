import i18n from "./i18n";

/** Every term used in the program, in plain words. [key, group, English, Arabic]
 *  Each language: name | one-line meaning | longer explanation with an example. */
type Entry = [string, string, [string, string, string], [string, string, string]];

export const GROUPS = ["basics", "growth", "customers", "segments", "act", "products", "data", "security"] as const;

export const TERMS: Entry[] = [
  // ------------------------------------------------------------ basics
  ["sales", "basics", ["Sales", "Total money of all sold lines.", "The sum of the amount column of every line in the selected period, after discounts. Returns are negative, so they reduce sales."],
    ["المبيعات", "إجمالي قيمة كل السطور المباعة.", "مجموع عمود القيمة لكل سطر في الفترة المختارة بعد الخصم. المرتجعات قيمتها بالسالب فبتقلل المبيعات."]],
  ["invoice", "basics", ["Invoice / visit", "One purchase at the cashier = one invoice = one visit.", "Lines with the same invoice number in the same branch form one invoice. If the file has no invoice number, all lines of the same customer, day and branch count as one visit."],
    ["الفاتورة / الزيارة", "عملية شراء واحدة عند الكاشير = فاتورة واحدة = زيارة واحدة.", "السطور اللي ليها نفس رقم الفاتورة في نفس الفرع = فاتورة واحدة. لو الملف مفيهوش رقم فاتورة، كل سطور نفس العميل في نفس اليوم ونفس الفرع = زيارة واحدة."]],
  ["line", "basics", ["Sales line", "One product inside an invoice.", "An invoice with 3 products has 3 lines. Data check counts lines; most reports count invoices."],
    ["سطر المبيعات", "صنف واحد داخل الفاتورة.", "فاتورة فيها 3 أصناف = 3 سطور. فحص البيانات بيعد السطور، ومعظم التقارير بتعد الفواتير."]],
  ["customer", "basics", ["Customer", "One mobile number = one customer.", "Customers are identified by their mobile number (normalised to 01xxxxxxxxx). Sales without a phone count in totals but not per customer."],
    ["العميل", "رقم موبايل واحد = عميل واحد.", "العميل بيتعرف برقم الموبايل (بيتظبط لشكل 01xxxxxxxxx). المبيعات اللي من غير موبايل بتتحسب في الإجمالي بس مش على عميل."]],
  ["avg_invoice", "basics", ["Average invoice", "Sales ÷ number of invoices.", "How much a customer spends in one visit on average. Example: 100,000 EGP from 400 invoices = 250 EGP."],
    ["متوسط الفاتورة", "المبيعات ÷ عدد الفواتير.", "العميل بيصرف كام في الزيارة الواحدة في المتوسط. مثال: 100,000 جنيه من 400 فاتورة = 250 جنيه."]],
  ["avg_per_customer", "basics", ["Average spend per customer", "Sales ÷ number of customers.", "How much one customer brought in the selected period on average."],
    ["متوسط الإنفاق لكل عميل", "المبيعات ÷ عدد العملاء.", "العميل الواحد جاب كام في الفترة المختارة في المتوسط."]],
  ["max_min_invoice", "basics", ["Highest / lowest invoice", "The biggest and smallest single purchase of a customer.", "Shown in each customer's profile and list to see how much they can spend in one visit."],
    ["أعلى / أقل فاتورة", "أكبر وأصغر عملية شراء للعميل.", "بتظهر في ملف كل عميل وفي القائمة عشان تعرف العميل ممكن يصرف قد إيه في الزيارة."]],
  ["reference_date", "basics", ["Status calculated on", "The day used to count 'days since last visit'.", "It is the end of the selected period, or the latest date in your data - not today. So an old upload doesn't make everyone look inactive."],
    ["الحالة محسوبة بتاريخ", "اليوم اللي بنحسب منه 'أيام منذ آخر زيارة'.", "هو آخر يوم في الفترة المختارة أو آخر تاريخ في بياناتك - مش النهارده. عشان لو البيانات قديمة ميبانش كل العملاء غير نشطين."]],
  ["sales_type", "basics", ["Sales type", "How the sale was made: Cash, Delivery, Insurance…", "Taken from the sales type column of your file or POS."],
    ["نوع البيع", "طريقة البيع: نقدي، توصيل، تأمين…", "بيتاخد من عمود نوع البيع في الملف أو الكاشير."]],
  ["district", "basics", ["District", "The customer's area (from the address or customer list).", "Used in Areas. Customer lists (with a district column) correct the district of every sale of that customer."],
    ["المنطقة", "منطقة العميل (من العنوان أو قائمة العملاء).", "بتستخدم في صفحة المناطق. قوائم العملاء (اللي فيها عمود منطقة) بتصحح منطقة كل مبيعات العميل."]],
  ["season", "basics", ["Season", "Winter (Dec-Feb), Spring (Mar-May), Summer (Jun-Aug), Autumn (Sep-Nov).", "Calculated from the invoice date."],
    ["الموسم", "الشتاء (ديسمبر-فبراير)، الربيع (مارس-مايو)، الصيف (يونيو-أغسطس)، الخريف (سبتمبر-نوفمبر).", "بيتحسب من تاريخ الفاتورة."]],

  // ------------------------------------------------------------ growth
  ["growth", "growth", ["Growth / comparison", "This period compared with another period.", "By default the selected dates are compared with the SAME dates last year (1 Jan-31 Oct 2026 vs 1 Jan-31 Oct 2025). You can choose 'Period just before' in the filters: same number of days right before the selected dates. Without a date range, the last 30 days are compared. The column headers show the exact dates."],
    ["النمو / المقارنة", "الفترة دي مقارنة بفترة تانية.", "افتراضياً التواريخ المختارة بتتقارن بنفس التواريخ من السنة اللي فاتت (1 يناير-31 أكتوبر 2026 مقابل 1 يناير-31 أكتوبر 2025). وتقدر تختار 'الفترة اللي قبلها مباشرة' من الفلاتر: نفس عدد الأيام قبل الفترة المختارة. لو مفيش فترة مختارة بنقارن آخر 30 يوم. عناوين الأعمدة بتوضح التواريخ بالظبط."]],
  ["new_branch", "growth", ["New branch", "The branch had no sales in the comparison period.", "So a percentage change can't be calculated."],
    ["فرع جديد", "الفرع ملوش مبيعات في فترة المقارنة.", "عشان كده مينفعش نحسب نسبة تغير."]],
  ["new_customers", "growth", ["New customers", "Customers whose first purchase ever is inside the selected period.", "Only shown when a start date is selected."],
    ["عملاء جدد", "عملاء أول شراء ليهم على الإطلاق جوه الفترة المختارة.", "بيظهر بس لما تختار تاريخ بداية."]],
  ["new_vs_returning", "growth", ["New vs returning", "Each month: first-time buyers vs customers who bought before.", "A healthy branch keeps many returning customers every month."],
    ["جدد مقابل عائدين", "كل شهر: اللي بيشتروا لأول مرة مقابل اللي اشتروا قبل كده.", "الفرع الكويس بيحافظ على عدد كبير من العملاء العائدين كل شهر."]],
  ["cohort", "growth", ["Retention by first-purchase month", "Of the customers who first bought in a month, how many came back later.", "Row 2026-01, column M2 = 30% means 30% of January's new customers bought again 2 months later."],
    ["الاحتفاظ حسب شهر أول شراء", "من العملاء اللي اشتروا لأول مرة في شهر، كام واحد رجع بعد كده.", "صف 2026-01 وعمود M2 = 30% يعني 30% من عملاء يناير الجدد اشتروا تاني بعد شهرين."]],
  ["pareto", "growth", ["Top 20% share", "How much of sales comes from your best 20% of customers.", "If it is 60%, a small group of customers is very important - protect them."],
    ["نصيب أفضل 20%", "قد إيه من المبيعات جاي من أفضل 20% من عملائك.", "لو 60% يبقى مجموعة صغيرة من العملاء مهمة جداً - حافظ عليهم."]],
  ["trend", "growth", ["Spend trend", "Is a customer spending more or less lately?", "Spend in the last 90 days vs the 90 days before. Growing = +25% or more · Declining = -25% or more · Stopped = nothing in the last 90 days · New = first purchase in the last 90 days · Came back = nothing in the previous 90 days but bought recently."],
    ["اتجاه الإنفاق", "العميل بيصرف أكتر ولا أقل مؤخراً؟", "إنفاق آخر 90 يوم مقابل الـ 90 يوم اللي قبلهم. متزايد = +25% أو أكتر · متراجع = -25% أو أكتر · توقف = مفيش شراء آخر 90 يوم · جديد = أول شراء في آخر 90 يوم · رجع = مكنش بيشتري في الـ 90 اللي قبل وبعدين اشترى."]],

  // ------------------------------------------------------------ customers
  ["status", "customers", ["Customer status", "Active / Needs attention / Inactive - by days since last visit.", "Active: visited within 30 days. Needs attention: 31-60 days. Inactive: more than 60 days. The numbers can be changed in Settings."],
    ["حالة العميل", "نشط / يحتاج متابعة / غير نشط - حسب الأيام من آخر زيارة.", "نشط: زار خلال 30 يوم. يحتاج متابعة: من 31 لـ 60 يوم. غير نشط: أكتر من 60 يوم. الأرقام دي تتغير من الإعدادات."]],
  ["high_value", "customers", ["High value", "Total spend at or above the limit in Settings (default 10,000 EGP).", ""],
    ["قيمة عالية", "إجمالي مشترياته أكبر من أو يساوي الحد في الإعدادات (افتراضي 10,000 جنيه).", ""]],
  ["loyal", "customers", ["Loyal", "Spend ≥ 10,000 EGP or 5+ visits (changeable in Settings).", ""],
    ["وفي", "مشتريات ≥ 10,000 جنيه أو 5 زيارات أو أكتر (تتغير من الإعدادات).", ""]],
  ["churn_risk", "customers", ["Churn risk", "How likely the customer is to stop coming.", "Compares days since the last visit with the customer's OWN usual gap. High = more than twice their usual gap. A customer who comes every week and hasn't come for 3 weeks is high risk; one who comes every 2 months isn't."],
    ["خطر الفقد", "احتمال إن العميل يبطل ييجي.", "بنقارن الأيام من آخر زيارة بالفاصل المعتاد للعميل نفسه. مرتفع = أكتر من ضعف فاصله المعتاد. عميل بييجي كل أسبوع وغاب 3 أسابيع = خطر مرتفع، لكن اللي بييجي كل شهرين لأ."]],
  ["expected_next", "customers", ["Expected next visit", "Last visit + the customer's usual days between visits.", "Overdue days = how many days after that date they still haven't come."],
    ["الزيارة المتوقعة", "آخر زيارة + متوسط الأيام بين زيارات العميل.", "أيام التأخير = عدد الأيام اللي عدت بعد التاريخ ده ولسه مجاش."]],
  ["avg_days_between", "customers", ["Average days between visits", "How often the customer usually comes.", "First and last visit day divided by the number of visit days."],
    ["متوسط الأيام بين الزيارات", "العميل بييجي كل قد إيه عادة.", "الفرق بين أول وآخر زيارة مقسوم على عدد أيام الزيارة."]],
  ["customer_base", "customers", ["Customer base", "Everyone in your uploaded customer lists - even those who never bought.", "Customer lists (phone, name, address) are linked to sales by phone and fill names and districts."],
    ["قاعدة العملاء", "كل الموجودين في قوائم العملاء المرفوعة - حتى اللي عمرهم ما اشتروا.", "قوائم العملاء (موبايل، اسم، عنوان) بتتربط بالمبيعات برقم الموبايل وبتكمّل الأسماء والمناطق."]],
  ["habits", "customers", ["Shopping habits", "Favourite day and time, items per visit, delivery share, returns, favourite branch.", "In each customer's profile (Purchases tab)."],
    ["عادات الشراء", "اليوم والوقت المفضل، الأصناف في الزيارة، نسبة التوصيل، المرتجعات، الفرع المفضل.", "في ملف كل عميل (تبويب المشتريات)."]],

  // ------------------------------------------------------------ segments
  ["rfm", "segments", ["Segments (RFM)", "Customers grouped by Recency, Frequency and Money.", "Each customer gets 1-5 for how recently they bought (R), how often (F) and how much (M), compared with all other customers. The scores give the segment below."],
    ["الشرائح (RFM)", "تقسيم العملاء حسب الحداثة والتكرار والقيمة.", "كل عميل بياخد من 1 لـ 5 في: آخر شراء قريب قد إيه (R)، بيشتري كام مرة (F)، بيصرف قد إيه (M) مقارنة بباقي العملاء. الدرجات دي بتحدد الشريحة."]],
  ["champions", "segments", ["Champions", "Bought recently, often, and spend the most.", "Reward them; ask for reviews."], ["الأبطال", "اشتروا مؤخراً وكتير وبيصرفوا الأعلى.", "كافئهم واطلب رأيهم."]],
  ["loyal_seg", "segments", ["Loyal", "Buy regularly.", "Offer loyalty benefits."], ["أوفياء", "بيشتروا بانتظام.", "قدم لهم مزايا الولاء."]],
  ["potential", "segments", ["Potential loyalists", "Recent customers with average frequency.", "Encourage a second and third purchase."], ["أوفياء محتملون", "عملاء حديثين بتكرار متوسط.", "شجعهم على الشراء التاني والتالت."]],
  ["new_seg", "segments", ["New", "First purchase recently.", "Welcome message, first-visit follow-up."], ["جدد", "أول شراء مؤخراً.", "رسالة ترحيب ومتابعة بعد أول زيارة."]],
  ["promising", "segments", ["Promising", "Recent but not frequent.", "Small offers to bring them back."], ["واعدون", "حديثين لكن مش متكررين.", "عروض صغيرة تخليهم يرجعوا."]],
  ["cant_lose", "segments", ["Can't lose them", "Used to buy often and spend a lot, now gone.", "Call them first."], ["لا يمكن خسارتهم", "كانوا بيشتروا كتير وبمبالغ كبيرة وبعدين اختفوا.", "اتصل بيهم الأول."]],
  ["at_risk", "segments", ["At risk", "Used to buy often, haven't come back.", "Send a personal offer."], ["معرضون للفقد", "كانوا متكررين ومرجعوش.", "ابعت لهم عرض خاص."]],
  ["hibernating", "segments", ["Hibernating", "Low and infrequent, long ago.", "Seasonal reminders only."], ["خاملون", "قليلين ومن زمان.", "تذكير موسمي بس."]],
  ["lost", "segments", ["Lost", "Lowest recency and frequency.", "Low priority."], ["مفقودون", "الأقل حداثة وتكراراً.", "أولوية منخفضة."]],

  // ------------------------------------------------------------ act
  ["call_list", "act", ["Call lists", "Who to contact first: inactive and high-spend customers on top.", "Action column: Keep engaged (active) · Send an offer (needs attention) · Call the customer (inactive)."],
    ["قوائم الاتصال", "مين تتواصل معاه الأول: غير النشطين وكبار العملاء فوق.", "عمود الإجراء: حافظ على التواصل (نشط) · أرسل عرض (يحتاج متابعة) · اتصل بالعميل (غير نشط)."]],
  ["refill", "act", ["Refill reminder", "A product the customer buys again on a regular cycle.", "Counted when bought 3+ times at regular intervals (every 5-120 days). Cycle = usual days between purchases. Due date = last purchase + cycle. Delivery fees and services are ignored."],
    ["تذكير إعادة الشراء", "صنف العميل بيرجع يشتريه بانتظام.", "بيتحسب لو اتشرى 3 مرات أو أكتر على فترات منتظمة (كل 5 لـ 120 يوم). الدورة = الأيام المعتادة بين كل شراء. الموعد = آخر شراء + الدورة. رسوم التوصيل والخدمات مش بتتحسب."]],
  ["refill_status", "act", ["Refill status", "Due this week · Overdue · Lapsed · Not due yet.", "Due this week: due in the next 7 days. Overdue: due date passed (less than one cycle late). Lapsed: more than one cycle late - may have switched pharmacy or product."],
    ["حالة إعادة الشراء", "مستحق هذا الأسبوع · متأخر · انقطع · لم يحن موعده.", "مستحق هذا الأسبوع: موعده خلال 7 أيام. متأخر: الموعد عدّى (أقل من دورة). انقطع: متأخر أكتر من دورة كاملة - ممكن غيّر الصيدلية أو الصنف."]],

  // ------------------------------------------------------------ products
  ["repeat_rate", "products", ["Repeat rate", "% of a product's buyers who bought it in 2 or more visits.", "High repeat rate = customers come back for it (chronic or favourite products)."],
    ["نسبة التكرار", "نسبة مشتري الصنف اللي اشتروه في زيارتين أو أكتر.", "نسبة تكرار عالية = العملاء بيرجعوا عشانه (أصناف مزمنة أو مفضلة)."]],
  ["product_code", "products", ["Product code vs name", "The code identifies a product; the name is how it is called.", "Products are grouped by code, because different reports write the same product's name differently. If a file has only codes, the name is taken from any other file or product list that has it. Codes with no name anywhere show '(no name in file)' - upload a product list to fix them."],
    ["كود الصنف واسمه", "الكود بيحدد الصنف، والاسم هو اللي بيتسمى بيه.", "الأصناف بتتجمع بالكود، لأن التقارير المختلفة بتكتب اسم نفس الصنف بأشكال مختلفة. لو الملف فيه أكواد بس، الاسم بيتاخد من أي ملف تاني أو قائمة أصناف فيها الاسم. الأكواد اللي ملهاش اسم في أي مكان بتظهر '(بدون اسم في الملف)' - ارفع قائمة أصناف عشان تتحل."]],
  ["rebuy_interval", "products", ["Re-buys every", "Typical days between two purchases of the same product by the same customer.", "The median gap: half of the repeat purchases happen sooner, half later. Example: 30 days for a monthly medicine. Good for stock planning and reminders."],
    ["يعيد الشراء كل", "عدد الأيام المعتاد بين مرتين شراء لنفس الصنف من نفس العميل.", "الوسيط: نص مرات إعادة الشراء بتحصل قبله والنص بعده. مثال: 30 يوم لدوا شهري. مفيد لتخطيط المخزون والتذكير."]],
  ["shift", "products", ["Shift", "Night 00:00–08:30, Morning 08:30–16:30, Evening 16:30–24:00.", "Each invoice is placed in a shift by its time. The start times can be changed in Settings. Invoices from files that have only a date (no time) are shown as 'No time recorded'. Live POS invoices always have a time."],
    ["الوردية", "ليل 12 ص – 8:30 ص، صباح 8:30 ص – 4:30 م، مساء 4:30 م – 12 ص.", "كل فاتورة بتتحط في وردية حسب وقتها. مواعيد البداية ممكن تتغير من الإعدادات. فواتير الملفات اللي فيها تاريخ بس (من غير وقت) بتظهر 'بدون وقت مسجل'. فواتير الكاشير المباشر دايماً فيها وقت."]],
  ["product_list", "data", ["Product list", "An Excel with product codes and names (and category, unit).", "Upload it like any other file - it is recognised automatically. It fills the product name of every sale with that code, in old and new data."],
    ["قائمة الأصناف", "إكسيل فيه أكواد وأسماء الأصناف (والفئة والوحدة).", "ارفعه زي أي ملف - بيتعرف تلقائياً. بيكمل اسم الصنف في كل مبيعات الكود ده، في البيانات القديمة والجديدة."]],
  ["basket", "products", ["Bought together / lift", "Products often bought in the same invoice.", "Lift above 1 means the pair appears together more often than by chance (2 = twice as often). Use it for bundles and shelf placement."],
    ["يشترى معاً / معامل الارتباط", "أصناف بتتشرى كتير في نفس الفاتورة.", "المعامل أكبر من 1 يعني الاتنين بيتشروا مع بعض أكتر من الصدفة (2 = الضعف). استخدمه في العروض المجمعة وترتيب الأرفف."]],

  // ------------------------------------------------------------ data
  ["merge", "data", ["Add new, skip existing (upload mode)", "The safe mode: nothing is ever deleted.", "Lines already in the system are skipped - even from a differently shaped report. Use it for every normal upload."],
    ["إضافة الجديد وتجاهل الموجود (طريقة الرفع)", "الطريقة الآمنة: مفيش أي حذف.", "السطور الموجودة بالفعل بتتجاهل - حتى لو من تقرير بشكل مختلف. استخدمها في كل رفع عادي."]],
  ["replace_period", "data", ["Replace same dates & branches", "Deletes the existing sales of those dates and branches, then adds the file.", "Only for a complete, corrected file of that period."],
    ["استبدال نفس التواريخ والفروع", "بيحذف مبيعات نفس التواريخ والفروع وبعدين يضيف الملف.", "استخدمه بس لملف كامل ومصحح لنفس الفترة."]],
  ["skipped", "data", ["Skipped (upload)", "Lines not added: already in the system, or with an invalid date.", "For customer lists: the same phone appearing more than once in the file."],
    ["المتجاهل (الرفع)", "سطور مضافتش: موجودة بالفعل أو تاريخها غلط.", "في قوائم العملاء: نفس الموبايل متكرر أكتر من مرة في الملف."]],
  ["data_check", "data", ["Data check", "Live numbers straight from the database.", "Use it to confirm an upload reached every report: rows added vs rows stored now, totals by month, branch and sales type."],
    ["فحص البيانات", "أرقام مباشرة من قاعدة البيانات.", "استخدمه للتأكد إن الرفع وصل لكل التقارير: الصفوف المضافة مقابل الموجودة الآن، والإجماليات حسب الشهر والفرع ونوع البيع."]],
  ["live_state", "data", ["Online / Idle / Offline (Live POS)", "Online: data in the last 15 minutes · Idle: up to 2 hours · Offline: more.", "If an open branch shows Offline, check its POS internet connection."],
    ["متصل / خامل / غير متصل (الكاشير المباشر)", "متصل: بيانات آخر 15 دقيقة · خامل: لحد ساعتين · غير متصل: أكتر.", "لو فرع شغال وظاهر غير متصل، راجع إنترنت الكاشير."]],

  // ------------------------------------------------------------ security
  ["roles", "security", ["Roles & permissions", "Which pages and abilities each group of users gets.", "Users & roles → Roles & permissions: tick a box to show a page for that role, untick to hide it. A user can also be limited to certain branches."],
    ["الأدوار والصلاحيات", "كل مجموعة مستخدمين بتشوف أنهي صفحات وبتعمل إيه.", "المستخدمون والصلاحيات ← الأدوار والصلاحيات: علّم المربع عشان تظهر الصفحة للدور ده، وشيله عشان تختفي. وكمان ممكن تحدد للمستخدم فروع معينة بس."]],
  ["phones_masked", "security", ["Hidden phone numbers", "01x****5678 - shown when the role can't see full phone numbers.", "Controlled by the permission 'See full phone numbers'."],
    ["أرقام مخفية", "01x****5678 - بتظهر كده لو الدور مش مسموح له يشوف الرقم كامل.", "بتتحكم فيها صلاحية 'رؤية أرقام الموبايل كاملة'."]],
  ["two_factor", "security", ["Google Authenticator (2-step sign-in)", "After the password, a 6-digit code from your phone.", "Turn it on in My account. The code changes every 30 seconds. Lost phone? An admin can reset it from Users & roles."],
    ["Google Authenticator (الدخول بخطوتين)", "بعد كلمة المرور بتكتب كود من 6 أرقام من موبايلك.", "فعّله من حسابي. الكود بيتغير كل 30 ثانية. ضاع الموبايل؟ المدير يقدر يعيد ضبطه من المستخدمون والصلاحيات."]],
  ["audit", "security", ["Audit log", "Who did what and when.", "Sign-ins, exports, customer views, uploads, setting and user changes."],
    ["سجل التدقيق", "مين عمل إيه وإمتى.", "الدخول، التنزيلات، فتح ملفات العملاء، الرفع، وتغييرات الإعدادات والمستخدمين."]],
];

// make "glossary.terms.<key>.short" available to t() (used by the "?" help icons)
const pack = (idx: 2 | 3) => Object.fromEntries(TERMS.map((e) => [e[0], { name: e[idx][0], short: e[idx][1], long: e[idx][2] }]));
i18n.addResourceBundle("en", "translation", { glossary: { terms: pack(2) } }, true, false);
i18n.addResourceBundle("ar", "translation", { glossary: { terms: pack(3) } }, true, false);
