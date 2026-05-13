"""授权服务端 - 数据库模块"""
import sqlite3, hashlib, os
from pathlib import Path
from contextmanager import contextmanager

BASE_DIR = Path(__file__).resolve().parent.parent
# Railway 持久化路径（本地开发用项目目录）
DB_PATH = os.environ.get("LICENSE_DB_PATH", str(BASE_DIR / "license.db"))

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def get_db_context():
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db_context() as conn:
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=30000")

        c.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                customer_name TEXT,
                machine_code TEXT,
                expires_at TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                last_verify_at TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        admin_hash = hashlib.sha256('admin888'.encode()).hexdigest()
        c.execute("""
            INSERT OR IGNORE INTO admins (username, password_hash)
            VALUES ('admin', ?)
        """, (admin_hash,))
        c.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('server_secret', 'change-me-in-production')")

if __name__ == "__main__":
    init_db()
    print(f"授权数据库初始化完成！路径: {DB_PATH}")
