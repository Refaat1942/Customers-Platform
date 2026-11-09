# ui_helpers.py
import os
import pandas as pd
from PyQt6 import QtCore


# ======================================================
# Formatting helpers
# ======================================================
def accounting(x):
    try:
        return f"{float(x):,.2f}"
    except Exception:
        return str(x)


# ======================================================
# Pandas → Qt Table Model
# ======================================================
class PandasModel(QtCore.QAbstractTableModel):
    def __init__(self, df=pd.DataFrame(), parent=None):
        super().__init__(parent)
        self._df = df.copy()

    def update(self, df):
        self.beginResetModel()
        self._df = df.copy()
        self.endResetModel()

    def rowCount(self, parent=None):
        return 0 if self._df is None else len(self._df)

    def columnCount(self, parent=None):
        return 0 if self._df is None or self._df.empty else len(self._df.columns)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self._df is None or self._df.empty:
            return None

        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            val = self._df.iat[index.row(), index.column()]
            return str(val)

        return None

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == QtCore.Qt.Orientation.Horizontal:
            return str(self._df.columns[section])
        else:
            return str(self._df.index[section])


# ======================================================
# SAFE Excel Loader (NO CRASH)
# ======================================================
def read_excel_with_fallback(path, status_callback=None):
    """
    Safe Excel reader.
    - Uses pandas only (more stable than duckdb for large files)
    - Raises errors instead of silent crash
    """

    if status_callback:
        status_callback("Reading Excel file...")

    try:
        df = pd.read_excel(path, engine="openpyxl")

        if status_callback:
            status_callback(f"Loaded {len(df):,} rows")

        return df

    except Exception as e:
        if status_callback:
            status_callback(f"Failed to load file: {e}")
        raise


# ======================================================
# Resources
# ======================================================
def resource_logo_path():
    local_path = "Lotus.png"
    if os.path.exists(local_path):
        return local_path
    return None
