from PyQt6 import QtWidgets, QtGui
from ui_helpers import PandasModel, accounting
import business_analysis as ba
import pandas as pd


# ==========================================================
# SETUP TAB UI
# ==========================================================
def setup_overall_tab(self):
    layout = QtWidgets.QVBoxLayout(self.tab_overall)

    title_font = QtGui.QFont()
    title_font.setPointSize(13)
    title_font.setBold(True)

    sub_font = QtGui.QFont()
    sub_font.setPointSize(9)

    # ------------------ FILTER + RUN ROW ------------------
    top_row = QtWidgets.QHBoxLayout()

    top_row.addWidget(QtWidgets.QLabel("Branch Filter:"))
    self.overall_branch_filter = QtWidgets.QComboBox()
    self.overall_branch_filter.setFixedWidth(200)
    top_row.addWidget(self.overall_branch_filter)

    self.btn_run_overall = QtWidgets.QPushButton("Run Overall Summary")
    self.btn_run_overall.setFixedWidth(180)
    self.btn_run_overall.clicked.connect(
        lambda: update_overall_metrics(self, force=True)
    )
    top_row.addWidget(self.btn_run_overall)

    top_row.addStretch()
    layout.addLayout(top_row)

    # ------------------ CONTEXT LABEL ------------------
    self.overall_context = QtWidgets.QLabel("Based on: Full Data")
    self.overall_context.setFont(sub_font)
    self.overall_context.setStyleSheet("color: #555;")
    layout.addWidget(self.overall_context)

    # ------------------ KPI ROW ------------------
    kpi_row = QtWidgets.QHBoxLayout()

    self.kpi_clients = QtWidgets.QLabel("Clients: 0")
    self.kpi_clients.setFont(title_font)
    kpi_row.addWidget(self.kpi_clients)
    kpi_row.addStretch()

    self.kpi_invoices = QtWidgets.QLabel("Invoices: 0")
    self.kpi_invoices.setFont(title_font)
    kpi_row.addWidget(self.kpi_invoices)
    kpi_row.addStretch()

    self.kpi_total_sales = QtWidgets.QLabel("Total Sales: 0.00")
    self.kpi_total_sales.setFont(title_font)
    kpi_row.addWidget(self.kpi_total_sales)
    kpi_row.addStretch()

    self.kpi_avg_spend = QtWidgets.QLabel("Avg Spend/Client: 0.00")
    self.kpi_avg_spend.setFont(title_font)
    kpi_row.addWidget(self.kpi_avg_spend)

    layout.addLayout(kpi_row)

    # ------------------ INSIGHTS TABLE ------------------
    label_insights = QtWidgets.QLabel("\nBusiness Insights")
    label_insights.setFont(title_font)
    layout.addWidget(label_insights)

    self.insights_table = QtWidgets.QTableView()
    layout.addWidget(self.insights_table)

    # ------------------ EXPORT BUTTONS ------------------
    btn_row = QtWidgets.QHBoxLayout()

    self.btn_export_high_value = QtWidgets.QPushButton(
        "Export High Value Customers"
    )
    self.btn_export_high_value.setFixedWidth(260)
    self.btn_export_high_value.clicked.connect(
        lambda: export_high_value(self)
    )
    btn_row.addWidget(self.btn_export_high_value)

    self.btn_export_at_risk = QtWidgets.QPushButton(
        "Export At-Risk Customers"
    )
    self.btn_export_at_risk.setFixedWidth(260)
    self.btn_export_at_risk.clicked.connect(
        lambda: export_at_risk(self)
    )
    btn_row.addWidget(self.btn_export_at_risk)

    btn_row.addStretch()
    layout.addLayout(btn_row)


# ==========================================================
# MAIN UPDATE FUNCTION
# ==========================================================
def update_overall_metrics(self, force=False):
    if not hasattr(self, "_overall_cache"):
        self._overall_cache = {}

    df_base = self.df
    if df_base is None or df_base.empty:
        return

    phone_col = self.colmap.get("phone")
    name_col = self.colmap.get("name")
    branch_col = self.colmap.get("branch")
    price_col = self.colmap.get("item_price")
    date_col = self.colmap.get("invoice_date")
    time_col = self.colmap.get("invoice_time")
    type_col = self.colmap.get("invoice_type")
    mat_col = self.colmap.get("material_group")
    cat_col = self.colmap.get("item_category")

    # ------------------ FIX: Smart Branch Filter Population ------------------
    # بدلاً من التحميل مرة واحدة، نتأكد هل الفروع تغيرت أم لا
    
    current_branches = []
    if branch_col and branch_col in df_base.columns:
        current_branches = sorted(df_base[branch_col].dropna().astype(str).unique())
    
    # جلب العناصر الحالية في القائمة (ما عدا All)
    existing_items = [self.overall_branch_filter.itemText(i) for i in range(self.overall_branch_filter.count())]
    if "All" in existing_items:
        existing_items.remove("All")
    
    # المقارنة: إذا كانت الفروع في الداتا تختلف عن الموجود في القائمة، نعيد التحميل
    if set(current_branches) != set(existing_items):
        self.overall_branch_filter.blockSignals(True)
        old_selection = self.overall_branch_filter.currentText()
        
        self.overall_branch_filter.clear()
        self.overall_branch_filter.addItem("All")
        self.overall_branch_filter.addItems(current_branches)
        
        # محاولة استعادة الاختيار السابق
        idx = self.overall_branch_filter.findText(old_selection)
        if idx >= 0:
            self.overall_branch_filter.setCurrentIndex(idx)
        else:
            self.overall_branch_filter.setCurrentIndex(0) # All
            
        self.overall_branch_filter.blockSignals(False)

    # -------------------------------------------------------------------------

    selected_branch = self.overall_branch_filter.currentText() or "All"
    cache_key = selected_branch

    self.overall_context.setText(
        f"Based on: Branch = {selected_branch}"
    )

    if not force and cache_key in self._overall_cache:
        _apply_overall_result(self, self._overall_cache[cache_key])
        return

    # ------------------ FILTER DATA ------------------
    df = df_base.copy()
    if selected_branch != "All" and branch_col in df.columns:
        df = df[df[branch_col].astype(str) == selected_branch]

    if date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

    # ------------------ KPIs ------------------
    clients = df[phone_col].nunique()

    if time_col in df.columns:
        df["_invoice_key"] = (
            df[phone_col].astype(str)
            + "_"
            + df[date_col].dt.strftime("%Y-%m-%d")
            + "_"
            + df[time_col].astype(str)
        )
        invoices = df["_invoice_key"].nunique()
    else:
        invoices = df[date_col].dt.date.nunique()

    total_sales = df[price_col].sum()
    avg_spend = total_sales / clients if clients else 0

    # ------------------ INSIGHTS ------------------
    def safe_mode(series):
        s = series.dropna().astype(str)
        return s.mode().iloc[0] if not s.empty else "N/A"

    insights = [
        ["Top Branch", safe_mode(df[branch_col])],
        ["Top Season", safe_mode(df[date_col].dt.month.map(ba.month_to_season))],
        ["Top Sales Type", safe_mode(df[type_col])],
        ["Top Material Group", safe_mode(df[mat_col])],
        ["Top Item Category", safe_mode(df[cat_col])],
    ]

    # ------------------ DETAILED CUSTOMER TABLE ------------------
    # تجميع سريع للعملاء لتصدير القوائم (High Value / At Risk)
    cust_df = df.groupby(phone_col).agg({
        price_col: "sum",
        date_col: "max",
        branch_col: "first",
        name_col: "first" if name_col in df.columns else "first",
    }).reset_index()

    cust_df.rename(columns={
        phone_col: "Customer Phone",
        name_col: "Customer Name",
        price_col: "Total Spend",
        date_col: "Last Visit",
        branch_col: "Branch",
    }, inplace=True)

    today = pd.Timestamp.today()
    cust_df["Customer Status"] = "Normal"
    cust_df.loc[cust_df["Total Spend"] >= 10000, "Customer Status"] = "High Value"
    cust_df.loc[
        today - cust_df["Last Visit"] >= pd.Timedelta(days=60),
        "Customer Status"
    ] = "At Risk"

    self._overall_customers_df = cust_df

    result = {
        "clients": clients,
        "invoices": invoices,
        "total_sales": total_sales,
        "avg_spend": avg_spend,
        "insights": insights,
    }

    self._overall_cache[cache_key] = result
    _apply_overall_result(self, result)


def _apply_overall_result(self, res):
    self.kpi_clients.setText(f"Clients: {res['clients']}")
    self.kpi_invoices.setText(f"Invoices: {res['invoices']}")
    self.kpi_total_sales.setText(
        f"Total Sales: {accounting(res['total_sales'])}"
    )
    self.kpi_avg_spend.setText(
        f"Avg Spend/Client: {accounting(res['avg_spend'])}"
    )

    df_insights = pd.DataFrame(
        res["insights"], columns=["Metric", "Value"]
    )
    self.insights_table.setModel(PandasModel(df_insights))
    self.insights_table.horizontalHeader().setStretchLastSection(True)


# ==========================================================
# EXPORTS (DETAILED & BUSINESS READY)
# ==========================================================
def export_high_value(self):
    if not hasattr(self, "_overall_customers_df"):
        return

    df = self._overall_customers_df
    df = df[df["Customer Status"] == "High Value"]

    if df.empty:
        QtWidgets.QMessageBox.information(
            self, "No Data", "No High Value customers found"
        )
        return

    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        self,
        "Export High Value Customers",
        "high_value_customers.xlsx",
        "Excel Files (*.xlsx)"
    )
    if path:
        df.to_excel(path, index=False)


def export_at_risk(self):
    if not hasattr(self, "_overall_customers_df"):
        return

    df = self._overall_customers_df
    df = df[df["Customer Status"] == "At Risk"]

    if df.empty:
        QtWidgets.QMessageBox.information(
            self, "No Data", "No At-Risk customers found"
        )
        return

    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        self,
        "Export At-Risk Customers",
        "at_risk_customers.xlsx",
        "Excel Files (*.xlsx)"
    )
    if path:
        df.to_excel(path, index=False)