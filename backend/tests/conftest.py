import os
import tempfile

_d = tempfile.mkdtemp(prefix="cp-test-")
os.environ["DATA_DIR"] = _d
os.environ["DB_PATH"] = os.path.join(_d, "test.duckdb")
os.environ["ADMIN_PASSWORD"] = "admin-pass-123"
os.environ["FRONTEND_DIST"] = os.path.join(_d, "nofrontend")
