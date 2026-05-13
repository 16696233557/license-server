"""授权服务端 - API路由"""
from fastapi import APIRouter, HTTPException, Form, Request, Depends
from datetime import datetime, timedelta
import hashlib, uuid, secrets, jwt, time
from app.database import get_db_context, get_db

router = APIRouter(prefix="/api", tags=["授权API"])

SECRET = "license-server-secret-key-change-me"
ALGO = "HS256"

def get_server_secret():
    conn = get_db()
    conn.execute("PRAGMA busy_timeout=30000")
    c = conn.cursor()
    c.execute("SELECT value FROM config WHERE key = 'server_secret'")
    row = c.fetchone()
    conn.close()
    return row["value"] if row else "change-me"

def generate_license_key() -> str:
    """生成随机license key: XXXX-XXXX-XXXX-XXXX"""
    raw = secrets.token_hex(8).upper()
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:]}"

def sign_key(key: str, secret: str) -> str:
    return hashlib.sha256(f"{key}:{secret}".encode()).hexdigest()[:16].upper()

def verify_admin(username: str, password: str) -> bool:
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    with get_db_context() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM admins WHERE username = ? AND password_hash = ?", (username, pwd_hash))
        return c.fetchone() is not None

def create_admin_token(username: str) -> str:
    payload = {"sub": username, "exp": datetime.utcnow() + timedelta(hours=12)}
    return jwt.encode(payload, SECRET, algorithm=ALGO)

def verify_admin_token(token: str) -> bool:
    try:
        jwt.decode(token, SECRET, algorithms=[ALGO])
        return True
    except:
        return False

# ========== 客户端调用 ==========

@router.post("/verify")
def verify_license(key: str = Form(...), machine_code: str = Form(...)):
    """验证卡密（客户端启动时调用）"""
    with get_db_context() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, customer_name, expires_at, is_active
            FROM licenses WHERE key = ? AND (machine_code = ? OR machine_code = '')
        """, (key, machine_code))
        row = c.fetchone()

        if not row:
            return {"valid": False, "message": "卡密无效"}

        if not row["is_active"]:
            return {"valid": False, "message": "卡密已被封禁"}

        expires = datetime.strptime(row["expires_at"], "%Y-%m-%d")
        if expires < datetime.now():
            return {"valid": False, "message": f"卡密已于 {row['expires_at']} 到期", "expired": True}

        # 更新最后验证时间
        c.execute("UPDATE licenses SET last_verify_at = datetime('now', 'localtime') WHERE id = ?", (row["id"],))

        return {
            "valid": True,
            "message": "验证通过",
            "expires_at": row["expires_at"],
            "customer_name": row["customer_name"]
        }

@router.get("/check")
def check_license(key: str, machine_code: str):
    """轻量检查（不更新验证时间）"""
    with get_db_context() as conn:
        c = conn.cursor()
        c.execute("SELECT expires_at, is_active FROM licenses WHERE key = ? AND machine_code = ?", (key, machine_code))
        row = c.fetchone()
        if not row:
            return {"valid": False}
        if not row["is_active"]:
            return {"valid": False, "message": "已封禁"}
        expires = datetime.strptime(row["expires_at"], "%Y-%m-%d")
        return {"valid": expires >= datetime.now(), "expires_at": row["expires_at"]}

# ========== 管理后台API ==========

@router.post("/admin/login")
def admin_login(username: str = Form(...), password: str = Form(...)):
    if not verify_admin(username, password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_admin_token(username)
    return {"token": token, "username": username}

@router.get("/admin/licenses")
def list_licenses(authorization: str = None):
    if not authorization or not verify_admin_token(authorization):
        raise HTTPException(status_code=401, detail="未登录")
    with get_db_context() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM licenses ORDER BY created_at DESC")
        rows = c.fetchall()
        return [dict(r) for r in rows]

@router.post("/admin/licenses")
def create_license(
    customer_name: str = Form(...),
    duration_days: int = Form(...),
    machine_code: str = Form(default=""),
    authorization: str = Form(...)
):
    if not verify_admin_token(authorization):
        raise HTTPException(status_code=401, detail="未登录")

    key = generate_license_key()
    expires = (datetime.now() + timedelta(days=duration_days)).strftime("%Y-%m-%d")
    secret = get_server_secret()
    signature = sign_key(key, secret)

    with get_db_context() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO licenses (key, customer_name, machine_code, expires_at)
            VALUES (?, ?, ?, ?)
        """, (key, customer_name, machine_code, expires))
        lid = c.lastrowid
        c.execute("SELECT * FROM licenses WHERE id = ?", (lid,))
        lic = dict(c.fetchone())

    return {**lic, "signature": signature}

@router.delete("/admin/licenses/{license_id}")
def revoke_license(license_id: int, authorization: str = None):
    if not verify_admin_token(authorization):
        raise HTTPException(status_code=401, detail="未登录")
    with get_db_context() as conn:
        c = conn.cursor()
        c.execute("UPDATE licenses SET is_active = 0 WHERE id = ?", (license_id,))
    return {"success": True}

@router.put("/admin/licenses/{license_id}/extend")
def extend_license(license_id: int, days: int = Form(...), authorization: str = None):
    if not verify_admin_token(authorization):
        raise HTTPException(status_code=401, detail="未登录")
    with get_db_context() as conn:
        c = conn.cursor()
        c.execute("SELECT expires_at FROM licenses WHERE id = ?", (license_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="卡密不存在")
        current = datetime.strptime(row["expires_at"], "%Y-%m-%d")
        new_expires = (current + timedelta(days=days)).strftime("%Y-%m-%d")
        c.execute("UPDATE licenses SET expires_at = ? WHERE id = ?", (new_expires, license_id))
    return {"success": True, "expires_at": new_expires}

@router.put("/admin/licenses/{license_id}/reactivate")
def reactivate_license(license_id: int, authorization: str = None):
    if not verify_admin_token(authorization):
        raise HTTPException(status_code=401, detail="未登录")
    with get_db_context() as conn:
        c = conn.cursor()
        c.execute("UPDATE licenses SET is_active = 1 WHERE id = ?", (license_id,))
    return {"success": True}

@router.get("/admin/stats")
def admin_stats(authorization: str = None):
    if not verify_admin_token(authorization):
        raise HTTPException(status_code=401, detail="未登录")
    with get_db_context() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as total FROM licenses")
        total = c.fetchone()["total"]
        c.execute("SELECT COUNT(*) as active FROM licenses WHERE is_active = 1")
        active = c.fetchone()["active"]
        c.execute("SELECT COUNT(*) as expired FROM licenses WHERE expires_at < date('now')")
        expired = c.fetchone()["expired"]
        return {"total": total, "active": active, "expired": expired}
