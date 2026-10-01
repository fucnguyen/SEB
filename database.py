import sqlite3
import os
import hashlib
import secrets
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

VIETNAM_TZ = timezone(timedelta(hours=7))

def now_vn() -> datetime:
    """Trả về thời gian hiện tại chuẩn múi giờ Việt Nam (GMT+7)"""
    return datetime.now(VIETNAM_TZ).replace(tzinfo=None)

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "seb_portal.db")

def get_connection():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
    except Exception:
        pass
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
        approved_at TEXT,
        system_type TEXT DEFAULT 'SEB'
    )
    """)

    try:
        cursor.execute("ALTER TABLE download_requests ADD COLUMN system_type TEXT DEFAULT 'SEB'")
        conn.commit()
    except Exception:
        pass

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

    try:
        cursor.execute("ALTER TABLE licenses ADD COLUMN phone TEXT DEFAULT ''")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE licenses ADD COLUMN notes TEXT DEFAULT ''")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE licenses ADD COLUMN system_type TEXT DEFAULT 'SEB'")
    except Exception:
        pass

    # 3. Bảng tin nhắn chat giữa học sinh và admin (kèm IP máy)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        sender TEXT NOT NULL,          -- student, admin
        sender_name TEXT NOT NULL,
        message TEXT NOT NULL,
        ip_address TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """)

    try:
        cursor.execute("ALTER TABLE chat_messages ADD COLUMN ip_address TEXT DEFAULT ''")
    except Exception:
        pass

    # 4. Bảng cấu hình hệ thống
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """)

    # 5. Bảng ghi nhận lịch sử Vào / Thoát bài thi của học sinh
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS access_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hwid TEXT NOT NULL,
        student_name TEXT NOT NULL,
        machine_name TEXT,
        ip_address TEXT,
        event_type TEXT NOT NULL, -- START_EXAM, EXIT_NORMAL, EXIT_LOCKED, EXIT_DELETED, EXIT_EXPIRED
        details TEXT,
        created_at TEXT NOT NULL
    )
    """)

    # 6. Bảng lưu phiên thi trực tuyến của thí sinh
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS live_exam_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hwid TEXT UNIQUE NOT NULL,
        student_name TEXT NOT NULL,
        exam_title TEXT,
        page_url TEXT DEFAULT '',
        total_questions INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active', -- active, finished
        last_sync TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    # 7. Bảng lưu danh sách câu hỏi, ảnh và đáp án của từng câu
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS live_exam_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hwid TEXT NOT NULL,
        question_index INTEGER NOT NULL,
        question_text TEXT NOT NULL,
        question_type TEXT DEFAULT 'unknown', -- radio, checkbox, text, essay, unknown
        images_json TEXT DEFAULT '[]',
        options_json TEXT NOT NULL DEFAULT '[]',
        current_answer TEXT DEFAULT '',       -- Câu trả lời hiện tại của thí sinh
        support_answer TEXT DEFAULT '',       -- Đáp án do Support chọn
        updated_at TEXT NOT NULL,
        UNIQUE(hwid, question_index)
    )
    """)

    # Migration: thêm cột mới nếu DB cũ chưa có
    for _col, _def in [
        ("question_type",  "TEXT DEFAULT 'unknown'"),
        ("current_answer", "TEXT DEFAULT ''"),
        ("support_answer", "TEXT DEFAULT ''"),
        ("images_json",    "TEXT DEFAULT '[]'"),
        ("options_json",   "TEXT DEFAULT '[]'"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE live_exam_questions ADD COLUMN {_col} {_def}")
        except Exception:
            pass  # Column already exists

    # Migration: thêm các cột metadata vào live_exam_sessions nếu DB cũ chưa có
    for _col, _def in [
        ("page_url", "TEXT DEFAULT ''"),
        ("remaining_time", "TEXT DEFAULT ''"),
        ("exam_server_time", "TEXT DEFAULT ''"),
        ("subject_code", "TEXT DEFAULT ''"),
        ("class_code", "TEXT DEFAULT ''"),
        ("campus", "TEXT DEFAULT ''"),
        ("auto_fill_requested", "INTEGER DEFAULT 0"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE live_exam_sessions ADD COLUMN {_col} {_def}")
        except Exception:
            pass

    # 8. Bảng quản lý mã Key Support dành cho CTV / Người hỗ trợ
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS support_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key_code TEXT UNIQUE NOT NULL,
        assigned_name TEXT NOT NULL,
        email TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        note TEXT DEFAULT '',
        status TEXT DEFAULT 'active', -- active, suspended, locked
        created_at TEXT NOT NULL,
        expires_at TEXT DEFAULT '',
        last_login TEXT DEFAULT ''
    )
    """)

    # 9. Bảng phân ca thi / gắn máy (HWID) theo ngày cho từng Support Key
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS support_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        support_key TEXT NOT NULL,
        hwid TEXT NOT NULL,
        student_name TEXT DEFAULT '',
        exam_date TEXT NOT NULL,      -- YYYY-MM-DD
        exam_shift TEXT DEFAULT '',   -- Ca thi
        subject TEXT DEFAULT '',      -- Môn thi
        notes TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        status TEXT DEFAULT 'active', -- active, completed, cancelled
        UNIQUE(support_key, hwid, exam_date)
    )
    """)
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sup_assign_date ON support_assignments(support_key, exam_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sup_assign_hwid ON support_assignments(hwid, exam_date)")
    except Exception:
        pass

    # Các giá trị mặc định cho settings
    default_settings = {
        "admin_password": "Nguyenphuc1234@",
        "download_require_approval": "true",
        "telegram_bot_token": "8902883418:AAF1rAAcEVx4gyI9gcJW5GrBjqB-PphSuf8",
        "telegram_chat_id": "6396371761",
        "telegram_notifications_enabled": "true",
        "external_download_url": "https://github.com/fucnguyen/SEB/releases/download/v2.0/Setup_ThiTrucTuyen_v2.exe",
        "external_download_url_seb": "https://github.com/fucnguyen/SEB/releases/download/v2.0/Setup_ThiTrucTuyen_v2.exe",
        "external_download_url_mac": "https://github.com/fucnguyen/SEB/releases/download/v2.0/Setup_ThiTrucTuyen_macOS.zip",
        "external_download_url_eos": "https://github.com/fucnguyen/SEB/releases/download/v2.0/Setup_ThiTrucTuyen_EOS_v2.exe",
        "github_token": "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",
        "github_repo": "fucnguyen/SEB",
        "github_release_tag": "v2.0",
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

    # Cập nhật nếu trước đó là mật khẩu mặc định "admin" hoặc các giá trị quan trọng bị trống
    cursor.execute("UPDATE settings SET value = 'Nguyenphuc1234@' WHERE key = 'admin_password' AND value = 'admin'")
    cursor.execute("UPDATE settings SET value = '8902883418:AAF1rAAcEVx4gyI9gcJW5GrBjqB-PphSuf8' WHERE key = 'telegram_bot_token' AND (value = '' OR value IS NULL)")
    cursor.execute("UPDATE settings SET value = '6396371761' WHERE key = 'telegram_chat_id' AND (value = '' OR value IS NULL)")
    cursor.execute("UPDATE settings SET value = 'https://github.com/fucnguyen/SEB/releases/download/v2.0/Setup_ThiTrucTuyen_macOS.zip' WHERE key = 'external_download_url_mac' AND (value = '' OR value IS NULL)")
    cursor.execute("UPDATE settings SET value = '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' WHERE key = 'github_token' AND (value = '' OR value IS NULL)")
    cursor.execute("UPDATE settings SET value = 'fucnguyen/SEB' WHERE key = 'github_repo' AND (value = '' OR value IS NULL)")
    cursor.execute("UPDATE settings SET value = 'v2.0' WHERE key = 'github_release_tag' AND (value = '' OR value IS NULL)")

    # 6. Tự động nạp danh sách mã máy lịch sử và bản quyền từ seed_data.json
    seed_initial_data(cursor)

    conn.commit()
    conn.close()

# ────────────────── Download Requests API ──────────────────

def create_download_request(request_id: str, full_name: str, email: str, note: str, ip_address: str, system_type: str = "SEB") -> Dict[str, Any]:
    now = now_vn().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO download_requests (request_id, full_name, email, note, ip_address, status, created_at, system_type)
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
    """, (request_id, full_name, email, note, ip_address, now, system_type))
    conn.commit()
    conn.close()
    try:
        sync_seed_file()
    except Exception:
        pass
    return get_download_request(request_id)

def get_download_request(request_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM download_requests WHERE request_id = ?", (request_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def approve_download_request(request_id: str, token: str, expires_at: str) -> bool:
    now = now_vn().strftime("%Y-%m-%d %H:%M:%S")
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
    if affected:
        try:
            sync_seed_file()
        except Exception:
            pass
    return affected

def reject_download_request(request_id: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE download_requests SET status = 'rejected' WHERE request_id = ?", (request_id,))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    if affected:
        try:
            sync_seed_file()
        except Exception:
            pass
    return affected

def list_download_requests(limit: int = 50, system_type: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    if system_type:
        st = system_type.upper().strip()
        if st == 'SEB':
            # Hệ thống SEB bao gồm cả bản Windows, macOS, SEB và dữ liệu cũ (NULL)
            c.execute("""
                SELECT * FROM download_requests 
                WHERE (UPPER(system_type) IN ('SEB', 'WINDOWS', 'MACOS', 'MAC', 'WIN', 'SEB_MAC') 
                       OR system_type IS NULL) 
                ORDER BY id DESC LIMIT ?
            """, (limit,))
        elif st in ('EOS', 'PEA'):
            c.execute("SELECT * FROM download_requests WHERE UPPER(system_type) IN ('EOS', 'PEA') ORDER BY id DESC LIMIT ?", (limit,))
        else:
            c.execute("SELECT * FROM download_requests WHERE (UPPER(system_type) = ? OR system_type IS NULL) ORDER BY id DESC LIMIT ?", (st, limit))
    else:
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
    request_id: str, hwid: str, student_name: str, email: str, machine_name: str, ip_address: str, system_type: str = "SEB"
) -> Dict[str, Any]:
    now = now_vn().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT * FROM licenses WHERE hwid = ?", (hwid,))
    existing = c.fetchone()

    if existing:
        c.execute("""
            UPDATE licenses 
            SET student_name = ?, email = ?, machine_name = ?, ip_address = ?, last_heartbeat = ?, system_type = ?
            WHERE hwid = ?
        """, (student_name, email, machine_name, ip_address, now, system_type, hwid))
    else:
        c.execute("""
            INSERT INTO licenses (request_id, hwid, student_name, email, machine_name, ip_address, status, created_at, last_heartbeat, system_type)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
        """, (request_id, hwid, student_name, email, machine_name, ip_address, now, now, system_type))

    conn.commit()
    conn.close()
    try:
        sync_seed_file()
    except Exception:
        pass
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
    now = now_vn().strftime("%Y-%m-%d %H:%M:%S")
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
    if affected:
        sync_seed_file()
    return affected

def lock_license(hwid: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE licenses SET status = 'locked' WHERE hwid = ?", (hwid.strip(),))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    if affected:
        sync_seed_file()
    return affected

def unlock_license(hwid: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE licenses SET status = 'active' WHERE hwid = ?", (hwid.strip(),))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    if affected:
        sync_seed_file()
    return affected

def delete_license(hwid: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM licenses WHERE hwid = ?", (hwid.strip(),))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    if affected:
        sync_seed_file()
    return affected

def update_license_info(hwid: str, student_name: str, email: str = "", phone: str = "", notes: str = "") -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE licenses 
        SET student_name = ?, email = ?, phone = ?, notes = ?
        WHERE hwid = ?
    """, (student_name.strip(), email.strip(), phone.strip(), notes.strip(), hwid.strip()))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    if affected:
        sync_seed_file()
    return affected

def update_heartbeat(hwid: str) -> None:
    now = now_vn().strftime("%Y-%m-%d %H:%M:%S")
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

def add_chat_message(session_id: str, sender: str, sender_name: str, message: str, ip_address: str = "") -> Dict[str, Any]:
    now = now_vn().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO chat_messages (session_id, sender, sender_name, message, ip_address, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (session_id, sender, sender_name, message, ip_address, now))
    msg_id = c.lastrowid
    conn.commit()
    conn.close()
    return {
        "id": msg_id,
        "session_id": session_id,
        "sender": sender,
        "sender_name": sender_name,
        "message": message,
        "ip_address": ip_address,
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
        SELECT session_id, 
               MAX(CASE WHEN sender = 'student' THEN sender_name ELSE '' END) as student_sender_name,
               MAX(sender_name) as fallback_name,
               MAX(created_at) as last_activity, 
               COUNT(*) as message_count,
               MAX(CASE WHEN sender = 'student' THEN ip_address ELSE '' END) as ip_address
        FROM chat_messages
        GROUP BY session_id
        ORDER BY last_activity DESC
        LIMIT 50
    """)
    rows = [dict(r) for r in c.fetchall()]
    for r in rows:
        r["sender_name"] = r.get("student_sender_name") or r.get("fallback_name") or "Học sinh"
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

# ────────────────── Access Logs API (Vào / Thoát Ca Thi) ──────────────────

def log_access_event(
    hwid: str,
    student_name: str,
    machine_name: str,
    ip_address: str,
    event_type: str,
    details: str = ""
) -> Dict[str, Any]:
    now = now_vn().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO access_logs (hwid, student_name, machine_name, ip_address, event_type, details, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (hwid.strip(), student_name.strip(), machine_name.strip(), ip_address.strip(), event_type.strip(), details.strip(), now))
    log_id = c.lastrowid
    conn.commit()
    conn.close()
    return {
        "id": log_id,
        "hwid": hwid,
        "student_name": student_name,
        "machine_name": machine_name,
        "ip_address": ip_address,
        "event_type": event_type,
        "details": details,
        "created_at": now
    }

def list_access_logs(limit: int = 300, hwid: Optional[str] = None, target_date: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    params = []
    query = "SELECT * FROM access_logs WHERE 1=1"
    if hwid and hwid.strip():
        query += " AND hwid = ?"
        params.append(hwid.strip())
    if target_date and target_date.strip() and target_date.strip().lower() != "all":
        d = target_date.strip()
        query += " AND (created_at LIKE ? OR DATE(created_at) = ?)"
        params.extend([f"{d}%", d])
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    c.execute(query, tuple(params))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def list_access_log_dates() -> List[Dict[str, Any]]:
    """Lấy danh sách các ngày có nhật ký kèm số sự kiện để hiển thị thanh lọc theo ngày"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT SUBSTR(created_at, 1, 10) as log_date, COUNT(*) as count 
        FROM access_logs 
        WHERE created_at IS NOT NULL AND created_at != ''
        GROUP BY SUBSTR(created_at, 1, 10) 
        ORDER BY log_date DESC 
        LIMIT 60
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def clear_access_logs() -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM access_logs")
    conn.commit()
    conn.close()
    return True

# ────────────────── Auto-Seed & Data Backup / Restore ──────────────────

SEED_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_data.json")

def seed_initial_data(cursor):
    """
    Tự động nạp danh sách mã máy lịch sử và bản quyền từ seed_data.json vào DB.
    Đảm bảo sau mỗi lần redeploy hoặc restart trên Render, toàn bộ key cũ không bao giờ bị mất!
    """
    seed_paths = [
        SEED_FILE_PATH,
        os.path.join(DB_DIR, "seed_data.json")
    ]
    seed_file = None
    for p in seed_paths:
        if os.path.exists(p):
            seed_file = p
            break

    if not seed_file:
        return

    try:
        import json
        with open(seed_file, "r", encoding="utf-8") as f:
            seed = json.load(f)

        # 1. Nạp licenses
        for lic in seed.get("licenses", []):
            hwid = lic.get("hwid", "").strip()
            if not hwid:
                continue
            cursor.execute("SELECT id, status, license_key FROM licenses WHERE hwid = ?", (hwid,))
            row = cursor.fetchone()
            if not row:
                cursor.execute("""
                    INSERT INTO licenses (
                        request_id, hwid, student_name, email, phone, machine_name, ip_address,
                        status, duration_type, license_key, activated_at, expires_at,
                        last_heartbeat, created_at, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    lic.get("request_id") or f"REQ_{hwid[:8]}",
                    hwid,
                    lic.get("student_name", "Học sinh"),
                    lic.get("email", ""),
                    lic.get("phone", ""),
                    lic.get("machine_name", ""),
                    lic.get("ip_address", ""),
                    lic.get("status", "active"),
                    lic.get("duration_type", "365d"),
                    lic.get("license_key", ""),
                    lic.get("activated_at", lic.get("created_at")),
                    lic.get("expires_at", ""),
                    lic.get("last_heartbeat", lic.get("activated_at")),
                    lic.get("created_at") or now_vn().strftime("%Y-%m-%d %H:%M:%S"),
                    lic.get("notes", "")
                ))
            else:
                # Nếu đã có nhưng chưa có key hoặc đang pending mà seed có key active thì phục hồi
                if (not row["license_key"] or row["status"] == "pending") and lic.get("license_key"):
                    cursor.execute("""
                        UPDATE licenses SET 
                            license_key = ?, status = ?, expires_at = ?, duration_type = ?,
                            student_name = COALESCE(NULLIF(?, ''), student_name),
                            email = COALESCE(NULLIF(?, ''), email),
                            phone = COALESCE(NULLIF(?, ''), phone),
                            machine_name = COALESCE(NULLIF(?, ''), machine_name),
                            notes = COALESCE(NULLIF(?, ''), notes)
                        WHERE hwid = ?
                    """, (
                        lic.get("license_key"), lic.get("status", "active"), lic.get("expires_at"),
                        lic.get("duration_type", "365d"), lic.get("student_name", ""),
                        lic.get("email", ""), lic.get("phone", ""), lic.get("machine_name", ""),
                        lic.get("notes", ""), hwid
                    ))

        # 2. Nạp download requests
        for dl in seed.get("download_requests", []):
            req_id = dl.get("request_id")
            if not req_id:
                continue
            cursor.execute("SELECT id FROM download_requests WHERE request_id = ?", (req_id,))
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO download_requests (
                        request_id, full_name, email, note, ip_address, status,
                        download_token, token_expires_at, created_at, approved_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    req_id,
                    dl.get("full_name", ""),
                    dl.get("email", ""),
                    dl.get("note", ""),
                    dl.get("ip_address", ""),
                    dl.get("status", "approved"),
                    dl.get("download_token", ""),
                    dl.get("token_expires_at", ""),
                    dl.get("created_at") or now_vn().strftime("%Y-%m-%d %H:%M:%S"),
                    dl.get("approved_at", dl.get("created_at"))
                ))
        # 3. Nạp support keys
        for sk in seed.get("support_keys", []):
            kcode = sk.get("key_code", "").strip()
            if not kcode:
                continue
            cursor.execute("SELECT id FROM support_keys WHERE key_code = ?", (kcode,))
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO support_keys (key_code, assigned_name, email, phone, note, status, created_at, expires_at, last_login)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    kcode, sk.get("assigned_name", "CTV Support"), sk.get("email", ""),
                    sk.get("phone", ""), sk.get("note", ""), sk.get("status", "active"),
                    sk.get("created_at") or now_vn().strftime("%Y-%m-%d %H:%M:%S"),
                    sk.get("expires_at", ""), sk.get("last_login", "")
                ))

        # 4. Nạp support assignments
        for sa in seed.get("support_assignments", []):
            skey = sa.get("support_key", "").strip()
            hwid = sa.get("hwid", "").strip()
            edate = sa.get("exam_date", "").strip()
            if not skey or not hwid or not edate:
                continue
            cursor.execute("SELECT id FROM support_assignments WHERE support_key = ? AND hwid = ? AND exam_date = ?", (skey, hwid, edate))
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO support_assignments (support_key, hwid, student_name, exam_date, exam_shift, subject, notes, created_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    skey, hwid, sa.get("student_name", ""), edate,
                    sa.get("exam_shift", ""), sa.get("subject", ""), sa.get("notes", ""),
                    sa.get("created_at") or now_vn().strftime("%Y-%m-%d %H:%M:%S"),
                    sa.get("status", "active")
                ))

        # 5. Nạp live_exam_sessions (Đảm bảo không bao giờ mất ca thi cũ như Đỗ Văn Đông khi redeploy Render)
        for ses in seed.get("live_exam_sessions", []):
            shwid = ses.get("hwid", "").strip()
            if not shwid:
                continue
            cursor.execute("SELECT id FROM live_exam_sessions WHERE hwid = ?", (shwid,))
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO live_exam_sessions (
                        hwid, student_name, exam_title, page_url, total_questions, status, last_sync, created_at,
                        remaining_time, exam_server_time, subject_code, class_code, campus
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    shwid, ses.get("student_name", "Thí sinh"), ses.get("exam_title", ""),
                    ses.get("page_url", ""), ses.get("total_questions", 0), ses.get("status", "active"),
                    ses.get("last_sync") or now_vn().strftime("%Y-%m-%d %H:%M:%S"),
                    ses.get("created_at") or now_vn().strftime("%Y-%m-%d %H:%M:%S"),
                    ses.get("remaining_time", ""), ses.get("exam_server_time", ""),
                    ses.get("subject_code", ""), ses.get("class_code", ""), ses.get("campus", "")
                ))

        # 6. Nạp live_exam_questions
        for q in seed.get("live_exam_questions", []):
            qhwid = q.get("hwid", "").strip()
            qidx = q.get("question_index")
            if not qhwid or qidx is None:
                continue
            cursor.execute("SELECT id FROM live_exam_questions WHERE hwid = ? AND question_index = ?", (qhwid, qidx))
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO live_exam_questions (
                        hwid, question_index, question_text, question_type, images_json, options_json,
                        current_answer, support_answer, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    qhwid, qidx, q.get("question_text", ""), q.get("question_type", "unknown"),
                    q.get("images_json", "[]"), q.get("options_json", "[]"),
                    q.get("current_answer", ""), q.get("support_answer", ""),
                    q.get("updated_at") or now_vn().strftime("%Y-%m-%d %H:%M:%S")
                ))

        # 7. Nạp archived_exam_sources (Kho source đề ZIP)
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS archived_exam_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hwid TEXT,
                    student_name TEXT,
                    exam_title TEXT,
                    archive_filename TEXT UNIQUE,
                    file_size_bytes INTEGER,
                    total_questions INTEGER,
                    created_at TEXT
                )
            """)
            for arc in seed.get("archived_exam_sources", []):
                afname = arc.get("archive_filename", "").strip()
                if not afname:
                    continue
                cursor.execute("SELECT id FROM archived_exam_sources WHERE archive_filename = ?", (afname,))
                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO archived_exam_sources (
                            hwid, student_name, exam_title, archive_filename, file_size_bytes, total_questions, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        arc.get("hwid", ""), arc.get("student_name", ""), arc.get("exam_title", ""),
                        afname, arc.get("file_size_bytes", 0), arc.get("total_questions", 0),
                        arc.get("created_at") or now_vn().strftime("%Y-%m-%d %H:%M:%S")
                    ))
        except Exception:
            pass

        try:
            print(f"[Seed] Successfully seeded {len(seed.get('licenses', []))} licenses, {len(seed.get('live_exam_sessions', []))} exam sessions, and {len(seed.get('live_exam_questions', []))} questions.")
        except Exception:
            pass
    except Exception as e:
        try:
            print(f"[Warning] Failed to load seed_data.json: {e}")
        except Exception:
            pass

def sync_seed_file():
    """Tự động đồng bộ các license, yêu cầu tải và support keys mới nhất ra seed_data.json để lưu trữ lâu dài"""
    try:
        data = export_all_data()
        payload = {
            "licenses": data.get("licenses", []),
            "download_requests": data.get("download_requests", []),
            "support_keys": data.get("support_keys", []),
            "support_assignments": data.get("support_assignments", []),
            "live_exam_sessions": data.get("live_exam_sessions", []),
            "live_exam_questions": data.get("live_exam_questions", []),
            "archived_exam_sources": data.get("archived_exam_sources", []),
            "access_logs": data.get("access_logs", [])
        }
        import json
        with open(SEED_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def export_all_data() -> Dict[str, Any]:
    """Xuất toàn bộ cơ sở dữ liệu thành đối tượng Dict JSON để tải về máy tính hoặc sao lưu Cloud"""
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT * FROM licenses ORDER BY id ASC")
    licenses = [dict(r) for r in c.fetchall()]
    
    c.execute("SELECT * FROM download_requests ORDER BY id ASC")
    download_requests = [dict(r) for r in c.fetchall()]

    c.execute("SELECT * FROM support_keys ORDER BY id ASC")
    support_keys = [dict(r) for r in c.fetchall()]

    c.execute("SELECT * FROM support_assignments ORDER BY id ASC")
    support_assignments = [dict(r) for r in c.fetchall()]
    
    c.execute("SELECT * FROM chat_messages ORDER BY id ASC")
    chat_messages = [dict(r) for r in c.fetchall()]
    
    c.execute("SELECT * FROM live_exam_sessions ORDER BY id ASC")
    live_exam_sessions = [dict(r) for r in c.fetchall()]

    c.execute("SELECT * FROM live_exam_questions ORDER BY id ASC")
    live_exam_questions = [dict(r) for r in c.fetchall()]

    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS archived_exam_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hwid TEXT,
                student_name TEXT,
                exam_title TEXT,
                archive_filename TEXT UNIQUE,
                file_size_bytes INTEGER,
                total_questions INTEGER,
                created_at TEXT
            )
        """)
        c.execute("SELECT * FROM archived_exam_sources ORDER BY id ASC")
        archived_exam_sources = [dict(r) for r in c.fetchall()]
    except Exception:
        archived_exam_sources = []

    c.execute("SELECT * FROM access_logs ORDER BY id DESC LIMIT 1000")
    access_logs = [dict(r) for r in c.fetchall()]
    
    c.execute("SELECT key, value FROM settings")
    settings = {r["key"]: r["value"] for r in c.fetchall()}
    
    conn.close()
    return {
        "exported_at": now_vn().strftime("%Y-%m-%d %H:%M:%S"),
        "licenses": licenses,
        "download_requests": download_requests,
        "support_keys": support_keys,
        "support_assignments": support_assignments,
        "live_exam_sessions": live_exam_sessions,
        "live_exam_questions": live_exam_questions,
        "archived_exam_sources": archived_exam_sources,
        "chat_messages": chat_messages,
        "access_logs": access_logs,
        "settings": settings
    }

def import_all_data(data: Dict[str, Any], overwrite: bool = False) -> Dict[str, int]:
    """Nạp dữ liệu từ file backup JSON vào cơ sở dữ liệu"""
    conn = get_connection()
    c = conn.cursor()
    stats = {"licenses": 0, "download_requests": 0, "support_keys": 0, "support_assignments": 0, "chat_messages": 0, "access_logs": 0}
    
    for lic in data.get("licenses", []):
        hwid = lic.get("hwid", "").strip()
        if not hwid:
            continue
        c.execute("SELECT id FROM licenses WHERE hwid = ?", (hwid,))
        exists = c.fetchone()
        if exists and overwrite:
            c.execute("""
                UPDATE licenses SET
                    student_name = ?, email = ?, phone = ?, machine_name = ?, ip_address = ?,
                    status = ?, duration_type = ?, license_key = ?, activated_at = ?,
                    expires_at = ?, last_heartbeat = ?, notes = ?
                WHERE hwid = ?
            """, (
                lic.get("student_name", ""), lic.get("email", ""), lic.get("phone", ""),
                lic.get("machine_name", ""), lic.get("ip_address", ""), lic.get("status", "active"),
                lic.get("duration_type", "365d"), lic.get("license_key", ""), lic.get("activated_at"),
                lic.get("expires_at"), lic.get("last_heartbeat"), lic.get("notes", ""), hwid
            ))
            stats["licenses"] += 1
        elif not exists:
            c.execute("""
                INSERT INTO licenses (
                    request_id, hwid, student_name, email, phone, machine_name, ip_address,
                    status, duration_type, license_key, activated_at, expires_at,
                    last_heartbeat, created_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                lic.get("request_id") or f"REQ_{hwid[:8]}", hwid, lic.get("student_name", ""),
                lic.get("email", ""), lic.get("phone", ""), lic.get("machine_name", ""),
                lic.get("ip_address", ""), lic.get("status", "active"), lic.get("duration_type", "365d"),
                lic.get("license_key", ""), lic.get("activated_at"), lic.get("expires_at"),
                lic.get("last_heartbeat"), lic.get("created_at") or now_vn().strftime("%Y-%m-%d %H:%M:%S"),
                lic.get("notes", "")
            ))
            stats["licenses"] += 1
            
    for dl in data.get("download_requests", []):
        req_id = dl.get("request_id")
        if not req_id:
            continue
        c.execute("SELECT id FROM download_requests WHERE request_id = ?", (req_id,))
        exists = c.fetchone()
        if not exists:
            c.execute("""
                INSERT INTO download_requests (
                    request_id, full_name, email, note, ip_address, status,
                    download_token, token_expires_at, created_at, approved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                req_id, dl.get("full_name", ""), dl.get("email", ""), dl.get("note", ""),
                dl.get("ip_address", ""), dl.get("status", "approved"), dl.get("download_token", ""),
                dl.get("token_expires_at", ""), dl.get("created_at") or now_vn().strftime("%Y-%m-%d %H:%M:%S"),
                dl.get("approved_at")
            ))
            stats["download_requests"] += 1

    for sk in data.get("support_keys", []):
        kcode = sk.get("key_code", "").strip()
        if not kcode:
            continue
        c.execute("SELECT id FROM support_keys WHERE key_code = ?", (kcode,))
        if not c.fetchone():
            c.execute("""
                INSERT INTO support_keys (key_code, assigned_name, email, phone, note, status, created_at, expires_at, last_login)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                kcode, sk.get("assigned_name", "CTV Support"), sk.get("email", ""),
                sk.get("phone", ""), sk.get("note", ""), sk.get("status", "active"),
                sk.get("created_at") or now_vn().strftime("%Y-%m-%d %H:%M:%S"),
                sk.get("expires_at", ""), sk.get("last_login", "")
            ))
            stats["support_keys"] += 1

    for sa in data.get("support_assignments", []):
        skey = sa.get("support_key", "").strip()
        hwid = sa.get("hwid", "").strip()
        edate = sa.get("exam_date", "").strip()
        if not skey or not hwid or not edate:
            continue
        c.execute("SELECT id FROM support_assignments WHERE support_key = ? AND hwid = ? AND exam_date = ?", (skey, hwid, edate))
        if not c.fetchone():
            c.execute("""
                INSERT INTO support_assignments (support_key, hwid, student_name, exam_date, exam_shift, subject, notes, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                skey, hwid, sa.get("student_name", ""), edate,
                sa.get("exam_shift", ""), sa.get("subject", ""), sa.get("notes", ""),
                sa.get("created_at") or now_vn().strftime("%Y-%m-%d %H:%M:%S"),
                sa.get("status", "active")
            ))
            stats["support_assignments"] += 1
            
    conn.commit()
    conn.close()
    try:
        sync_seed_file()
    except Exception:
        pass
    return stats

def send_backup_to_telegram() -> Dict[str, Any]:
    """Tự động đóng gói toàn bộ database thành file JSON và gửi trực tiếp qua Telegram Bot về máy admin."""
    import requests
    bot_token = get_setting("telegram_bot_token") or "8902883418:AAF1rAAcEVx4gyI9gcJW5GrBjqB-PphSuf8"
    chat_id = get_setting("telegram_chat_id") or "6396371761"
    if not bot_token or not chat_id:
        return {"success": False, "error": "Chưa cấu hình Telegram Bot Token hoặc Chat ID"}
    
    data = export_all_data()
    now_str = now_vn().strftime("%Y-%m-%d_%H%M%S")
    filename = f"seb_portal_cloud_backup_{now_str}.json"
    
    caption = (
        f"📦 <b>[SAO LƯU DỮ LIỆU SEB CLOUD]</b>\n\n"
        f"📅 <b>Thời gian:</b> {now_vn().strftime('%Y-%m-%d %H:%M:%S')} (GMT+7)\n"
        f"🔑 <b>Bản quyền & Mã máy:</b> {len(data.get('licenses', []))} máy\n"
        f"📥 <b>Yêu cầu tải:</b> {len(data.get('download_requests', []))} yêu cầu\n"
        f"👨‍🏫 <b>Key Support CTV:</b> {len(data.get('support_keys', []))} keys\n"
        f"📝 <b>Phân ca thi:</b> {len(data.get('support_assignments', []))} ca\n"
        f"🛡️ <i>Tệp đính kèm chứa trọn vẹn CSDL, có thể tải về hoặc nạp khôi phục (Restore) bất cứ lúc nào!</i>"
    )
    
    try:
        content_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        files = {
            "document": (filename, content_bytes, "application/json")
        }
        res = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendDocument",
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files=files,
            timeout=15
        )
        if res.status_code == 200:
            return {"success": True, "filename": filename, "message": "Đã gửi bản sao lưu thành công qua Telegram!"}
        else:
            return {"success": False, "error": f"Telegram API lỗi HTTP {res.status_code}: {res.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ────────────────── Live Exam Sync & Support API ──────────────────

def clean_exam_stem_text(t: str) -> str:
    """Loại bỏ sạch các đoạn mã CSS, bình luận Word/Math, và biểu ngữ thời gian thi / hướng dẫn giám thị."""
    if not t:
        return ""
    import re
    # Strip HTML tags like <style>...</style>
    t = re.sub(r'<style[\s\S]*?</style>', ' ', t, flags=re.IGNORECASE)
    # Strip HTML / XML comments
    t = re.sub(r'<!--[\s\S]*?-->', ' ', t)
    # Strip CSS comments
    t = re.sub(r'/\*[\s\S]*?\*/', ' ', t)
    # Strip exam instructions & countdown timer banners
    t = re.sub(r'(?:Thời gian còn lại|Thời gian làm bài|Time remaining|Time left)[\s\S]*?(?:quá trình thi|suốt quá trình thi|hết giờ|làm bài thi)[,\.\s\!:;]*', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'(?:Thí sinh chú ý|Tiến trình thi|Tiên tính|Lưu ý khi làm bài|Liên hệ cán bộ|Kiểm tra làm thật kỹ|Không được thay đổi tỉ lệ zoom)[\s\S]*?(?:quá trình thi|suốt quá trình thi|hết giờ|làm bài thi)[,\.\s\!:;]*', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'(?:Thời gian còn lại|Thời gian làm bài|Time remaining|Time left)\s*:\s*[\d\w\s:]+', ' ', t, flags=re.IGNORECASE)
    # Strip @font-face and @keyframes blocks (only specific CSS at-rules)
    t = re.sub(r'@(?:font-face|keyframes|import|media)[^{]*\{[\s\S]*?\}', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'(?:p|li|div)\.MsoNormal[\s\S]*?(?:;|\})', ' ', t, flags=re.IGNORECASE)
    # NOTE: Do NOT use generic { ... } stripper, as it wipes out math piecewise functions and LaTeX!
    t = re.sub(r'(?:font-family|font-size|margin|padding|line-height|text-align):[^;}]+;?', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'mso-[^;}]+;?', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'panose-1:[^;}]+;?', ' ', t, flags=re.IGNORECASE)
    # Strip question number header
    t = re.sub(r'^(?:CÂU\s*HỎI|CÂU|QUESTION)\s*\d+[\s\:\.\-]*(?:\([^)]*\))?', ' ', t, flags=re.IGNORECASE)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()

def check_is_new_exam(
    existing: Optional[sqlite3.Row],
    new_title: str,
    new_page_url: str,
    new_questions: List[Dict[str, Any]],
    c: sqlite3.Cursor,
    hwid: str,
    new_subject_code: str = ""
) -> bool:
    """
    Xác định chính xác liệu thí sinh có đang chuyển sang một ĐỀ THI MỚI / LƯỢT THI MỚI hay không.
    Điều kiện nhận diện:
    1. Trạng thái ca thi cũ trong DB đã 'finished', 'archived' hoặc 'reset_requested'.
    2. Tên bài thi (exam_title) hoặc Mã môn thi (subject_code) thay đổi.
    3. Tham số attempt/quiz/cmid/testcode trong URL thay đổi hoặc URL cơ sở khác nhau.
    4. Nội dung câu hỏi (5 câu đầu) khác biệt > 30% so với câu hỏi cũ cùng index.
    """
    if not existing:
        return False

    status = (existing["status"] or "").strip().lower()
    if status in ("finished", "archived", "reset_requested"):
        return True

    # 1. So sánh tên bài thi chuẩn hóa (bỏ qua các tên generic)
    old_title = (existing["exam_title"] or "").strip().lower()
    norm_new = (new_title or "").strip().lower()
    generic_titles = {
        "", "bài thi trực tuyến", "bai thi truc tuyen", "kiểm tra", "kiem tra",
        "exam", "test", "thi", "online exam", "fpt exam", "moodle", "quiz", "unknown"
    }
    if norm_new and old_title and norm_new != old_title:
        if norm_new not in generic_titles and old_title not in generic_titles:
            return True

    # 1.1 So sánh mã môn thi (subject_code) nếu có
    old_sub = (existing["subject_code"] or "").strip().lower()
    new_sub = (new_subject_code or "").strip().lower()
    if old_sub and new_sub and old_sub != new_sub:
        return True

    # 2. Kiểm tra URL thay đổi
    old_url = (existing["page_url"] or "").strip().lower()
    new_url = (new_page_url or "").strip().lower()
    if old_url and new_url and old_url != new_url:
        import re
        pat = r'(?:attempt|quiz|cmid|examid|paperid|testcode|test_id|exam_id|code|test|exam)[=\/](\d+|[a-zA-Z0-9_\-]+)'
        m_old = re.findall(pat, old_url)
        m_new = re.findall(pat, new_url)
        if m_old and m_new and set(m_old) != set(m_new):
            return True

        old_base = old_url.split("?")[0].rstrip("/")
        new_base = new_url.split("?")[0].rstrip("/")
        if old_base and new_base and old_base != new_base and not new_base.endswith("/exam/index"):
            return True

    # 3. Kiểm tra nội dung câu hỏi: nếu có câu nào có text khác biệt > 30% so với câu cũ
    if new_questions:
        try:
            c.execute("SELECT question_index, question_text FROM live_exam_questions WHERE hwid = ?", (hwid,))
            old_qs = {int(r["question_index"]): (r["question_text"] or "").strip().lower() for r in c.fetchall()}
            if old_qs:
                for q in new_questions[:6]:
                    idx = int(q.get("question_index") if q.get("question_index") is not None else q.get("index", 0))
                    q_text_new = (q.get("question_text") or "").strip().lower()
                    if len(q_text_new) < 12:
                        continue
                    if idx in old_qs:
                        q_text_old = old_qs[idx]
                        if len(q_text_old) >= 12:
                            import difflib
                            ratio = difflib.SequenceMatcher(None, q_text_new[:90], q_text_old[:90]).ratio()
                            if ratio < 0.65:
                                return True
        except Exception:
            pass

    return False


def sync_student_exam_data(
    hwid: str,
    student_name: str,
    exam_title: str,
    questions: list,
    page_url: str = "",
    return_details: bool = False,
    remaining_time: str = "",
    exam_server_time: str = "",
    subject_code: str = "",
    class_code: str = "",
    campus: str = ""
) -> Any:
    """
    Nhận toàn bộ danh sách câu hỏi từ thí sinh, lưu vào DB, trả về dict đáp án Support đã chọn.
    Tự động phát hiện khi thí sinh sang ĐỀ MỚI:
      - Đóng gói ZIP lưu trữ đề cũ vào data/exam_archives
      - XÓA SẠCH câu hỏi cũ trong DB để không bị dồn ghép câu hỏi
      - Khởi tạo ca thi mới tinh khôi
    """
    import json
    now  = now_vn().strftime("%Y-%m-%d %H:%M:%S")
    hwid = hwid.strip()
    conn = get_connection()
    c    = conn.cursor()

    # Filter out bogus questions (e.g. from index/lobby pages with 0 options and generic placeholder stem)
    valid_questions = []
    for q in questions:
        q_text = (q.get("question_text") or "").strip()
        opts = q.get("options") or []
        q_type = (q.get("question_type") or "unknown").strip().lower()
        is_bogus = (len(opts) == 0 and ("[Đề bài dạng hình ảnh" in q_text or "[Câu hỏi dạng hình ảnh" in q_text) and q_type not in ["essay", "pea", "text"])
        if not is_bogus:
            valid_questions.append(q)

    # Check if DB already has existing questions for this hwid
    c.execute("SELECT COUNT(*) as cnt FROM live_exam_questions WHERE hwid = ?", (hwid,))
    cnt_existing = c.fetchone()
    has_existing_questions = bool(cnt_existing and cnt_existing["cnt"] > 0)

    clean_url = (page_url or "").strip().lower()
    is_lobby_url = clean_url.endswith("/exam/index") or clean_url.endswith("/quizprogress/exam") or "/login" in clean_url

    # If incoming questions is purely bogus (e.g. index/lobby page), but DB already has questions or it's a lobby url:
    if len(valid_questions) == 0 and (has_existing_questions or is_lobby_url):
        c.execute("""
            UPDATE live_exam_sessions
            SET last_sync = ?, status = 'active'
            WHERE hwid = ?
        """, (now, hwid))
        conn.commit()
        c.execute("SELECT question_index, support_answer FROM live_exam_questions WHERE hwid = ? AND support_answer != ''", (hwid,))
        answers = {str(r["question_index"]): r["support_answer"] for r in c.fetchall()}
        c.execute("SELECT auto_fill_requested FROM live_exam_sessions WHERE hwid = ?", (hwid,))
        af_row = c.fetchone()
        auto_fill = bool(af_row and dict(af_row).get("auto_fill_requested") == 1)
        conn.close()
        if return_details:
            return answers, False, auto_fill
        return answers

    questions_to_sync = valid_questions if valid_questions else questions

    # 1. Kiểm tra session hiện có và xác định xem có phải ĐỀ MỚI không
    c.execute("SELECT id, status, exam_title, page_url, total_questions, created_at, last_sync FROM live_exam_sessions WHERE hwid = ?", (hwid,))
    existing = c.fetchone()

    is_new = check_is_new_exam(existing, exam_title, page_url, questions_to_sync, c, hwid, new_subject_code=subject_code)
    should_reset_cache = is_new or (existing and (existing["status"] or "").strip().lower() == "reset_requested")

    eff_url = (page_url or "").strip()[:500]

    if is_new:
        # Nếu là đề mới và DB còn dữ liệu cũ -> Tự động đóng gói ZIP lưu trữ đề cũ trước
        if has_existing_questions and existing:
            try:
                archive_and_purge_exam_session(hwid, purge_questions=True, conn_override=conn)
            except Exception:
                pass

        # XÓA SẠCH toàn bộ câu hỏi cũ trong DB để không bị dồn câu hỏi của đề cũ vào đề mới
        c.execute("DELETE FROM live_exam_questions WHERE hwid = ?", (hwid,))

        # Khởi tạo session mới tinh khôi
        if existing:
            c.execute("""
                UPDATE live_exam_sessions
                SET student_name = ?, exam_title = ?, page_url = ?, total_questions = ?, last_sync = ?, status = 'active', created_at = ?,
                    remaining_time = CASE WHEN ? != '' THEN ? ELSE remaining_time END,
                    exam_server_time = CASE WHEN ? != '' THEN ? ELSE exam_server_time END,
                    subject_code = CASE WHEN ? != '' THEN ? ELSE subject_code END,
                    class_code = CASE WHEN ? != '' THEN ? ELSE class_code END,
                    campus = CASE WHEN ? != '' THEN ? ELSE campus END
                WHERE hwid = ?
            """, (student_name.strip(), exam_title.strip(), eff_url, len(questions_to_sync), now, now,
                    remaining_time.strip(), remaining_time.strip(),
                    exam_server_time.strip(), exam_server_time.strip(),
                    subject_code.strip(), subject_code.strip(),
                    class_code.strip(), class_code.strip(),
                    campus.strip(), campus.strip(),
                    hwid))
        else:
            c.execute("""
                INSERT INTO live_exam_sessions (hwid, student_name, exam_title, page_url, total_questions, status, last_sync, created_at, remaining_time, exam_server_time, subject_code, class_code, campus)
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?)
            """, (hwid, student_name.strip(), exam_title.strip(), eff_url, len(questions_to_sync), now, now, remaining_time.strip(), exam_server_time.strip(), subject_code.strip(), class_code.strip(), campus.strip()))
    else:
        # Cùng một đề thi (đang chuyển trang phân trang hoặc gửi cập nhật)
        if existing:
            if is_lobby_url and existing["page_url"] and not existing["page_url"].lower().endswith("/exam/index"):
                eff_url = existing["page_url"]
            c.execute("""
                UPDATE live_exam_sessions
                SET student_name = ?, exam_title = ?, page_url = ?, last_sync = ?, status = 'active',
                    remaining_time = CASE WHEN ? != '' THEN ? ELSE remaining_time END,
                    exam_server_time = CASE WHEN ? != '' THEN ? ELSE exam_server_time END,
                    subject_code = CASE WHEN ? != '' THEN ? ELSE subject_code END,
                    class_code = CASE WHEN ? != '' THEN ? ELSE class_code END,
                    campus = CASE WHEN ? != '' THEN ? ELSE campus END
                WHERE hwid = ?
            """, (student_name.strip(), exam_title.strip(), eff_url, now,
                    remaining_time.strip(), remaining_time.strip(),
                    exam_server_time.strip(), exam_server_time.strip(),
                    subject_code.strip(), subject_code.strip(),
                    class_code.strip(), class_code.strip(),
                    campus.strip(), campus.strip(),
                    hwid))
        else:
            c.execute("""
                INSERT INTO live_exam_sessions (hwid, student_name, exam_title, page_url, total_questions, status, last_sync, created_at, remaining_time, exam_server_time, subject_code, class_code, campus)
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?)
            """, (hwid, student_name.strip(), exam_title.strip(), eff_url, len(questions_to_sync), now, now, remaining_time.strip(), exam_server_time.strip(), subject_code.strip(), class_code.strip(), campus.strip()))

    # 2. Upsert từng câu hỏi
    for q in questions_to_sync:
        q_idx   = int(q.get("question_index") if q.get("question_index") is not None else q.get("index", 0))
        q_text  = clean_exam_stem_text(q.get("question_text") or "")[:1500]
        q_type  = (q.get("question_type") or "unknown").strip()
        cur_ans = (q.get("current_answer") or "").strip()

        # options: list of {label, text, image_base64}  OR legacy list of strings
        raw_opts = q.get("options") or []
        if raw_opts and isinstance(raw_opts[0], str):
            ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            raw_opts = [{"label": ALPHA[i] if i < 26 else str(i), "text": o, "image_base64": ""}
                        for i, o in enumerate(raw_opts)]

        # KHÔNG cắt cụt base64 giữa chừng (gây hỏng ảnh) - giữ nguyên vẹn đến 1.5MB
        opts_clean = []
        for o in raw_opts:
            oc = dict(o)
            b64 = oc.get("image_base64", "")
            if b64 and len(b64) <= 1500000:
                oc["image_base64"] = b64
            else:
                oc["image_base64"] = ""
            opts_clean.append(oc)
        opts_json = json.dumps(opts_clean, ensure_ascii=False)

        # Giữ nguyên vẹn ảnh câu hỏi đến 2MB (tránh corrupt)
        stem_img = q.get("image_base64") or ""
        if len(stem_img) > 2000000:
            stem_img = ""
        imgs_json = json.dumps([stem_img] if stem_img else [], ensure_ascii=False)

        try:
            c.execute("SELECT id, images_json, options_json FROM live_exam_questions WHERE hwid = ? AND question_index = ?", (hwid, q_idx))
            existing_row = c.fetchone()
            if existing_row:
                # Bảo toàn ảnh đề bài cũ nếu lượt sync này chưa tải kịp ảnh mới
                if not stem_img and existing_row["images_json"]:
                    try:
                        prev_imgs = json.loads(existing_row["images_json"])
                        if prev_imgs and len(prev_imgs) > 0 and prev_imgs[0]:
                            imgs_json = existing_row["images_json"]
                    except Exception:
                        pass

                # Bảo toàn ảnh lựa chọn cũ nếu lượt sync này chưa có ảnh
                if existing_row["options_json"]:
                    try:
                        prev_opts = json.loads(existing_row["options_json"])
                        for oi, opt in enumerate(opts_clean):
                            if not opt.get("image_base64") and oi < len(prev_opts):
                                prev_img = prev_opts[oi].get("image_base64")
                                if prev_img:
                                    opt["image_base64"] = prev_img
                        opts_json = json.dumps(opts_clean, ensure_ascii=False)
                    except Exception:
                        pass

                c.execute("""
                    UPDATE live_exam_questions
                    SET question_text = ?, question_type = ?, images_json = ?,
                        options_json = ?, current_answer = ?, updated_at = ?
                    WHERE hwid = ? AND question_index = ?
                """, (q_text, q_type, imgs_json, opts_json, cur_ans, now, hwid, q_idx))
            else:
                c.execute("""
                    INSERT INTO live_exam_questions
                        (hwid, question_index, question_text, question_type,
                         images_json, options_json, current_answer, support_answer, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, '', ?)
                """, (hwid, q_idx, q_text, q_type, imgs_json, opts_json, cur_ans, now))
        except sqlite3.OperationalError:
            for _col, _def in [("question_type", "TEXT DEFAULT 'unknown'"), ("current_answer", "TEXT DEFAULT ''"), ("support_answer", "TEXT DEFAULT ''"), ("images_json", "TEXT DEFAULT '[]'"), ("options_json", "TEXT DEFAULT '[]'")]:
                try: c.execute(f"ALTER TABLE live_exam_questions ADD COLUMN {_col} {_def}")
                except Exception: pass
            c.execute("""
                INSERT OR REPLACE INTO live_exam_questions
                    (hwid, question_index, question_text, question_type,
                     images_json, options_json, current_answer, support_answer, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, '', ?)
            """, (hwid, q_idx, q_text, q_type, imgs_json, opts_json, cur_ans, now))

    # Cập nhật chính xác số lượng câu hỏi hiện có trong DB cho ca thi này
    c.execute("SELECT COUNT(*) as cnt FROM live_exam_questions WHERE hwid = ?", (hwid,))
    cnt_row = c.fetchone()
    if cnt_row:
        c.execute("UPDATE live_exam_sessions SET total_questions = ? WHERE hwid = ?", (cnt_row["cnt"], hwid))

    # 3. Trả về đáp án support đã set cho thí sinh này
    c.execute("""
        SELECT question_index, support_answer
        FROM live_exam_questions
        WHERE hwid = ? AND support_answer != ''
    """, (hwid,))
    answers = {str(r["question_index"]): r["support_answer"] for r in c.fetchall()}

    c.execute("SELECT auto_fill_requested FROM live_exam_sessions WHERE hwid = ?", (hwid,))
    af_row = c.fetchone()
    auto_fill = bool(af_row and dict(af_row).get("auto_fill_requested") == 1)

    conn.commit()
    conn.close()

    if return_details:
        return answers, should_reset_cache, auto_fill
    return answers


def trigger_auto_fill_for_session(hwid: str) -> bool:
    """Admin yêu cầu máy học sinh tự động điền toàn bộ đáp án Support đã chọn."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE live_exam_sessions SET auto_fill_requested = 1 WHERE LOWER(hwid) = LOWER(?) OR hwid = ?", (hwid.strip(), hwid.strip()))
    conn.commit()
    conn.close()
    return True


def ack_auto_fill_for_session(hwid: str) -> bool:
    """Máy học sinh xác nhận đã điền xong full đáp án, tắt cờ auto_fill_requested."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE live_exam_sessions SET auto_fill_requested = 0 WHERE LOWER(hwid) = LOWER(?) OR hwid = ?", (hwid.strip(), hwid.strip()))
    conn.commit()
    conn.close()
    return True


def set_question_support_answer(hwid: str, question_index: int, support_answer: str) -> bool:
    """
    Admin chọn đáp án hỗ trợ.
    - radio/checkbox: index-based string "0" hoặc "0,2,3"
    - text/essay: chuỗi câu trả lời literal (không ép upper())
    """
    now  = now_vn().strftime("%Y-%m-%d %H:%M:%S")
    hwid = hwid.strip() if isinstance(hwid, str) else hwid
    ans  = (support_answer or "").strip()
    conn = get_connection()
    c    = conn.cursor()
    c.execute("""
        UPDATE live_exam_questions
        SET support_answer = ?, updated_at = ?
        WHERE hwid = ? AND question_index = ?
    """, (ans, now, hwid, question_index))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    return affected


def list_live_exam_sessions(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    c    = conn.cursor()
    c.execute("SELECT * FROM live_exam_sessions ORDER BY last_sync DESC LIMIT ?", (limit,))
    rows = []
    for r in c.fetchall():
        d = dict(r)
        d["question_count"] = d.get("total_questions", 0)
        rows.append(d)
    conn.close()
    return rows


def get_live_exam_questions(hwid: str) -> List[Dict[str, Any]]:
    """
    Trả về danh sách câu hỏi với options parse thành list of {label,text,image_base64}.
    """
    import json
    conn = get_connection()
    c    = conn.cursor()
    c.execute("SELECT * FROM live_exam_questions WHERE hwid = ? ORDER BY question_index ASC", (hwid.strip(),))
    rows = []
    for r in c.fetchall():
        d = dict(r)
        try:
            opts = json.loads(d.get("options_json") or "[]")
        except Exception:
            opts = []
        d["options"] = opts

        try:
            imgs = json.loads(d.get("images_json") or "[]")
        except Exception:
            imgs = []
        d["image_base64"] = imgs[0] if imgs else ""

        # Backward compat: rows created before question_type column
        if not d.get("question_type"):
            d["question_type"] = "radio" if opts else "unknown"

        rows.append(d)
    conn.close()
    return rows


def get_exam_questions_version(hwid: str) -> str:
    """Trả về chuỗi hash phiên bản của các câu hỏi thuộc hwid này để client kiểm tra thay đổi nhanh chóng (ETag)."""
    hwid = hwid.strip()
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt, MAX(updated_at) as last_mod FROM live_exam_questions WHERE hwid = ?", (hwid,))
    row = c.fetchone()
    conn.close()
    if not row or not row["cnt"]:
        return "empty"
    return f"{row['cnt']}_{row['last_mod']}"


def archive_and_purge_exam_session(hwid: str, purge_questions: bool = False, conn_override: sqlite3.Connection = None) -> Optional[Dict[str, Any]]:
    """
    Đóng gói toàn bộ đề thi, ảnh và đáp án thành file ZIP chuẩn làm source đề.
    Nếu purge_questions=True: xóa sạch câu hỏi trong live_exam_questions để giải phóng hoàn toàn và sẵn sàng cho đề mới.
    """
    import os, json, zipfile, base64, re
    hwid = hwid.strip()
    should_close = False
    if conn_override:
        conn = conn_override
    else:
        conn = get_connection()
        should_close = True
    c = conn.cursor()

    # 1. Lấy thông tin session
    c.execute("SELECT * FROM live_exam_sessions WHERE hwid = ?", (hwid,))
    s_row = c.fetchone()
    if not s_row:
        if should_close: conn.close()
        return None
    session = dict(s_row)

    # 2. Lấy danh sách câu hỏi
    questions = get_live_exam_questions(hwid)
    if not questions:
        c.execute("UPDATE live_exam_sessions SET status = 'archived' WHERE hwid = ?", (hwid,))
        conn.commit()
        if should_close: conn.close()
        return None

    # 3. Tạo file ZIP lưu trữ source
    archive_dir = os.path.join(os.path.dirname(__file__), "data", "exam_archives")
    os.makedirs(archive_dir, exist_ok=True)

    safe_student = re.sub(r'[\\/*?:"<>| ]', '_', session.get("student_name") or "ThiSinh")
    safe_title = re.sub(r'[\\/*?:"<>| ]', '_', (session.get("exam_title") or "DeThi")[:30])
    timestamp = now_vn().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"Source_{safe_title}_{safe_student}_{timestamp}.zip"
    zip_path = os.path.join(archive_dir, zip_filename)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # File 1: info.txt
        info_lines = [
            f"BÀI THI: {session.get('exam_title')}",
            f"THÍ SINH: {session.get('student_name')}",
            f"MÃ MÁY (HWID): {hwid}",
            f"THỜI GIAN THI: {session.get('created_at')} -> {now_vn().strftime('%Y-%m-%d %H:%M:%S')}",
            f"TỔNG SỐ CÂU HỎI: {len(questions)}",
            "=" * 50
        ]
        z.writestr("info.txt", "\n".join(info_lines).encode("utf-8"))

        # File 2: dap_an.txt (Bảng đáp án nguồn định dạng chuẩn để tra cứu / ôn tập)
        ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        ans_lines = [
            f"BẢNG ĐÁP ÁN NGUỒN (EXAM ANSWER KEY)",
            f"Đề: {session.get('exam_title')} | Thí sinh: {session.get('student_name')}",
            "-" * 50
        ]
        for idx, q in enumerate(questions):
            q_num = idx + 1
            support_ans = q.get("support_answer", "")
            student_ans = q.get("current_answer", "")
            opts = q.get("options") or []
            
            ans_display = support_ans or student_ans or "(Chưa có)"
            if support_ans.isdigit():
                oi = int(support_ans)
                if oi < len(opts) and isinstance(opts[oi], dict):
                    ans_display = f"{opts[oi].get('label', ALPHA[oi])} - {opts[oi].get('text', '')}"
                elif oi < 26:
                    ans_display = ALPHA[oi]

            ans_lines.append(f"Câu {q_num:02d}: Đáp án hỗ trợ: [{support_ans}] | Thí sinh: [{student_ans}] | Chi tiết: {ans_display}")
            ans_lines.append(f"   Đề bài: {q.get('question_text', '')[:120]}")
            ans_lines.append("")
        z.writestr("dap_an.txt", "\n".join(ans_lines).encode("utf-8"))

        # File 3: questions.json (Dữ liệu nguồn JSON nguyên bản)
        z.writestr("questions.json", json.dumps(questions, ensure_ascii=False, indent=2).encode("utf-8"))

        # File 4: Thư mục images/ chứa các ảnh đề bài và lựa chọn
        for idx, q in enumerate(questions):
            q_num = idx + 1
            stem_b64 = q.get("image_base64") or ""
            if stem_b64 and "base64," in stem_b64:
                try:
                    img_data = base64.b64decode(stem_b64.split("base64,")[1])
                    z.writestr(f"images/Cau_{q_num:02d}.png", img_data)
                except Exception:
                    pass

            opts = q.get("options") or []
            for oi, o in enumerate(opts):
                if isinstance(o, dict):
                    opt_b64 = o.get("image_base64") or ""
                    lbl = o.get("label") or (ALPHA[oi] if oi < 26 else str(oi))
                    if opt_b64 and "base64," in opt_b64:
                        try:
                            o_data = base64.b64decode(opt_b64.split("base64,")[1])
                            z.writestr(f"images/Cau_{q_num:02d}_Opt_{lbl}.png", o_data)
                        except Exception:
                            pass

    file_size = os.path.getsize(zip_path)

    # 4. Ghi nhận vào bảng archived_exam_sources
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS archived_exam_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hwid TEXT,
                student_name TEXT,
                exam_title TEXT,
                archive_filename TEXT UNIQUE,
                file_size_bytes INTEGER,
                total_questions INTEGER,
                created_at TEXT
            )
        """)
        c.execute("""
            INSERT OR REPLACE INTO archived_exam_sources
            (hwid, student_name, exam_title, archive_filename, file_size_bytes, total_questions, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (hwid, session.get("student_name"), session.get("exam_title"), zip_filename, file_size, len(questions), now_vn().strftime("%Y-%m-%d %H:%M:%S")))
    except Exception:
        pass

    # 5. Cập nhật trạng thái session
    if purge_questions:
        c.execute("DELETE FROM live_exam_questions WHERE hwid = ?", (hwid,))
        c.execute("UPDATE live_exam_sessions SET status = 'archived', total_questions = 0 WHERE hwid = ?", (hwid,))
    else:
        c.execute("UPDATE live_exam_sessions SET status = 'archived', total_questions = ? WHERE hwid = ?", (len(questions), hwid))

    conn.commit()
    if should_close:
        conn.close()

    return {
        "success": True,
        "filename": zip_filename,
        "path": zip_path,
        "download_url": f"/api/admin/download-archive/{zip_filename}",
        "size_bytes": file_size,
        "total_questions": len(questions)
    }


def reset_and_archive_exam_session(hwid: str) -> Dict[str, Any]:
    """
    Chủ động lưu trữ ca thi cũ thành ZIP và xóa sạch live_exam_questions để thí sinh nạp đề mới hoàn toàn.
    Được gọi khi Admin hoặc Support bấm nút 'Bắt Đầu Đề Mới'.
    """
    hwid = hwid.strip()
    archive_res = archive_and_purge_exam_session(hwid, purge_questions=True)
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM live_exam_questions WHERE hwid = ?", (hwid,))
    c.execute("""
        UPDATE live_exam_sessions
        SET total_questions = 0, status = 'reset_requested', last_sync = ?
        WHERE hwid = ?
    """, (now_vn().strftime("%Y-%m-%d %H:%M:%S"), hwid))
    conn.commit()
    conn.close()
    return {
        "success": True,
        "message": "Đã lưu trữ đề cũ và làm sạch dữ liệu thành công! Đề thi tiếp theo sẽ nạp mới 100%.",
        "archive": archive_res
    }


def get_live_exam_session(hwid: str) -> Optional[Dict[str, Any]]:
    """Lấy thông tin session hiện tại của 1 máy theo HWID."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM live_exam_sessions WHERE hwid = ?", (hwid.strip(),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def update_live_exam_session_status(hwid: str, status: str) -> bool:
    """Cập nhật trạng thái session (e.g. active, finished, archived, reset_requested)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE live_exam_sessions SET status = ? WHERE hwid = ?", (status.strip(), hwid.strip()))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    return affected


def cleanup_archived_sources_older_than(max_age_hours: float = 24.0) -> int:
    """Xóa các file ZIP lưu trữ trong data/exam_archives và bản ghi trong archived_exam_sources đã quá 24 giờ."""
    from datetime import datetime, timedelta
    import os
    conn = get_connection()
    c = conn.cursor()
    cutoff_time = (now_vn() - timedelta(hours=max_age_hours)).strftime("%Y-%m-%d %H:%M:%S")
    
    deleted_count = 0
    try:
        c.execute("SELECT id, archive_filename FROM archived_exam_sources WHERE created_at < ?", (cutoff_time,))
        expired_rows = c.fetchall()
        
        archive_dir = os.path.join(os.path.dirname(__file__), "data", "exam_archives")
        for r in expired_rows:
            fn = r["archive_filename"]
            fp = os.path.join(archive_dir, fn)
            if os.path.exists(fp):
                try:
                    os.remove(fp)
                except Exception:
                    pass
            c.execute("DELETE FROM archived_exam_sources WHERE id = ?", (r["id"],))
            deleted_count += 1
            
        conn.commit()
    except Exception:
        deleted_count = 0
    finally:
        conn.close()
    return deleted_count


def auto_archive_expired_sessions(max_age_hours: float = 24.0) -> int:
    """
    Tự động quét các ca thi cũ hơn 24 tiếng:
    Lưu toàn bộ bài đã support trong 24h tiếp theo mới xóa để admin có thể tải về hoặc xem lại.
    Sau 24h: Đóng gói thành file ZIP source lưu trữ và xóa sạch câu hỏi trong DB để giải phóng dung lượng & RAM máy chủ.
    """
    from datetime import datetime, timedelta
    conn = get_connection()
    c = conn.cursor()
    cutoff_time = (now_vn() - timedelta(hours=max_age_hours)).strftime("%Y-%m-%d %H:%M:%S")
    
    # Chỉ dọn dẹp các ca thi có last_sync đã quá 24 tiếng
    c.execute("""
        SELECT hwid FROM live_exam_sessions
        WHERE last_sync < ?
    """, (cutoff_time,))
    rows = c.fetchall()
    conn.close()

    archived_count = 0
    for r in rows:
        h = r["hwid"]
        res = archive_and_purge_exam_session(h, purge_questions=True)
        # Xóa record ca thi đã quá 24h trong live_exam_sessions
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM live_exam_sessions WHERE hwid = ? AND last_sync < ?", (h, cutoff_time))
        conn.commit()
        conn.close()
        if res and res.get("success"):
            archived_count += 1

    # Dọn dẹp các file ZIP trong kho đã vượt quá 24h
    cleanup_archived_sources_older_than(max_age_hours=max_age_hours)

    return archived_count


def list_archived_exam_sources(limit: int = 50) -> List[Dict[str, Any]]:
    """Lấy danh sách các file ZIP source đề thi đã lưu trữ."""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS archived_exam_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hwid TEXT,
                student_name TEXT,
                exam_title TEXT,
                archive_filename TEXT UNIQUE,
                file_size_bytes INTEGER,
                total_questions INTEGER,
                created_at TEXT
            )
        """)
        # Tự động quét và đồng bộ các file ZIP trong thư mục data/exam_archives nếu chưa có trong DB
        archive_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "exam_archives")
        if os.path.exists(archive_dir):
            for fname in os.listdir(archive_dir):
                if fname.lower().endswith(".zip"):
                    c.execute("SELECT id FROM archived_exam_sources WHERE archive_filename = ?", (fname,))
                    if not c.fetchone():
                        fpath = os.path.join(archive_dir, fname)
                        fsize = os.path.getsize(fpath)
                        total_q = 0
                        hwid = ""
                        st_name = "Thí sinh"
                        title = "Kỳ thi"
                        try:
                            import zipfile, json
                            with zipfile.ZipFile(fpath, "r") as z:
                                if "questions.json" in z.namelist():
                                    q_data = json.loads(z.read("questions.json").decode("utf-8"))
                                    total_q = len(q_data)
                                    if total_q > 0:
                                        hwid = q_data[0].get("hwid", "")
                                if "info.txt" in z.namelist():
                                    info_str = z.read("info.txt").decode("utf-8", "ignore")
                                    for line in info_str.splitlines():
                                        if "Tên thí sinh:" in line:
                                            st_name = line.split(":", 1)[1].strip()
                                        elif "Kỳ thi:" in line:
                                            title = line.split(":", 1)[1].strip()
                        except Exception:
                            pass
                        import datetime
                        mtime = os.path.getmtime(fpath)
                        created_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                        c.execute("""
                            INSERT OR IGNORE INTO archived_exam_sources
                            (hwid, student_name, exam_title, archive_filename, file_size_bytes, total_questions, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (hwid, st_name, title, fname, fsize, total_q, created_str))
            conn.commit()

        c.execute("SELECT * FROM archived_exam_sources ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in c.fetchall()]
    except Exception:
        rows = []
    conn.close()
    return rows


# ────────────────── Support Keys & Exam Scheduling ──────────────────

SUPPORT_KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
SUPPORT_KEY_SALT = "SEB_SUPPORT_SECRET_SALT_2026"

def _calc_support_checksum(prefix: str) -> str:
    h = hashlib.sha256(f"{SUPPORT_KEY_SALT}:{prefix}".encode()).hexdigest().upper()
    res = []
    for i in range(4):
        val = int(h[i * 2 : i * 2 + 2], 16) % len(SUPPORT_KEY_ALPHABET)
        res.append(SUPPORT_KEY_ALPHABET[val])
    return "".join(res)

def generate_support_key() -> str:
    """Sinh key bảo mật dài: SUP-XXXX-XXXX-XXXX-YYYY với checksum SHA-256 chống gõ nhầm"""
    p1 = "".join(secrets.choice(SUPPORT_KEY_ALPHABET) for _ in range(4))
    p2 = "".join(secrets.choice(SUPPORT_KEY_ALPHABET) for _ in range(4))
    p3 = "".join(secrets.choice(SUPPORT_KEY_ALPHABET) for _ in range(4))
    prefix = f"SUP-{p1}-{p2}-{p3}"
    checksum = _calc_support_checksum(prefix)
    return f"{prefix}-{checksum}"

def verify_support_key_checksum(key: str) -> bool:
    """Kiểm tra cấu trúc và checksum mã key Support"""
    key = (key or "").strip().upper()
    parts = key.split("-")
    if len(parts) != 5 or parts[0] != "SUP":
        return False
    if any(len(p) != 4 for p in parts[1:]):
        return False
    prefix = "-".join(parts[:4])
    expected = _calc_support_checksum(prefix)
    return parts[4] == expected

def create_support_key(assigned_name: str, email: str = "", phone: str = "", note: str = "", expires_at: str = "") -> Dict[str, Any]:
    key_code = generate_support_key()
    now = now_vn().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO support_keys (key_code, assigned_name, email, phone, note, status, created_at, expires_at, last_login)
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?, '')
    """, (key_code, assigned_name.strip(), email.strip(), phone.strip(), note.strip(), now, expires_at.strip()))
    conn.commit()
    conn.close()
    return get_support_key(key_code)

def get_support_key(key_code: str) -> Optional[Dict[str, Any]]:
    key_code = (key_code or "").strip().upper()
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM support_keys WHERE UPPER(key_code) = ?", (key_code,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def list_support_keys() -> List[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM support_keys ORDER BY id DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def update_support_key_status(key_code: str, status: str) -> bool:
    """Cập nhật trạng thái: active (kích hoạt), suspended (tạm khóa), locked (khóa vĩnh viễn)"""
    key_code = (key_code or "").strip().upper()
    status = status.lower().strip()
    if status not in ("active", "suspended", "locked"):
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE support_keys SET status = ? WHERE UPPER(key_code) = ?", (status, key_code))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def update_support_key_expiry(key_code: str, expires_at: str) -> bool:
    key_code = (key_code or "").strip().upper()
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE support_keys SET expires_at = ? WHERE UPPER(key_code) = ?", (expires_at.strip(), key_code))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def update_support_key_last_login(key_code: str) -> bool:
    key_code = (key_code or "").strip().upper()
    now = now_vn().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE support_keys SET last_login = ? WHERE UPPER(key_code) = ?", (now, key_code))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def delete_support_key(key_code: str) -> bool:
    key_code = (key_code or "").strip().upper()
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM support_keys WHERE UPPER(key_code) = ?", (key_code,))
    c.execute("DELETE FROM support_assignments WHERE UPPER(support_key) = ?", (key_code,))
    conn.commit()
    conn.close()
    return True

def create_support_assignment(support_key: str, hwid: str, student_name: str = "", exam_date: str = "", exam_shift: str = "", subject: str = "", notes: str = "") -> Dict[str, Any]:
    support_key = (support_key or "").strip().upper()
    hwid = (hwid or "").strip()
    now = now_vn().strftime("%Y-%m-%d %H:%M:%S")
    if not exam_date:
        exam_date = now_vn().strftime("%Y-%m-%d")
    else:
        exam_date = exam_date.strip()

    if not student_name:
        lic = get_license_by_hwid(hwid)
        if lic:
            student_name = lic.get("student_name") or ""

    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO support_assignments (support_key, hwid, student_name, exam_date, exam_shift, subject, notes, created_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
        ON CONFLICT(support_key, hwid, exam_date) DO UPDATE SET
            student_name = excluded.student_name,
            exam_shift = excluded.exam_shift,
            subject = excluded.subject,
            notes = excluded.notes,
            status = 'active'
    """, (support_key, hwid, student_name, exam_date, exam_shift.strip(), subject.strip(), notes.strip(), now))
    conn.commit()
    last_id = c.lastrowid
    conn.close()
    return {"id": last_id, "support_key": support_key, "hwid": hwid, "student_name": student_name, "exam_date": exam_date, "exam_shift": exam_shift, "subject": subject, "notes": notes}

def list_support_assignments(support_key: Optional[str] = None, exam_date: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    query = """
        SELECT a.*, k.assigned_name, k.status as key_status
        FROM support_assignments a
        LEFT JOIN support_keys k ON UPPER(a.support_key) = UPPER(k.key_code)
        WHERE 1=1
    """
    params = []
    if support_key:
        query += " AND UPPER(a.support_key) = ?"
        params.append(support_key.strip().upper())
    if exam_date:
        query += " AND a.exam_date = ?"
        params.append(exam_date.strip())
    query += " ORDER BY a.exam_date DESC, a.id DESC"
    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def delete_support_assignment(assignment_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM support_assignments WHERE id = ?", (assignment_id,))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def is_hwid_assigned_to_support(support_key: str, hwid: str, target_date: Optional[str] = None) -> bool:
    """Kiểm tra bảo mật RBAC: HWID này có được phân công cho Support Key này vào ngày target_date không?"""
    support_key = (support_key or "").strip().upper()
    hwid = (hwid or "").strip()
    if not support_key or not hwid:
        return False
    
    k = get_support_key(support_key)
    if not k or k.get("status") != "active":
        return False
    
    exp = k.get("expires_at")
    if exp:
        try:
            today_str = now_vn().strftime("%Y-%m-%d")
            if today_str > exp:
                return False
        except Exception:
            pass

    if not target_date:
        target_date = now_vn().strftime("%Y-%m-%d")

    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT 1 FROM support_assignments 
        WHERE UPPER(support_key) = ? AND hwid = ? AND exam_date = ? AND status = 'active'
        LIMIT 1
    """, (support_key, hwid, target_date))
    row = c.fetchone()
    conn.close()
    return row is not None

def get_support_assigned_exams_for_date(support_key: str, target_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Lấy danh sách các ca thi và máy được phân công cho Support Key này trong ngày target_date (mặc định hôm nay).
    Chỉ trả về máy được phân công, kết hợp với trạng thái thi trực tiếp từ live_exam_sessions.
    """
    support_key = (support_key or "").strip().upper()
    k = get_support_key(support_key)
    if not k:
        return {"success": False, "message": "Mã Key Support không tồn tại!", "sessions": []}
    
    if k.get("status") == "suspended":
        return {"success": False, "message": "Key của bạn đang bị TẠM KHÓA bởi Quản trị viên!", "status": "suspended", "sessions": []}
    if k.get("status") == "locked":
        return {"success": False, "message": "Key của bạn đã bị KHÓA vĩnh viễn!", "status": "locked", "sessions": []}

    exp = k.get("expires_at")
    if exp:
        today_str = now_vn().strftime("%Y-%m-%d")
        if today_str > exp:
            return {"success": False, "message": f"Key đã hết hạn sử dụng vào ngày {exp}!", "status": "expired", "sessions": []}

    if not target_date:
        target_date = now_vn().strftime("%Y-%m-%d")

    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT a.*, 
               s.exam_title, s.total_questions, s.status as session_status, s.last_sync,
               s.remaining_time, s.exam_server_time, s.subject_code, s.class_code, s.campus,
               l.student_name as lic_student_name, l.machine_name, l.ip_address, l.status as lic_status
        FROM support_assignments a
        LEFT JOIN live_exam_sessions s ON a.hwid = s.hwid
        LEFT JOIN licenses l ON a.hwid = l.hwid
        WHERE UPPER(a.support_key) = ? AND a.exam_date = ? AND a.status = 'active'
        ORDER BY a.id ASC
    """, (support_key, target_date))
    rows = c.fetchall()
    conn.close()

    now_dt = now_vn()
    results = []
    for r in rows:
        d = dict(r)
        last_sync_str = d.get("last_sync") or ""
        is_online = False
        if last_sync_str:
            try:
                sync_dt = datetime.strptime(last_sync_str, "%Y-%m-%d %H:%M:%S")
                if (now_dt - sync_dt).total_seconds() <= 120:
                    is_online = True
            except Exception:
                pass
        
        student_display = d.get("student_name") or d.get("lic_student_name") or "Thí sinh"
        exam_title_display = d.get("subject") or d.get("exam_title") or "Bài thi trực tuyến"
        
        results.append({
            "assignment_id": d["id"],
            "hwid": d["hwid"],
            "student_name": student_display,
            "machine_name": d.get("machine_name") or "",
            "ip_address": d.get("ip_address") or "",
            "exam_date": d["exam_date"],
            "exam_shift": d.get("exam_shift") or "Tự do",
            "subject": exam_title_display,
            "notes": d.get("notes") or "",
            "total_questions": d.get("total_questions") or 0,
            "session_status": d.get("session_status") or ("active" if is_online else "pending"),
            "last_sync": last_sync_str,
            "is_online": is_online,
            "remaining_time": d.get("remaining_time") or "",
            "exam_server_time": d.get("exam_server_time") or "",
            "subject_code": d.get("subject_code") or "",
            "class_code": d.get("class_code") or "",
            "exam_title": d.get("exam_title") or "",
            "campus": d.get("campus") or ""
        })

    return {
        "success": True,
        "support_key": support_key,
        "assigned_name": k.get("assigned_name"),
        "exam_date": target_date,
        "total_assigned": len(results),
        "sessions": results
    }

