from PyQt6 import QtWidgets, QtCore
import pandas as pd
from customer_view import CustomerFullView
from ui_helpers import accounting

def setup_customer_tab(self):
    layout = QtWidgets.QVBoxLayout(self.tab_customer)

    # =========================
    # Filters row
    # =========================
    filter_row = QtWidgets.QHBoxLayout()

    self.customer_branch_filter = QtWidgets.QComboBox()
    self.customer_branch_filter.addItem("All Branches")
    filter_row.addWidget(self.customer_branch_filter)

    self.customer_phone_filter = QtWidgets.QLineEdit()
    self.customer_phone_filter.setPlaceholderText("Filter by phone...")
    filter_row.addWidget(self.customer_phone_filter)

    btn_apply = QtWidgets.QPushButton("Apply Filter")
    filter_row.addWidget(btn_apply)

    # ---------------------------------------------------------
    # زر جديد لاستخراج تحليل العملاء لملف إكسيل
    # ---------------------------------------------------------
    btn_export_all = QtWidgets.QPushButton("Export All Summaries (Excel)")
    btn_export_all.setStyleSheet("background-color: #e3f2fd; color: #0d47a1; font-weight: bold;")
    btn_export_all.clicked.connect(lambda: export_customers_summary(self))
    filter_row.addWidget(btn_export_all)

    layout.addLayout(filter_row)

    # =========================
    # Scroll area
    # =========================
    self.customer_scroll = QtWidgets.QScrollArea()
    self.customer_scroll.setWidgetResizable(True)

    self.customer_container = QtWidgets.QWidget()
    self.customer_layout = QtWidgets.QVBoxLayout(self.customer_container)
    self.customer_scroll.setWidget(self.customer_container)

    layout.addWidget(self.customer_scroll)

    # cache
    self._customer_cache = {}

    def apply_customer_filters():
        base_df = self.df
        if base_df is None or base_df.empty:
            populate_customer_buttons(self, pd.DataFrame())
            return

        branch_col = self.colmap.get("branch")
        phone_col = self.colmap.get("phone")

        df = base_df.copy()

        branch = self.customer_branch_filter.currentText()
        phone_txt = self.customer_phone_filter.text().strip()

        if branch_col and branch != "All Branches":
            df = df[df[branch_col].astype(str) == branch]

        if phone_txt and phone_col:
            df = df[df[phone_col].astype(str).str.contains(phone_txt, na=False)]
        
        # حفظ النتيجة الحالية لاستخدامها في التصدير
        self._current_customer_df = df 

        populate_customer_buttons(self, df)

    btn_apply.clicked.connect(apply_customer_filters)


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w:
            w.setParent(None)


def populate_customer_buttons(self, df):
    clear_layout(self.customer_layout)

    if df is None or df.empty:
        self.customer_layout.addWidget(QtWidgets.QLabel("No data."))
        return

    phone_col = self.colmap.get("phone")
    name_col = self.colmap.get("name")
    branch_col = self.colmap.get("branch")

    if not phone_col or phone_col not in df.columns:
        self.customer_layout.addWidget(QtWidgets.QLabel("No phone column found."))
        return

    # populate branch filter ONCE
    if (
        branch_col
        and branch_col in self.df.columns
        and not hasattr(self, "_customer_branches_loaded")
    ):
        self.customer_branch_filter.blockSignals(True)
        self.customer_branch_filter.clear()
        self.customer_branch_filter.addItem("All Branches")
        self.customer_branch_filter.addItems(
            sorted(self.df[branch_col].dropna().astype(str).unique())
        )
        self.customer_branch_filter.blockSignals(False)
        self._customer_branches_loaded = True

    # عرض أول 100 عميل فقط لتجنب تعليق الواجهة، لكن التصدير سيكون للكل
    phones = df[phone_col].dropna().unique().tolist()[:100]

    lbl_info = QtWidgets.QLabel(f"Showing first {len(phones)} customers (Use Export for full analysis)")
    lbl_info.setStyleSheet("color: gray; font-style: italic;")
    self.customer_layout.addWidget(lbl_info)

    for p in phones:
        subdf = df[df[phone_col] == p]
        label = str(p)

        if name_col and name_col in subdf.columns:
            nm = subdf[name_col].dropna().astype(str)
            if not nm.empty:
                label += f" - {nm.iloc[0]}"

        btn = QtWidgets.QPushButton(label)
        btn.setStyleSheet("text-align:left; padding:8px; font-size:14px;")

        btn.clicked.connect(
            lambda _, gdf=subdf.copy(): CustomerFullView(self, gdf, self.colmap).exec()
        )

        self.customer_layout.addWidget(btn)

    self.customer_layout.addStretch()


# ============================================================
#               LOGIC FOR EXPORTING SUMMARY
# ============================================================

def export_customers_summary(self):
    """
    يقوم بحساب الإحصائيات لكل العملاء وتصديرها لإكسيل
    """
    # التأكد من وجود داتا مفلترة أو استخدام الداتا الأصلية
    if hasattr(self, "_current_customer_df") and not self._current_customer_df.empty:
        df = self._current_customer_df.copy()
    elif hasattr(self, "df") and not self.df.empty:
        df = self.df.copy()
    else:
        QtWidgets.QMessageBox.warning(self, "Error", "No data to export.")
        return

    # التأكد من الأعمدة
    phone_col = self.colmap.get("phone")
    date_col = self.colmap.get("invoice_date")
    price_col = self.colmap.get("item_price")
    name_col = self.colmap.get("name")
    type_col = self.colmap.get("invoice_type")
    branch_col = self.colmap.get("branch")

    if not phone_col or not date_col:
        QtWidgets.QMessageBox.warning(self, "Error", "Phone or Date column missing.")
        return

    # تجهيز التاريخ
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

    # 1. التجميع الأساسي (المجموع، العدد، أول وآخر زيارة)
    agg_rules = {
        price_col: "sum" if price_col else "count",
        date_col: ["min", "max", "nunique"], # nunique counts visits
    }
    
    # إضافة الاسم والفرع (ناخذ أول قيمة)
    if name_col: agg_rules[name_col] = "first"
    if branch_col: agg_rules[branch_col] = "first"

    # تجميع الداتا
    grouped = df.groupby(phone_col).agg(agg_rules)
    
    # فك التجميع (Flatten columns)
    grouped.columns = ["_".join(col).strip() for col in grouped.columns.values]
    grouped = grouped.reset_index()

    # إعادة تسمية الأعمدة لتكون مفهومة
    rename_map = {
        phone_col + "_": "Phone", # sometimes happens
        phone_col: "Phone",
        f"{price_col}_sum": "Total Spend",
        f"{date_col}_min": "First Visit",
        f"{date_col}_max": "Last Visit",
        f"{date_col}_nunique": "Visit Count",
        f"{name_col}_first": "Name",
        f"{branch_col}_first": "Branch"
    }
    grouped.rename(columns=rename_map, inplace=True)

    # 2. حساب متوسط الأيام بين الزيارات (Complex Calculation)
    # سنقوم بعمل دالة مخصصة وتطبيقها
    
    # نصفي الداتا للعملاء الذين لديهم أكثر من زيارة فقط لتسريع الحساب
    multi_visit_phones = grouped[grouped["Visit Count"] > 1]["Phone"].unique()
    
    # نحسب الأيام فقط لهؤلاء
    avg_days_map = {}
    
    if len(multi_visit_phones) > 0:
        # نأخذ الداتا المصغرة للحساب السريع
        df_visits = df[df[phone_col].isin(multi_visit_phones)][[phone_col, date_col]].drop_duplicates()
        
        for phone, sub in df_visits.groupby(phone_col):
            dates = sub[date_col].sort_values()
            if len(dates) > 1:
                diff = dates.diff().dt.days.mean()
                avg_days_map[phone] = round(diff, 1)

    grouped["Avg Days Between Visits"] = grouped["Phone"].map(avg_days_map).fillna(0)

    # 3. أكثر نوع مبيعات استخداماً (Most Frequent Sales Type)
    if type_col:
        mode_series = df.groupby(phone_col)[type_col].agg(lambda x: x.mode().iloc[0] if not x.mode().empty else "")
        grouped["Most Used Type"] = grouped["Phone"].map(mode_series)

    # ترتيب الأعمدة للشكل النهائي
    final_cols = ["Phone", "Name", "Branch", "Total Spend", "Visit Count", "First Visit", "Last Visit", "Avg Days Between Visits"]
    if type_col:
        final_cols.append("Most Used Type")
    
    # التأكد أن الأعمدة موجودة (بعضها قد يكون غير موجود بناء على الداتا)
    final_cols = [c for c in final_cols if c in grouped.columns]
    
    final_df = grouped[final_cols]

    # حفظ الملف
    fname = "customers_full_analysis_summary.xlsx"
    path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Analysis", fname, "Excel Files (*.xlsx)")
    
    if path:
        try:
            final_df.to_excel(path, index=False)
            QtWidgets.QMessageBox.information(self, "Success", f"Saved {len(final_df)} customers to:\n{path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Could not save file:\n{e}")