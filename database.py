import sqlite3
import os
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

    try:
        cursor.execute("ALTER TABLE licenses ADD COLUMN phone TEXT DEFAULT ''")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE licenses ADD COLUMN notes TEXT DEFAULT ''")
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
        images_json TEXT DEFAULT '[]',
        options_json TEXT NOT NULL,
        support_answer TEXT DEFAULT '', -- Đáp án do Support chọn: A, B, C, D
        updated_at TEXT NOT NULL,
        UNIQUE(hwid, question_index)
    )
    """)

    # Các giá trị mặc định cho settings
    default_settings = {
        "admin_password": "Nguyenphuc1234@",
        "download_require_approval": "true",
        "telegram_bot_token": "8902883418:AAF1rAAcEVx4gyI9gcJW5GrBjqB-PphSuf8",
        "telegram_chat_id": "6396371761",
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
    cursor.execute("UPDATE settings SET value = '8902883418:AAF1rAAcEVx4gyI9gcJW5GrBjqB-PphSuf8' WHERE key = 'telegram_bot_token' AND (value = '' OR value IS NULL)")
    cursor.execute("UPDATE settings SET value = '6396371761' WHERE key = 'telegram_chat_id' AND (value = '' OR value IS NULL)")

    # 6. Tự động nạp danh sách mã máy lịch sử và bản quyền từ seed_data.json
    seed_initial_data(cursor)

    conn.commit()
    conn.close()

# ────────────────── Download Requests API ──────────────────

def create_download_request(request_id: str, full_name: str, email: str, note: str, ip_address: str) -> Dict[str, Any]:
    now = now_vn().strftime("%Y-%m-%d %H:%M:%S")
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
    now = now_vn().strftime("%Y-%m-%d %H:%M:%S")
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

def list_access_logs(limit: int = 200, hwid: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    if hwid:
        c.execute("SELECT * FROM access_logs WHERE hwid = ? ORDER BY id DESC LIMIT ?", (hwid.strip(), limit))
    else:
        c.execute("SELECT * FROM access_logs ORDER BY id DESC LIMIT ?", (limit,))
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
        try:
            print(f"[Seed] Successfully seeded {len(seed.get('licenses', []))} licenses and {len(seed.get('download_requests', []))} downloads.")
        except Exception:
            pass
    except Exception as e:
        try:
            print(f"[Warning] Failed to load seed_data.json: {e}")
        except Exception:
            pass

def sync_seed_file():
    """Tự động đồng bộ các license và yêu cầu tải mới nhất ra seed_data.json để lưu trữ lâu dài"""
    try:
        data = export_all_data()
        payload = {
            "licenses": data.get("licenses", []),
            "download_requests": data.get("download_requests", [])
        }
        import json
        with open(SEED_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def export_all_data() -> Dict[str, Any]:
    """Xuất toàn bộ cơ sở dữ liệu thành đối tượng Dict JSON để tải về máy tính"""
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT * FROM licenses ORDER BY id ASC")
    licenses = [dict(r) for r in c.fetchall()]
    
    c.execute("SELECT * FROM download_requests ORDER BY id ASC")
    download_requests = [dict(r) for r in c.fetchall()]
    
    c.execute("SELECT * FROM chat_messages ORDER BY id ASC")
    chat_messages = [dict(r) for r in c.fetchall()]
    
    c.execute("SELECT * FROM access_logs ORDER BY id DESC LIMIT 500")
    access_logs = [dict(r) for r in c.fetchall()]
    
    c.execute("SELECT key, value FROM settings")
    settings = {r["key"]: r["value"] for r in c.fetchall()}
    
    conn.close()
    return {
        "exported_at": now_vn().strftime("%Y-%m-%d %H:%M:%S"),
        "licenses": licenses,
        "download_requests": download_requests,
        "chat_messages": chat_messages,
        "access_logs": access_logs,
        "settings": settings
    }

def import_all_data(data: Dict[str, Any], overwrite: bool = False) -> Dict[str, int]:
    """Nạp dữ liệu từ file backup JSON vào cơ sở dữ liệu"""
    conn = get_connection()
    c = conn.cursor()
    stats = {"licenses": 0, "download_requests": 0, "chat_messages": 0, "access_logs": 0}
    
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
            
    conn.commit()
    conn.close()
    sync_seed_file()
    return stats

# ────────────────── Live Exam Sync & Support API ──────────────────

def sync_student_exam_data(hwid: str, student_name: str, exam_title: str, questions: list) -> Dict[str, str]:
    """Cập nhật toàn bộ câu hỏi/ảnh từ thí sinh lên và trả về các đáp án do Support chỉ định"""
    now = now_vn().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    c = conn.cursor()

    # 1. Cập nhật session
    c.execute("SELECT id FROM live_exam_sessions WHERE hwid = ?", (hwid.strip(),))
    sess = c.fetchone()
    if sess:
        c.execute("""
            UPDATE live_exam_sessions
            SET student_name = ?, exam_title = ?, total_questions = ?, last_sync = ?, status = 'active'
            WHERE hwid = ?
        """, (student_name.strip(), exam_title.strip(), len(questions), now, hwid.strip()))
    else:
        c.execute("""
            INSERT INTO live_exam_sessions (hwid, student_name, exam_title, total_questions, status, last_sync, created_at)
            VALUES (?, ?, ?, ?, 'active', ?, ?)
        """, (hwid.strip(), student_name.strip(), exam_title.strip(), len(questions), now, now))

    # 2. Cập nhật danh sách câu hỏi
    import json
    for q in questions:
        q_idx = q.get("index") or 0
        if not q_idx:
            continue
        q_text = (q.get("question_text") or "").strip()
        imgs = json.dumps(q.get("images", []), ensure_ascii=False)
        opts = json.dumps(q.get("options", []), ensure_ascii=False)

        c.execute("SELECT id FROM live_exam_questions WHERE hwid = ? AND question_index = ?", (hwid.strip(), q_idx))
        existing_q = c.fetchone()
        if existing_q:
            c.execute("""
                UPDATE live_exam_questions
                SET question_text = ?, images_json = ?, options_json = ?, updated_at = ?
                WHERE hwid = ? AND question_index = ?
            """, (q_text, imgs, opts, now, hwid.strip(), q_idx))
        else:
            c.execute("""
                INSERT INTO live_exam_questions (hwid, question_index, question_text, images_json, options_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (hwid.strip(), q_idx, q_text, imgs, opts, now))

    # 3. Lấy toàn bộ đáp án Support đã chọn cho thí sinh này
    c.execute("SELECT question_index, support_answer FROM live_exam_questions WHERE hwid = ? AND support_answer != ''", (hwid.strip(),))
    answers = {str(r["question_index"]): r["support_answer"] for r in c.fetchall()}

    conn.commit()
    conn.close()
    return answers

def set_question_support_answer(hwid: str, question_index: int, support_answer: str) -> bool:
    """Support chọn đáp án trên web: A, B, C, D"""
    now = now_vn().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE live_exam_questions
        SET support_answer = ?, updated_at = ?
        WHERE hwid = ? AND question_index = ?
    """, (support_answer.strip().upper(), now, hwid.strip(), question_index))
    affected = c.rowcount > 0
    conn.commit()
    conn.close()
    return affected

def list_live_exam_sessions(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM live_exam_sessions ORDER BY last_sync DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_live_exam_questions(hwid: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM live_exam_questions WHERE hwid = ? ORDER BY question_index ASC", (hwid.strip(),))
    import json
    rows = []
    for r in c.fetchall():
        d = dict(r)
        d["images"] = json.loads(d["images_json"]) if d.get("images_json") else []
        d["options"] = json.loads(d["options_json"]) if d.get("options_json") else []
        rows.append(d)
    conn.close()
    return rows



