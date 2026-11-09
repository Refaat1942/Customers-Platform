from PyQt6 import QtWidgets, QtGui
import pandas as pd
from ui_helpers import PandasModel, accounting
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


# ==========================================================
# SETUP AI TAB
# ==========================================================
def setup_ai_tab(self):
    layout = QtWidgets.QVBoxLayout(self.tab_ai)

    title_font = QtGui.QFont()
    title_font.setPointSize(13)
    title_font.setBold(True)

    # ---------------- TOP BAR ----------------
    top = QtWidgets.QHBoxLayout()

    top.addWidget(QtWidgets.QLabel("Branch"))

    self.ai_branch = QtWidgets.QComboBox()
    self.ai_branch.setFixedWidth(220)
    top.addWidget(self.ai_branch)

    btn_run = QtWidgets.QPushButton("Analyze Customers")
    btn_run.clicked.connect(lambda: run_customer_overview(self))
    top.addWidget(btn_run)

    top.addStretch()
    layout.addLayout(top)

    # ---------------- KPIs ----------------
    kpi = QtWidgets.QHBoxLayout()

    self.kpi_customers = QtWidgets.QLabel("Total Customers: 0")
    self.kpi_sales = QtWidgets.QLabel("Total Sales: 0")
    self.kpi_avg = QtWidgets.QLabel("Average Spend per Customer: 0")

    for w in (self.kpi_customers, self.kpi_sales, self.kpi_avg):
        w.setFont(title_font)
        kpi.addWidget(w)
        kpi.addStretch()

    layout.addLayout(kpi)

    # ---------------- TABLE ----------------
    layout.addWidget(QtWidgets.QLabel("Customer Overview"))

    self.tbl_overview = QtWidgets.QTableView()
    layout.addWidget(self.tbl_overview)

    # ---------------- SUMMARY ----------------
    layout.addWidget(QtWidgets.QLabel("Business Summary"))

    self.ai_summary = QtWidgets.QTextEdit()
    self.ai_summary.setReadOnly(True)
    self.ai_summary.setFixedHeight(120)
    layout.addWidget(self.ai_summary)

    # ---------------- EXPORT ----------------
    export_row = QtWidgets.QHBoxLayout()

    btn_excel = QtWidgets.QPushButton("Export Excel")
    btn_pdf = QtWidgets.QPushButton("Export PDF")

    btn_excel.clicked.connect(lambda: export_excel(self))
    btn_pdf.clicked.connect(lambda: export_pdf(self))

    export_row.addWidget(btn_excel)
    export_row.addWidget(btn_pdf)
    export_row.addStretch()

    layout.addLayout(export_row)

    self._branches_loaded = False
    self._last_df = None


# ==========================================================
# MAIN LOGIC
# ==========================================================
def run_customer_overview(self):
    if self.df is None or self.df.empty:
        QtWidgets.QMessageBox.information(
            self, "No Data", "Please load data first"
        )
        return

    df = self.df.copy()

    phone = self.colmap.get("phone")
    name = self.colmap.get("name")
    branch = self.colmap.get("branch")
    price = self.colmap.get("item_price")
    date = self.colmap.get("invoice_date")

    # ---------- Validate ----------
    for col, label in [
        (phone, "Phone"),
        (price, "Price"),
        (date, "Invoice Date"),
    ]:
        if not col or col not in df.columns:
            QtWidgets.QMessageBox.critical(
                self, "Missing Column",
                f"Required column missing: {label}"
            )
            return

    # ---------- Load branches once ----------
    if branch and branch in df.columns and not self._branches_loaded:
        self.ai_branch.blockSignals(True)
        self.ai_branch.clear()
        self.ai_branch.addItem("All")
        for b in sorted(df[branch].dropna().astype(str).unique()):
            self.ai_branch.addItem(b)
        self.ai_branch.blockSignals(False)
        self._branches_loaded = True

    # ---------- Apply branch filter ----------
    selected_branch = self.ai_branch.currentText()
    if branch and branch in df.columns:
        if selected_branch and selected_branch != "All":
            df = df[df[branch].astype(str) == selected_branch]

    # ---------- Fix date ----------
    df[date] = pd.to_datetime(df[date], errors="coerce")

    # ---------- KPIs ----------
    total_customers = df[phone].nunique()
    total_sales = df[price].sum()
    avg_spend = total_sales / total_customers if total_customers else 0

    self.kpi_customers.setText(f"Total Customers: {total_customers}")
    self.kpi_sales.setText(f"Total Sales: {accounting(total_sales)}")
    self.kpi_avg.setText(f"Average Spend per Customer: {accounting(avg_spend)}")

    # ---------- Build overview ----------
    agg = {
        price: "sum",
        date: "max",
    }

    if name and name in df.columns:
        agg[name] = "first"

    if branch and branch in df.columns:
        agg[branch] = "first"

    visits = df.groupby(phone).size().rename("Total Visits")

    overview = (
        df.groupby(phone)
        .agg(agg)
        .join(visits)
        .reset_index()
    )

    overview.rename(columns={
        phone: "Customer Phone",
        price: "Total Spend",
        date: "Last Visit Date",
        name: "Customer Name",
        branch: "Branch",
    }, inplace=True)

    today = pd.Timestamp.today()

    overview["Days Since Last Visit"] = (
        today - overview["Last Visit Date"]
    ).dt.days

    overview["Average Spend per Visit"] = (
        overview["Total Spend"] / overview["Total Visits"]
    ).round(2)

    # ---------- Status ----------
    def status(days):
        if days <= 30:
            return "Active"
        if days <= 60:
            return "Needs Attention"
        return "Inactive"

    overview["Customer Status"] = overview["Days Since Last Visit"].apply(status)

    # ---------- Action ----------
    def action(s):
        if s == "Active":
            return "Keep engaged"
        if s == "Needs Attention":
            return "Send offer"
        return "Call customer"

    overview["Business Action"] = overview["Customer Status"].apply(action)

    overview = overview.sort_values(
        by=["Customer Status", "Total Spend"],
        ascending=[True, False]
    )

    self._last_df = overview

    # ---------- Show ----------
    self.tbl_overview.setModel(PandasModel(overview))
    self.tbl_overview.resizeColumnsToContents()
    self.tbl_overview.horizontalHeader().setStretchLastSection(True)

    # ---------- Summary ----------
    self.ai_summary.setText(
        f"Total Customers: {total_customers}\n"
        f"Inactive Customers: {(overview['Customer Status']=='Inactive').sum()}\n"
        f"Customers Needing Attention: {(overview['Customer Status']=='Needs Attention').sum()}\n"
        "Focus on inactive and high-spend customers first."
    )


# ==========================================================
# EXPORT
# ==========================================================
def export_excel(self):
    if self._last_df is None or self._last_df.empty:
        return

    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        self, "Save Excel", "Customer_Overview.xlsx", "Excel Files (*.xlsx)"
    )
    if path:
        self._last_df.to_excel(path, index=False)


def export_pdf(self):
    if self._last_df is None or self._last_df.empty:
        return

    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        self, "Save PDF", "Customer_Overview.pdf", "PDF Files (*.pdf)"
    )
    if not path:
        return

    c = canvas.Canvas(path, pagesize=A4)
    y = 800
    c.setFont("Helvetica", 11)

    c.drawString(40, y, "Customer Overview Report")
    y -= 30

    for line in self.ai_summary.toPlainText().split("\n"):
        c.drawString(40, y, line)
        y -= 14

    c.save()
