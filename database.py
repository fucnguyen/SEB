import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "seb_portal.db")

def get_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Bảng yêu cầu tải file cài đặt
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS download_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        email TEXT,
        note TEXT,
        ip_address TEXT,
        status TEXT DEFAULT 'pending', -- pending, approved, rejected
        download_token TEXT,
        token_expires_at TEXT,
        created_at TEXT NOT NULL,
        approved_at TEXT
    )
    """)

    # 2. Bảng quản lý bản quyền & kích hoạt mã máy (HWID)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS licenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT UNIQUE NOT NULL,
        hwid TEXT UNIQUE NOT NULL,
        student_name TEXT NOT NULL,
        email TEXT,
        machine_name TEXT,
        ip_address TEXT,
        status TEXT DEFAULT 'pending', -- pending, active, locked, expired
        duration_type TEXT,            -- 7d, 30d, 120d, 365d, lifetime
        license_key TEXT,
        activated_at TEXT,
        expires_at TEXT,
        last_heartbeat TEXT,
        created_at TEXT NOT NULL
    )
    """)

    # 3. Bảng tin nhắn chat giữa học sinh và admin
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        sender TEXT NOT NULL,          -- student, admin
        sender_name TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    # 4. Bảng cấu hình hệ thống
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """)

    # Các giá trị mặc định cho settings
    default_settings = {
        "admin_password": "Nguyenphuc1234@",
        "download_require_approval": "true",
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "telegram_notifications_enabled": "true",
        "external_download_url": "https://github.com/fucnguyen/SEB/releases/download/v2.0/Setup_ThiTrucTuyen_v2.exe",
        "r2_endpoint_url": "",
        "r2_access_key": "",
        "r2_secret_key": "",
        "r2_bucket_name": "",
        "r2_file_key": "Setup_ThiTrucTuyen_v2.exe",
        "setup_file_size": "205 MB",
        "version_tag": "v2.5.0"
    }

    for k, v in default_settings.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    # Cập nhật nếu trước đó là mật khẩu mặc định "admin"
    cursor.execute("UPDATE settings SET value = 'Nguyenphuc1234@' WHERE key = 'admin_password' AND value = 'admin'")

    conn.commit()
    conn.close()

# ────────────────── Download Requests API ──────────────────

def create_download_request(request_id: str, full_name: str, email: str, note: str, ip_address: str) -> Dict[str, Any]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO download_requests (request_id, full_name, email, note, ip_address, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?)
    """, (request_id, full_name, email, note, ip_address, now))
    conn.commit()
    conn.close()
    return get_download_request(request_id)

def get_download_request(request_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM download_requests WHERE request_id = ?", (request_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def approve_download_request(request_id: str, token: str, expires_at: str) -> bool:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE download_requests 
        SET status = 'approved', download_token = ?, token_expires_at = ?, approved_at = ?
        WHERE request_id = ?
    """, (token, expires_at, now, request_id))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def reject_download_request(request_id: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE download_requests SET status = 'rejected' WHERE request_id = ?", (request_id,))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def list_download_requests(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM download_requests ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_request_by_download_token(token: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM download_requests WHERE download_token = ? AND status = 'approved'", (token,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

# ────────────────── License & HWID API ──────────────────

def create_or_update_activation_request(
    request_id: str, hwid: str, student_name: str, email: str, machine_name: str, ip_address: str
) -> Dict[str, Any]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT * FROM licenses WHERE hwid = ?", (hwid,))
    existing = c.fetchone()

    if existing:
        # Nếu đã có nhưng đang pending hoặc active, cập nhật thông tin
        c.execute("""
            UPDATE licenses 
            SET student_name = ?, email = ?, machine_name = ?, ip_address = ?, last_heartbeat = ?
            WHERE hwid = ?
        """, (student_name, email, machine_name, ip_address, now, hwid))
    else:
        c.execute("""
            INSERT INTO licenses (request_id, hwid, student_name, email, machine_name, ip_address, status, created_at, last_heartbeat)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        """, (request_id, hwid, student_name, email, machine_name, ip_address, now, now))

    conn.commit()
    conn.close()
    return get_license_by_hwid(hwid)

def get_license_by_hwid(hwid: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM licenses WHERE hwid = ?", (hwid.strip(),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_license_by_request_id(request_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM licenses WHERE request_id = ?", (request_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def approve_license(hwid: str, license_key: str, expires_at: str, duration_type: str) -> bool:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE licenses
        SET status = 'active', license_key = ?, expires_at = ?, duration_type = ?, activated_at = ?
        WHERE hwid = ?
    """, (license_key, expires_at, duration_type, now, hwid.strip()))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def lock_license(hwid: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE licenses SET status = 'locked' WHERE hwid = ?", (hwid.strip(),))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def unlock_license(hwid: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE licenses SET status = 'active' WHERE hwid = ?", (hwid.strip(),))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def delete_license(hwid: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM licenses WHERE hwid = ?", (hwid.strip(),))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def update_heartbeat(hwid: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE licenses SET last_heartbeat = ? WHERE hwid = ?", (now, hwid.strip()))
    conn.commit()
    conn.close()

def list_licenses(limit: int = 100) -> List[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM licenses ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

# ────────────────── Live Chat API ──────────────────

def add_chat_message(session_id: str, sender: str, sender_name: str, message: str) -> Dict[str, Any]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO chat_messages (session_id, sender, sender_name, message, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (session_id, sender, sender_name, message, now))
    msg_id = c.lastrowid
    conn.commit()
    conn.close()
    return {
        "id": msg_id,
        "session_id": session_id,
        "sender": sender,
        "sender_name": sender_name,
        "message": message,
        "created_at": now
    }

def get_chat_messages(session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM chat_messages WHERE session_id = ? ORDER BY id ASC LIMIT ?", (session_id, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def list_active_chat_sessions() -> List[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT session_id, sender_name, MAX(created_at) as last_activity, COUNT(*) as message_count
        FROM chat_messages
        GROUP BY session_id
        ORDER BY last_activity DESC
        LIMIT 30
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

# ────────────────── Settings API ──────────────────

def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key: str, value: str) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_all_settings() -> Dict[str, str]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM settings")
    rows = {r["key"]: r["value"] for r in c.fetchall()}
    conn.close()
    return rows
