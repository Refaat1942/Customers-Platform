import json
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config, db

_bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def make_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=config.TOKEN_HOURS)
    return jwt.encode({"sub": str(user_id), "exp": exp}, config.SECRET_KEY, algorithm="HS256")


def role_permissions(role: str) -> list[str]:
    r = db.one(db.cursor(), "SELECT permissions FROM roles WHERE name = ?", [role])
    return json.loads(r["permissions"]) if r else []


def public_user(u: dict) -> dict:
    return {"id": u["id"], "username": u["username"], "full_name": u["full_name"],
            "role": u["role"], "branches": json.loads(u["branches"] or "[]"),
            "language": u["language"], "active": u["active"],
            "created_at": u.get("created_at")}


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")


def current_user(request: Request,
                 cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    token = cred.credentials if cred else None
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
        u = db.one(db.cursor(), "SELECT * FROM users WHERE id = ?", [int(payload["sub"])])
    except (jwt.PyJWTError, KeyError, ValueError):
        u = None
    if not u or not u["active"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, please log in again")
    user = public_user(u)
    user["permissions"] = role_permissions(u["role"])
    user["ip"] = client_ip(request)
    user["default_password"] = u["username"] == config.ADMIN_USERNAME and \
        check_password(config.ADMIN_PASSWORD, u["password_hash"])
    return user


def require(*perms: str):
    """Dependency: the user needs ANY of the given permissions."""
    def dep(user: dict = Depends(current_user)) -> dict:
        if not any(p in user["permissions"] for p in perms):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this")
        return user
    return dep


def ensure_admin_exists():
    cur = db.cursor()
    if cur.execute("SELECT count(*) FROM users").fetchone()[0]:
        return
    cur.execute(
        "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, 'admin')",
        [config.ADMIN_USERNAME, hash_password(config.ADMIN_PASSWORD), "Administrator"])
    print(f"Created first admin user '{config.ADMIN_USERNAME}'. Change its password after "
          "logging in.", flush=True)


# ---- simple brute-force protection: 10 failed logins per IP+user per 15 minutes ----
_fails: dict[str, list[float]] = defaultdict(list)


def login_allowed(key: str) -> bool:
    now = time.time()
    _fails[key] = [t for t in _fails[key] if now - t < 900]
    return len(_fails[key]) < 10


def login_failed(key: str):
    _fails[key].append(time.time())
