import json
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
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


def public_user(u: dict) -> dict:
    return {"id": u["id"], "username": u["username"], "full_name": u["full_name"],
            "role": u["role"], "branches": json.loads(u["branches"] or "[]"),
            "language": u["language"], "active": u["active"]}


def get_user_by_id(uid: int):
    return db.one(db.cursor(), "SELECT * FROM users WHERE id = ?", [uid])


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(cred.credentials, config.SECRET_KEY, algorithms=["HS256"])
        u = get_user_by_id(int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        u = None
    if not u or not u["active"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, please log in again")
    return public_user(u)


def admin_user(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return user


def ensure_admin_exists():
    cur = db.cursor()
    if cur.execute("SELECT count(*) FROM users").fetchone()[0]:
        return
    pw = config.ADMIN_PASSWORD
    generated = not pw
    if generated:
        pw = secrets.token_urlsafe(10)
    cur.execute(
        "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, 'admin')",
        [config.ADMIN_USERNAME, hash_password(pw), "Administrator"])
    if generated:
        msg = f"Created admin user '{config.ADMIN_USERNAME}' with password: {pw}"
        print("=" * len(msg), msg, "Change it after logging in.", "=" * len(msg), sep="\n",
              flush=True)
