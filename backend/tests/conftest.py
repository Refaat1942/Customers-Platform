import os
import tempfile

_d = tempfile.mkdtemp(prefix="cp-test-")
os.environ["DATA_DIR"] = _d
os.environ.setdefault("DATABASE_URL", "postgresql://postgres@/customers_test?host=/var/lib/pgtest&port=5433")
os.environ["ADMIN_PASSWORD"] = "admin-pass-123"
os.environ["FRONTEND_DIST"] = os.path.join(_d, "nofrontend")

import psycopg  # noqa: E402

with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as _c:
    _c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
