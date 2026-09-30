import os
import uuid
import asyncio
import hashlib
import httpx
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import database
import crypto_engine
import storage
import telegram_bot
import exam_parser
from starlette.middleware.gzip import GZipMiddleware

# ────────────────── App Lifespan & Keep-Alive ──────────────────
async def render_keepalive_task():
    """Tự động gửi ping đến máy chủ mỗi 10 phút để Render không bao giờ ngủ đông"""
    await asyncio.sleep(60) # Chờ 1 phút sau khi khởi động
    while True:
        try:
            render_url = os.environ.get("RENDER_EXTERNAL_URL") or "https://seb-ki1x.onrender.com"
            ping_url = f"{render_url.rstrip('/')}/api/ping"
            async with httpx.AsyncClient(timeout=15.0) as client:
                await client.get(ping_url)
        except Exception:
            pass
        await asyncio.sleep(600) # Mỗi 10 phút ping 1 lần

async def exam_cleanup_task():
    """Tự động kiểm tra và lưu trữ toàn bộ bài thi đã support trong 24 tiếng. Sau 24h mới xóa để admin xem lại và tải về."""
    await asyncio.sleep(120)
    while True:
        try:
            archived = database.auto_archive_expired_sessions(max_age_hours=24.0)
            if archived > 0:
                print(f"[Cleanup 24h] Tự động dọn dẹp {archived} ca thi đã quá 24 tiếng sau khi thi xong.")
        except Exception as e:
            print(f"[Cleanup Error] {e}")
        await asyncio.sleep(900) # Mỗi 15 phút quét 1 lần

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi tạo cơ sở dữ liệu
    database.init_db()
    print("[System] Database SQLite ready.")

    # Khởi động Telegram Bot Polling, Keep-Alive và Auto-Cleanup ở chế độ nền
    bot_task = asyncio.create_task(telegram_bot.start_telegram_polling())
    keepalive_task = asyncio.create_task(render_keepalive_task())
    cleanup_task = asyncio.create_task(exam_cleanup_task())
    yield
    bot_task.cancel()
    keepalive_task.cancel()
    cleanup_task.cancel()

app = FastAPI(title="SEB Licensing Portal", lifespan=lifespan)

# Bật nén GZIP cho toàn bộ HTTP response >= 1KB (giảm 70-85% băng thông Outbound trên Render)
app.add_middleware(GZipMiddleware, minimum_size=1000)

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ────────────────── Admin Authentication ──────────────────
AUTH_COOKIE_NAME = "seb_admin_token"
AUTH_SALT = "seb_licensing_auth_salt_super_secret_2026"

def get_admin_expected_token() -> str:
    admin_pass = database.get_setting("admin_password", "admin")
    return hashlib.sha256(f"{admin_pass}:{AUTH_SALT}".encode()).hexdigest()

def is_admin_authenticated(request: Request) -> bool:
    token = request.cookies.get(AUTH_COOKIE_NAME) or request.headers.get("x-admin-token")
    if not token:
        return False
    return token == get_admin_expected_token()

def require_admin(request: Request):
    if not is_admin_authenticated(request):
        raise HTTPException(status_code=401, detail="Chưa đăng nhập quyền Quản trị viên!")
    return True

# ────────────────── Support Authentication ──────────────────
SUPPORT_COOKIE_NAME = "seb_support_token"
SUPPORT_AUTH_SALT = "seb_support_auth_salt_super_secret_2026"

def create_support_session_token(support_key: str) -> str:
    key_clean = support_key.strip().upper()
    sig = hashlib.sha256(f"{key_clean}:{SUPPORT_AUTH_SALT}".encode()).hexdigest()
    return f"{key_clean}:{sig}"

def verify_support_session_token(token: str) -> Optional[str]:
    if not token or ":" not in token:
        return None
    parts = token.split(":", 1)
    if len(parts) != 2:
        return None
    key_clean, sig = parts
    expected_sig = hashlib.sha256(f"{key_clean}:{SUPPORT_AUTH_SALT}".encode()).hexdigest()
    if sig != expected_sig:
        return None
    return key_clean

def is_support_authenticated(request: Request) -> bool:
    token = request.cookies.get(SUPPORT_COOKIE_NAME) or request.headers.get("x-support-token")
    if not token:
        return False
    key_clean = verify_support_session_token(token)
    if not key_clean:
        return False
    k = database.get_support_key(key_clean)
    if not k or k.get("status") != "active":
        return False
    exp = k.get("expires_at")
    if exp:
        today_str = database.now_vn().strftime("%Y-%m-%d")
        if today_str > exp:
            return False
    return True

def get_current_support(request: Request) -> Dict[str, Any]:
    token = request.cookies.get(SUPPORT_COOKIE_NAME) or request.headers.get("x-support-token")
    if not token:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập Support Key!")
    key_clean = verify_support_session_token(token)
    if not key_clean:
        raise HTTPException(status_code=401, detail="Token Support không hợp lệ!")
    k = database.get_support_key(key_clean)
    if not k:
        raise HTTPException(status_code=401, detail="Support Key không tồn tại trên hệ thống!")
    if k.get("status") == "suspended":
        raise HTTPException(status_code=403, detail="Key của bạn đang bị TẠM KHÓA bởi Quản trị viên!")
    if k.get("status") == "locked":
        raise HTTPException(status_code=403, detail="Key của bạn đã bị KHÓA vĩnh viễn!")
    exp = k.get("expires_at")
    if exp:
        today_str = database.now_vn().strftime("%Y-%m-%d")
        if today_str > exp:
            raise HTTPException(status_code=403, detail=f"Key đã hết hạn sử dụng vào ngày {exp}!")
    return k

# ────────────────── Pydantic Request Models ──────────────────

class SupportLoginModel(BaseModel):
    key_code: str

class SupportKeyCreateModel(BaseModel):
    assigned_name: str
    email: Optional[str] = ""
    phone: Optional[str] = ""
    note: Optional[str] = ""
    expires_at: Optional[str] = ""

class SupportKeyStatusModel(BaseModel):
    key_code: str
    status: str

class SupportKeyExpiryModel(BaseModel):
    key_code: str
    expires_at: str

class SupportAssignmentCreateModel(BaseModel):
    support_key: str
    hwid: str
    student_name: Optional[str] = ""
    exam_date: str
    exam_shift: Optional[str] = ""
    subject: Optional[str] = ""
    notes: Optional[str] = ""

class SupportSetAnswerModel(BaseModel):
    hwid: str
    question_index: int
    answer: str

class LoginModel(BaseModel):
    password: str

class ChangePasswordModel(BaseModel):
    password: str

class DownloadRequestModel(BaseModel):
    full_name: str
    email: Optional[str] = ""
    note: Optional[str] = ""
    session_id: Optional[str] = ""
    system_type: Optional[str] = "SEB"


class ActivationRequestModel(BaseModel):
    hwid: str
    student_name: Optional[str] = "Học sinh"
    email: Optional[str] = ""
    machine_name: Optional[str] = ""

class ApproveActivationModel(BaseModel):
    hwid: str
    duration: str # 2h, 4h, 8h, 1d, 3d, 7d, 30d, 120d, 365d, life, custom
    custom_datetime: Optional[str] = None

class ManualKeyModel(BaseModel):
    hwid: str
    duration: str
    custom_datetime: Optional[str] = None
    name: Optional[str] = ""
    email: Optional[str] = ""
    note: Optional[str] = ""
    system_type: Optional[str] = "SEB"

class UpdateStudentInfoModel(BaseModel):
    hwid: str
    student_name: str
    email: Optional[str] = ""
    phone: Optional[str] = ""
    notes: Optional[str] = ""

class SessionLogModel(BaseModel):
    hwid: str
    student_name: Optional[str] = "Học sinh"
    machine_name: Optional[str] = ""
    event_type: str # START_EXAM, EXIT_NORMAL, EXIT_LOCKED, EXIT_DELETED, EXIT_EXPIRED
    details: Optional[str] = ""

class StudentExamSyncModel(BaseModel):
    hwid: str
    student_name: Optional[str] = "Thí sinh"
    exam_title: Optional[str] = "Bài thi trực tuyến"
    page_url: Optional[str] = ""  # URL trang học sinh đang mở trong LMS
    questions: list
    class_code: Optional[str] = ""
    subject_code: Optional[str] = ""
    proctor_email: Optional[str] = ""
    paper_code: Optional[str] = ""
    student_account: Optional[str] = ""
    campus: Optional[str] = ""
    exam_server_time: Optional[str] = ""
    remaining_time: Optional[str] = ""

class SetAnswerModel(BaseModel):
    hwid: str
    question_index: int
    answer: str

def calculate_expiration(duration: str, custom_datetime: Optional[str] = None, current_exp: Optional[datetime] = None) -> datetime:
    now = database.now_vn()
    base = current_exp if (current_exp and current_exp > now) else now

    if duration == "custom" and custom_datetime:
        dt_str = custom_datetime.replace("T", " ").strip()
        if len(dt_str) == 16:
            dt_str += ":00"
        try:
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    if duration == "-15m": return base - timedelta(minutes=15)
    elif duration == "-30m": return base - timedelta(minutes=30)
    elif duration == "-1h": return base - timedelta(hours=1)
    elif duration == "5m": return now + timedelta(minutes=5)
    elif duration == "now": return now - timedelta(seconds=10)
    elif duration == "+15m": return base + timedelta(minutes=15)
    elif duration == "+30m": return base + timedelta(minutes=30)
    elif duration == "+45m": return base + timedelta(minutes=45)
    elif duration == "+1h": return base + timedelta(hours=1)
    elif duration == "+2h": return base + timedelta(hours=2)
    elif duration == "+4h": return base + timedelta(hours=4)
    elif duration == "2h": return now + timedelta(hours=2)
    elif duration == "4h": return now + timedelta(hours=4)
    elif duration == "8h": return now + timedelta(hours=8)
    elif duration == "1d": return now + timedelta(days=1)
    elif duration == "3d": return now + timedelta(days=3)
    elif duration == "7d": return now + timedelta(days=7)
    elif duration == "30d": return now + timedelta(days=30)
    elif duration == "120d": return now + timedelta(days=120)
    elif duration == "365d": return now + timedelta(days=365)
    elif duration == "life": return now + timedelta(days=3650)
    return now + timedelta(days=30)

class ChatMessageModel(BaseModel):
    session_id: str
    sender: str
    sender_name: str
    message: str

class SettingsModel(BaseModel):
    telegram_bot_token: Optional[str] = ""
    telegram_chat_id: Optional[str] = ""
    external_download_url: Optional[str] = ""
    external_download_url_seb: Optional[str] = ""
    external_download_url_mac: Optional[str] = ""
    external_download_url_eos: Optional[str] = ""
    r2_endpoint_url: Optional[str] = ""
    r2_bucket_name: Optional[str] = ""
    r2_access_key: Optional[str] = ""
    r2_secret_key: Optional[str] = ""
    github_token: Optional[str] = ""
    github_repo: Optional[str] = ""
    github_release_tag: Optional[str] = ""

# ────────────────── Web Pages ──────────────────

@app.get("/", response_class=HTMLResponse)
async def page_index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/mock-exam", response_class=HTMLResponse)
async def page_mock_exam(request: Request):
    return templates.TemplateResponse(request=request, name="mock_exam.html")

@app.get("/login", response_class=HTMLResponse)
async def page_login(request: Request):
    if is_admin_authenticated(request):
        return RedirectResponse(url="/admin", status_code=303)
    if is_support_authenticated(request):
        return RedirectResponse(url="/support", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html")

@app.get("/support", response_class=HTMLResponse)
async def page_support(request: Request):
    if not is_support_authenticated(request):
        if not is_admin_authenticated(request):
            return RedirectResponse(url="/login?tab=support", status_code=303)
    return templates.TemplateResponse(request=request, name="support.html")

@app.get("/admin", response_class=HTMLResponse)
async def page_admin(request: Request):
    if not is_admin_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request=request, name="admin.html")

@app.get("/admin/logout")
async def admin_logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(AUTH_COOKIE_NAME)
    return response

@app.get("/api/support/logout")
async def api_support_logout():
    response = RedirectResponse(url="/login?tab=support", status_code=303)
    response.delete_cookie(SUPPORT_COOKIE_NAME)
    return response

# ────────────────── Admin Authentication API ──────────────────

@app.post("/api/admin/login")
async def api_admin_login(payload: LoginModel):
    stored_pass = database.get_setting("admin_password", "admin")
    if payload.password.strip() == stored_pass:
        token = get_admin_expected_token()
        res = JSONResponse(content={"success": True, "message": "Đăng nhập thành công!"})
        res.set_cookie(
            key=AUTH_COOKIE_NAME,
            value=token,
            httponly=True,
            max_age=86400 * 7,
            samesite="lax"
        )
        return res
    return JSONResponse(
        status_code=400,
        content={"success": False, "message": "Mật khẩu không chính xác!"}
    )

@app.post("/api/admin/change-password", dependencies=[Depends(require_admin)])
async def api_admin_change_password(payload: ChangePasswordModel):
    new_pass = payload.password.strip()
    if not new_pass or len(new_pass) < 4:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Mật khẩu phải có ít nhất 4 ký tự!"}
        )
    database.set_setting("admin_password", new_pass)
    token = hashlib.sha256(f"{new_pass}:{AUTH_SALT}".encode()).hexdigest()
    res = JSONResponse(content={"success": True, "message": "Đổi mật khẩu thành công!"})
    res.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=86400 * 7,
        samesite="lax"
    )
    return res

# ────────────────── Student Download API ──────────────────

def get_client_ip(request: Request) -> str:
    """Lấy IP thật của người dùng ngay cả khi đứng sau Cloudflare hoặc Nginx Proxy"""
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip: return cf_ip.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff: return xff.split(",")[0].strip()
    x_real = request.headers.get("x-real-ip")
    if x_real: return x_real.strip()
    return request.client.host if request.client else "127.0.0.1"

@app.post("/api/request-download")
async def api_request_download(req: DownloadRequestModel, request: Request, bg_tasks: BackgroundTasks):
    client_ip = get_client_ip(request)
    request_id = "REQ_" + uuid.uuid4().hex[:10].upper()

    row = database.create_download_request(
        request_id=request_id,
        full_name=req.full_name,
        email=req.email or "",
        note=req.note or "",
        ip_address=client_ip,
        system_type=req.system_type or "SEB"
    )

    # Gửi thông báo đến Telegram Admin
    bg_tasks.add_task(telegram_bot.notify_download_request, row)

    return {"success": True, "request_id": request_id}

@app.get("/api/check-download-status")
async def api_check_download_status(request_id: str):
    row = database.get_download_request(request_id)
    if not row:
        return {"status": "not_found"}

    if row["status"] == "approved":
        # Link tải luôn đi qua validator IP nội bộ: /api/download/stream?token=...
        token = row["download_token"]
        download_url = f"/api/download/stream?token={token}"
        return {
            "status": "approved",
            "download_url": download_url,
            "expires_at": row["token_expires_at"]
        }
    
    return {"status": row["status"]}

@app.get("/api/download/stream")
async def api_stream_local_file(token: str, request: Request):
    """
    Stream file cài đặt ~205MB (Windows) hoặc ~11MB (macOS):
    - Kiểm tra token tải đã được Admin/Telegram duyệt.
    - Hỗ trợ đổi mạng IP (ghi nhận log, không chặn 403 gây lỗi học sinh).
    - Tự động chuyển hướng (Redirect 302) đến máy chủ AWS S3 / Cloudflare R2 tốc độ cao.
    - Fallback về file cục bộ nếu có.
    """
    row = database.get_request_by_download_token(token)
    if not row:
        raise HTTPException(status_code=403, detail="Mã tải không hợp lệ hoặc đã hết hạn!")

    # 1. Kiểm tra thời hạn 24 giờ của link
    exp_str = row.get("token_expires_at")
    if exp_str:
        try:
            exp_time = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
            if database.now_vn() > exp_time:
                raise HTTPException(status_code=403, detail="Đường link tải này đã hết hạn. Vui lòng gửi yêu cầu xin duyệt lại!")
        except Exception:
            pass

    # 2. GHI NHẬN ĐỊA CHỈ IP (Audit log, không chặn 403 để học sinh đổi mạng 4G/Wi-Fi vẫn tải được bình thường)
    current_ip = get_client_ip(request)
    registered_ip = row.get("ip_address")
    if registered_ip and current_ip != registered_ip:
        print(f"[Download Audit] Token {token[:8]}... downloaded from IP {current_ip} (registered IP: {registered_ip})")

    # 3. Lấy link CDN đám mây (GitHub S3 Pre-signed hoặc Cloudflare R2)
    sys_type = row.get("system_type", "SEB") or "SEB"
    cloud_url, is_cloud = storage.generate_download_url(token, system_type=sys_type)
    if is_cloud and cloud_url:
        return RedirectResponse(url=cloud_url, status_code=302)

    # 4. Stream file từ máy chủ nếu file có trên ổ cứng cục bộ
    file_path, filename = storage.get_local_setup_file(sys_type)
    if file_path and os.path.exists(file_path):
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="application/octet-stream"
        )

    # 5. Fallback cuối cùng: thử cấp lại pre-signed URL từ GitHub Release trực tiếp
    fallback_s3 = storage.get_github_signed_asset_url(sys_type)
    if fallback_s3:
        return RedirectResponse(url=fallback_s3, status_code=302)

    raise HTTPException(status_code=404, detail="File cài đặt đang được hệ thống chuẩn bị. Vui lòng thử lại sau 1 phút hoặc liên hệ Admin!")

# ────────────────── SEB Launcher Online License API ──────────────────

@app.post("/api/request-activation")
async def api_request_activation(req: ActivationRequestModel, request: Request, bg_tasks: BackgroundTasks):
    """
    Được gọi tự động bởi SEB_Launcher trên máy học sinh.
    Gửi thông tin mã máy HWID lên Server/Telegram để Admin duyệt.
    """
    client_ip = get_client_ip(request)
    request_id = "ACT_" + uuid.uuid4().hex[:10].upper()

    row = database.create_or_update_activation_request(
        request_id=request_id,
        hwid=req.hwid,
        student_name=req.student_name or "Học sinh",
        email=req.email or "",
        machine_name=req.machine_name or "",
        ip_address=client_ip
    )

    # Nếu máy chưa được kích hoạt thì mới gửi thông báo Telegram
    if row.get("status") == "pending":
        bg_tasks.add_task(telegram_bot.notify_activation_request, row)

    return {
        "success": True,
        "status": row.get("status"),
        "message": "Đã ghi nhận yêu cầu kích hoạt mã máy."
    }

@app.get("/api/check-activation")
async def api_check_activation(hwid: str):
    """
    Được gọi định kỳ bởi SEB_Launcher để kiểm tra bản quyền Online và trạng thái Khóa khẩn cấp.
    """
    lic = database.get_license_by_hwid(hwid)
    if not lic:
        return {"status": "not_registered", "message": "Mã máy chưa được đăng ký trong hệ thống."}

    # Cập nhật thời điểm kết nối gần nhất (heartbeat)
    database.update_heartbeat(hwid)

    status = lic["status"]
    if status == "active":
        # Kiểm tra ngày hết hạn theo giờ Việt Nam (GMT+7)
        exp_str = lic["expires_at"]
        if exp_str:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
            if database.now_vn() >= exp_date:
                database.lock_license(hwid)
                return {"status": "expired", "message": "Bản quyền đã hết hạn sử dụng."}

        return {
            "status": "active",
            "license_key": lic["license_key"],
            "expires_at": lic["expires_at"],
            "server_time": database.now_vn().strftime("%Y-%m-%d %H:%M:%S")
        }

    elif status == "locked":
        return {
            "status": "locked",
            "message": "Mã máy này đã bị Quản trị viên KHÓA KHẨN CẤP. Phần mềm sẽ tự hủy."
        }

    return {"status": "pending", "message": "Đang chờ Quản trị viên duyệt qua Telegram/Web..."}

@app.get("/api/ping")
@app.get("/api/health")
async def api_ping():
    return {
        "status": "online",
        "server_time": database.now_vn().strftime("%Y-%m-%d %H:%M:%S"),
        "service": "SEB Licensing & Portal"
    }

@app.post("/api/log-session")
async def api_log_session(payload: SessionLogModel, request: Request):
    client_ip = get_client_ip(request)
    hwid = payload.hwid.strip()
    name = payload.student_name.strip() if payload.student_name else "Học sinh"
    mach = payload.machine_name.strip() if payload.machine_name else "Unknown"
    evt = payload.event_type.strip()
    details = payload.details.strip() if payload.details else ""

    log_entry = database.log_access_event(hwid, name, mach, client_ip, evt, details)

    # Đánh dấu ca thi kết thúc khi học sinh thoát/nộp bài và tự động lưu đề để xem lại / tải về trong 24h
    if evt in ("EXIT_NORMAL", "EXIT_LOCKED", "EXIT_DELETED", "EXIT_EXPIRED"):
        try:
            database.update_live_exam_session_status(hwid, "finished")
            database.archive_and_purge_exam_session(hwid, purge_questions=False)
        except Exception:
            pass

    # Gửi thông báo tức thì lên Telegram cho Admin nắm được
    try:
        evt_labels = {
            "START_EXAM": "🟢 <b>HỌC SINH BẮT ĐẦU VÀO THI</b>",
            "EXIT_NORMAL": "🏁 <b>HỌC SINH ĐÃ THOÁT / NỘP BÀI THI</b>",
            "EXIT_LOCKED": "🔒 <b>MÁY BỊ KHÓA TỪ XA VÀ BUỘC THOÁT</b>",
            "EXIT_DELETED": "🗑️ <b>BẢN QUYỀN BỊ XÓA VÀ BUỘC THOÁT</b>",
            "EXIT_EXPIRED": "⌛ <b>HẾT HẠN SỬ DỤNG VÀ BUỘC THOÁT</b>"
        }
        title = evt_labels.get(evt, f"ℹ️ <b>SỰ KIỆN: {evt}</b>")
        time_vn = database.now_vn().strftime("%H:%M:%S %d/%m/%Y")
        tele_msg = (
            f"{title}\n\n"
            f"👤 <b>Học sinh:</b> {name}\n"
            f"💻 <b>Máy:</b> {mach} (IP: <code>{client_ip}</code>)\n"
            f"🔑 <b>HWID:</b> <code>{hwid[:16]}...</code>\n"
            f"📝 <b>Chi tiết:</b> {details}\n"
            f"⏰ <b>Thời gian:</b> {time_vn}"
        )
        asyncio.create_task(telegram_bot.notify_admin_custom(tele_msg))
    except Exception:
        pass

    return {"success": True, "log": log_entry}

# ────────────────── Admin Management API ──────────────────

@app.get("/api/admin/access-logs", dependencies=[Depends(require_admin)])
async def api_admin_access_logs(limit: int = 300, hwid: Optional[str] = None, target_date: Optional[str] = None):
    dates = database.list_access_log_dates()
    logs = database.list_access_logs(limit=limit, hwid=hwid, target_date=target_date)
    return {
        "logs": logs,
        "dates": dates,
        "selected_date": target_date or ""
    }

@app.post("/api/admin/backup-telegram", dependencies=[Depends(require_admin)])
async def api_admin_backup_telegram():
    res = database.send_backup_to_telegram()
    return res

@app.post("/api/admin/clear-access-logs", dependencies=[Depends(require_admin)])
async def api_admin_clear_access_logs():
    success = database.clear_access_logs()
    return {"success": success}

@app.get("/api/admin/stats", dependencies=[Depends(require_admin)])
async def api_admin_stats():
    dls = database.list_download_requests(100)
    lics = database.list_licenses(200)

    pending_dls = sum(1 for d in dls if d["status"] == "pending")
    pending_lics = sum(1 for l in lics if l["status"] == "pending")
    active_lics = sum(1 for l in lics if l["status"] == "active")
    locked_lics = sum(1 for l in lics if l["status"] == "locked")

    return {
        "pending_downloads": pending_dls,
        "pending_activations": pending_lics,
        "active_licenses": active_lics,
        "locked_licenses": locked_lics,
        "total_licenses": len(lics)
    }

@app.get("/api/admin/download-requests", dependencies=[Depends(require_admin)])
async def api_admin_list_downloads(system_type: Optional[str] = None):
    return database.list_download_requests(50, system_type=system_type)

@app.post("/api/admin/approve-download", dependencies=[Depends(require_admin)])
async def api_admin_approve_download(payload: dict):
    req_id = payload.get("request_id")
    token = str(uuid.uuid4())
    expires_at = (database.now_vn() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    success = database.approve_download_request(req_id, token, expires_at)
    if success:
        try:
            row = database.get_download_request(req_id)
            if row:
                st_name = row.get("full_name", "Học sinh")
                sys_t = (row.get("system_type") or "SEB").upper()
                os_lbl = "🍎 macOS" if sys_t in ["MAC", "MACOS", "SEB_MAC"] else "🪟 Windows"
                tele_msg = (
                    f"✅ <b>ĐÃ DUYỆT TẢI PHẦN MỀM THI (TỪ TRANG ADMIN)</b>\n\n"
                    f"👤 <b>Học sinh:</b> {st_name}\n"
                    f"💻 <b>Hệ điều hành:</b> {os_lbl}\n"
                    f"⏳ <b>Hạn link tải:</b> 30 phút (đến {expires_at})\n"
                    f"ℹ️ <i>Học sinh đã có thể bấm Tải xuống ngay trên web!</i>"
                )
                asyncio.create_task(telegram_bot.notify_admin_custom(tele_msg))
        except Exception:
            pass
    return {"success": success}

@app.post("/api/admin/reject-download", dependencies=[Depends(require_admin)])
async def api_admin_reject_download(payload: dict):
    req_id = payload.get("request_id")
    success = database.reject_download_request(req_id)
    if success:
        try:
            row = database.get_download_request(req_id)
            if row:
                st_name = row.get("full_name", "Học sinh")
                tele_msg = (
                    f"❌ <b>ĐÃ TỪ CHỐI YÊU CẦU TẢI (TỪ TRANG ADMIN)</b>\n\n"
                    f"👤 <b>Học sinh:</b> {st_name}"
                )
                asyncio.create_task(telegram_bot.notify_admin_custom(tele_msg))
        except Exception:
            pass
    return {"success": success}

@app.get("/api/admin/licenses", dependencies=[Depends(require_admin)])
async def api_admin_list_licenses(system_type: Optional[str] = None):
    licenses = database.list_licenses(200)
    if system_type:
        target = system_type.upper().strip()
        if target == 'SEB':
            licenses = [l for l in licenses if (l.get("system_type") or "SEB").upper() in ('SEB', 'WINDOWS', 'MACOS', 'MAC', 'WIN', 'SEB_MAC')]
        elif target in ('EOS', 'PEA'):
            licenses = [l for l in licenses if (l.get("system_type") or "").upper() in ('EOS', 'PEA')]
        else:
            licenses = [l for l in licenses if (l.get("system_type") or "SEB").upper() == target]
    return licenses

@app.post("/api/admin/approve-activation", dependencies=[Depends(require_admin)])
async def api_admin_approve_activation(payload: ApproveActivationModel):
    hwid = payload.hwid.strip()
    duration = payload.duration
    lic = database.get_license_by_hwid(hwid)
    current_exp = None
    if lic and lic.get("expires_at"):
        try:
            current_exp = datetime.strptime(lic["expires_at"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    exp_date = calculate_expiration(duration, payload.custom_datetime, current_exp)
    exp_str = exp_date.strftime("%Y-%m-%d %H:%M:%S")
    license_key = crypto_engine.generate_license(hwid, exp_str)

    dur_label = duration
    if duration == "custom": dur_label = f"Hết hạn {exp_str}"
    elif duration == "-15m": dur_label = f"Rút ngắn -15 Phút (đến {exp_str})"
    elif duration == "-30m": dur_label = f"Rút ngắn -30 Phút (đến {exp_str})"
    elif duration == "-1h": dur_label = f"Rút ngắn -1 Giờ (đến {exp_str})"
    elif duration == "5m": dur_label = f"Thu bài sau 5 phút (đến {exp_str})"
    elif duration == "now": dur_label = "Thu hồi / Hết hạn ngay lập tức"
    elif duration == "+15m": dur_label = f"+15 Phút (đến {exp_str})"
    elif duration == "+30m": dur_label = f"+30 Phút (đến {exp_str})"
    elif duration == "+45m": dur_label = f"+45 Phút (đến {exp_str})"
    elif duration == "+1h": dur_label = f"+1 Giờ (đến {exp_str})"
    elif duration == "+2h": dur_label = f"+2 Giờ (đến {exp_str})"
    elif duration == "+4h": dur_label = f"+4 Giờ (đến {exp_str})"
    elif duration == "2h": dur_label = "2 Giờ"
    elif duration == "4h": dur_label = "4 Giờ"
    elif duration == "8h": dur_label = "8 Giờ"
    elif duration == "1d": dur_label = "1 Ngày"
    elif duration == "3d": dur_label = "3 Ngày"
    elif duration == "7d": dur_label = "7 Ngày"
    elif duration == "30d": dur_label = "30 Ngày"
    elif duration == "120d": dur_label = "1 Học Kỳ"
    elif duration == "365d": dur_label = "1 Năm"
    elif duration == "life": dur_label = "Vĩnh Viễn"

    success = database.approve_license(hwid, license_key, exp_str, dur_label)

    # Gửi thông báo Telegram cập nhật hạn
    try:
        st_name = lic.get("student_name", "Học sinh") if lic else "Học sinh"
        tele_msg = (
            f"⏱️ <b>ĐÃ CẬP NHẬT / GIA HẠN THỜI GIAN THI</b>\n\n"
            f"👤 <b>Học sinh:</b> {st_name}\n"
            f"🔑 <b>HWID:</b> <code>{hwid[:16]}...</code>\n"
            f"⏳ <b>Hạn mới:</b> <b>{exp_str}</b> ({dur_label})\n"
            f"ℹ️ <i>Mã mới đã được ký và sẽ tự động nhúng vào máy học sinh!</i>"
        )
        asyncio.create_task(telegram_bot.notify_admin_custom(tele_msg))
    except Exception:
        pass

    return {"success": success, "license_key": license_key, "expires_at": exp_str, "duration_label": dur_label}

@app.post("/api/admin/lock-license", dependencies=[Depends(require_admin)])
async def api_admin_lock_license(payload: dict):
    hwid = payload.get("hwid", "")
    success = database.lock_license(hwid)
    return {"success": success}

@app.post("/api/admin/unlock-license", dependencies=[Depends(require_admin)])
async def api_admin_unlock_license(payload: dict):
    hwid = payload.get("hwid", "")
    success = database.unlock_license(hwid)
    return {"success": success}

@app.post("/api/admin/delete-license", dependencies=[Depends(require_admin)])
async def api_admin_delete_license(payload: dict):
    hwid = payload.get("hwid", "")
    success = database.delete_license(hwid)
    return {"success": success}

@app.post("/api/admin/update-student-info", dependencies=[Depends(require_admin)])
async def api_admin_update_student_info(payload: UpdateStudentInfoModel):
    hwid = payload.hwid.strip()
    if not hwid:
        return JSONResponse(status_code=400, content={"success": False, "message": "HWID không được để trống!"})
    success = database.update_license_info(
        hwid=hwid,
        student_name=payload.student_name,
        email=payload.email or "",
        phone=payload.phone or "",
        notes=payload.notes or ""
    )
    return {"success": success, "message": "Đã cập nhật thông tin học sinh thành công!"}

@app.post("/api/admin/manual-generate-key", dependencies=[Depends(require_admin)])
async def api_admin_manual_generate_key(payload: ManualKeyModel):
    hwid = payload.hwid.strip()
    if not hwid:
        return JSONResponse(status_code=400, content={"success": False, "message": "Mã máy tính (HWID) không được để trống!"})

    name = payload.name.strip() or "Học sinh thủ công"
    email = payload.email.strip() if payload.email else ""
    note = payload.note.strip() if payload.note else "Cấp thủ công"

    exp_date = calculate_expiration(payload.duration, payload.custom_datetime)
    exp_str = exp_date.strftime("%Y-%m-%d %H:%M:%S")
    license_key = crypto_engine.generate_license(hwid, exp_str)
    req_id = "MANUAL_" + uuid.uuid4().hex[:8].upper()

    dur_label = payload.duration
    if payload.duration == "custom": dur_label = f"Hết hạn {exp_str}"
    elif payload.duration == "2h": dur_label = "2 Giờ"
    elif payload.duration == "4h": dur_label = "4 Giờ"
    elif payload.duration == "8h": dur_label = "8 Giờ"
    elif payload.duration == "1d": dur_label = "1 Ngày"
    elif payload.duration == "3d": dur_label = "3 Ngày"
    elif payload.duration == "7d": dur_label = "7 Ngày"
    elif payload.duration == "30d": dur_label = "30 Ngày"
    elif payload.duration == "120d": dur_label = "1 Học Kỳ"
    elif payload.duration == "365d": dur_label = "1 Năm"
    elif payload.duration == "life": dur_label = "Vĩnh Viễn"

    sys_type = (payload.system_type or "SEB").upper()
    database.create_or_update_activation_request(req_id, hwid, name, email, note, "127.0.0.1", system_type=sys_type)
    database.approve_license(hwid, license_key, exp_str, dur_label)

    return {
        "success": True, 
        "license_key": license_key, 
        "expires_at": exp_str,
        "duration_label": dur_label,
        "student_name": name,
        "email": email,
        "hwid": hwid
    }

@app.get("/api/admin/settings", dependencies=[Depends(require_admin)])
async def api_admin_get_settings():
    return database.get_all_settings()

@app.post("/api/admin/settings", dependencies=[Depends(require_admin)])
async def api_admin_save_settings(payload: SettingsModel):
    for k, v in payload.dict().items():
        if v is not None:
            database.set_setting(k, v)
    return {"success": True}

@app.post("/api/admin/test-telegram", dependencies=[Depends(require_admin)])
async def api_admin_test_telegram():
    token, chat_id, _ = telegram_bot.get_bot_credentials()
    if not token or not chat_id:
        return {"success": False, "message": "Chưa điền Token hoặc Chat ID"}

    res = await telegram_bot.send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": "🎉 <b>KẾT NỐI TELEGRAM BOT THÀNH CÔNG!</b>\n\nBạn sẽ nhận được thông báo xin cấp quyền thi trực tiếp tại đây.",
        "parse_mode": "HTML"
    })
    return {"success": res is not None}

# ────────────────── Backup & Restore API ──────────────────

@app.get("/api/admin/backup-export", dependencies=[Depends(require_admin)])
async def api_admin_backup_export():
    """Xuất toàn bộ database thành JSON để admin tải về lưu trữ"""
    data = database.export_all_data()
    now_str = database.now_vn().strftime("%Y%m%d_%H%M%S")
    filename = f"seb_database_backup_{now_str}.json"
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.post("/api/admin/backup-import", dependencies=[Depends(require_admin)])
async def api_admin_backup_import(payload: Dict[str, Any]):
    """Nhập dữ liệu từ file backup JSON vào database"""
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Dữ liệu JSON không đúng định dạng!")
    stats = database.import_all_data(payload, overwrite=True)
    return {"success": True, "stats": stats}

@app.post("/api/admin/restore-seed", dependencies=[Depends(require_admin)])
async def api_admin_restore_seed():
    """Khôi phục lại toàn bộ danh sách key và máy lịch sử gốc từ seed_data.json"""
    seed_file = database.SEED_FILE_PATH
    if not os.path.exists(seed_file):
        raise HTTPException(status_code=404, detail="Không tìm thấy file seed_data.json gốc!")
    import json
    with open(seed_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    stats = database.import_all_data(data, overwrite=True)
    return {"success": True, "stats": stats}

# ────────────────── Live Chat & Client IP API ──────────────────

@app.get("/api/my-ip")
async def api_get_my_ip(request: Request):
    """Trả về địa chỉ IP mạng thật của client hiện tại"""
    return {"ip": get_client_ip(request)}

@app.get("/api/chat/messages")
async def api_get_chat_messages(session_id: str):
    return database.get_chat_messages(session_id)

@app.post("/api/chat/send")
async def api_send_chat_message(msg: ChatMessageModel, request: Request):
    client_ip = get_client_ip(request)
    res = database.add_chat_message(
        session_id=msg.session_id,
        sender=msg.sender,
        sender_name=msg.sender_name,
        message=msg.message,
        ip_address=client_ip
    )
    return {"success": True, "data": res}

@app.get("/api/admin/chat-sessions", dependencies=[Depends(require_admin)])
async def api_admin_chat_sessions():
    return database.list_active_chat_sessions()

# ────────────────── Live Exam Sync & Support API ──────────────────

@app.post("/api/exam/sync")
async def api_exam_sync(payload: StudentExamSyncModel):
    """Client thí sinh đẩy câu hỏi lên và nhận về danh sách đáp án mới nhất"""
    sync_result = database.sync_student_exam_data(
        hwid=payload.hwid,
        student_name=payload.student_name or "Thí sinh",
        exam_title=payload.exam_title or "Bài thi trực tuyến",
        page_url=payload.page_url or "",
        questions=payload.questions,
        return_details=True,
        remaining_time=payload.remaining_time or "",
        exam_server_time=payload.exam_server_time or "",
        subject_code=payload.subject_code or "",
        class_code=payload.class_code or "",
        campus=payload.campus or ""
    )
    if isinstance(sync_result, tuple):
        if len(sync_result) == 3:
            answers, should_reset, auto_fill = sync_result
        else:
            answers, should_reset = sync_result
            auto_fill = False
    else:
        answers = sync_result
        should_reset = False
        auto_fill = False

    return {
        "success": True,
        "support_answers": answers,
        "should_reset_cache": should_reset,
        "auto_fill_all": auto_fill
    }

@app.get("/api/exam/sync-answers")
async def api_exam_sync_answers(hwid: str):
    """Client poll để nhận đáp án hỗ trợ mới nhất từ Admin (không cần auth)"""
    session = database.get_live_exam_session(hwid)
    should_reset = False
    auto_fill = False
    if session:
        st = (session.get("status") or "").strip().lower()
        if st == "reset_requested":
            should_reset = True
            database.update_live_exam_session_status(hwid, "active")
        if session.get("auto_fill_requested") == 1:
            auto_fill = True

    questions = database.get_live_exam_questions(hwid)
    support_answers = {}
    for q in questions:
        if q.get("support_answer"):
            support_answers[str(q["question_index"])] = q["support_answer"]
    return {
        "success": True,
        "support_answers": support_answers,
        "should_reset_cache": should_reset,
        "auto_fill_all": auto_fill
    }

@app.post("/api/admin/trigger-auto-fill/{hwid}", dependencies=[Depends(require_admin)])
async def api_admin_trigger_auto_fill(hwid: str):
    """Admin yêu cầu máy thí sinh tự động điền toàn bộ đáp án hỗ trợ đã có vào bài thi"""
    database.trigger_auto_fill_for_session(hwid)
    return {"success": True, "message": "Đã kích hoạt lệnh tự động điền đáp án cho thí sinh!"}

@app.post("/api/exam/ack-auto-fill")
async def api_exam_ack_auto_fill(payload: Dict[str, Any]):
    """Client thí sinh xác nhận đã tự động điền đáp án thành công"""
    hwid = (payload.get("hwid") or "").strip()
    if hwid:
        database.ack_auto_fill_for_session(hwid)
    return {"success": True}

@app.get("/api/admin/exam-sessions", dependencies=[Depends(require_admin)])
async def api_admin_get_exam_sessions():
    """Lấy danh sách các thí sinh đang trong ca thi"""
    return database.list_live_exam_sessions()

@app.get("/api/admin/seb-sessions", dependencies=[Depends(require_admin)])
async def api_admin_get_seb_sessions():
    """Lấy danh sách các phiên thi chạy qua hệ thống SEB Browser (tất cả các đề Moodle / LMS / Thi trực tuyến)"""
    all_sessions = database.list_live_exam_sessions()
    seb_sessions = [
        s for s in all_sessions 
        if not any(k in (s.get("exam_title") or "").upper() for k in ["EOS", "PEA"])
    ]
    return {"success": True, "system": "SEB", "count": len(seb_sessions), "sessions": seb_sessions}

@app.get("/api/admin/fpt-sessions", dependencies=[Depends(require_admin)])
async def api_admin_get_fpt_sessions():
    """Lấy danh sách các ca thi EOS (Trắc nghiệm) và PEA (Thực hành C/Java/C#) của FPT"""
    all_sessions = database.list_live_exam_sessions()
    fpt_sessions = [
        s for s in all_sessions 
        if any(k in (s.get("exam_title") or "").upper() for k in ["EOS", "PEA", "PRJ", "PRF", "PRO", "SPK", "TRẮC NGHIỆM", "THỰC HÀNH"])
    ]
    return {"success": True, "system": "EOS_PEA", "count": len(fpt_sessions), "sessions": fpt_sessions}

@app.get("/api/admin/exam-questions/{hwid}", dependencies=[Depends(require_admin)])
async def api_admin_get_exam_questions(hwid: str, v: str = ""):
    """Lấy toàn bộ câu hỏi, ảnh và đáp án của 1 thí sinh cụ thể (hỗ trợ version check giảm 99% bandwidth)"""
    cur_v = database.get_exam_questions_version(hwid)
    if v and v == cur_v:
        return JSONResponse(content={"status": "unchanged", "version": cur_v}, headers={"Cache-Control": "no-cache"})
    questions = database.get_live_exam_questions(hwid)
    return JSONResponse(
        content={"status": "ok", "version": cur_v, "questions": questions},
        headers={"Cache-Control": "no-cache"}
    )

@app.post("/api/admin/archive-session/{hwid}", dependencies=[Depends(require_admin)])
async def api_admin_archive_session(hwid: str):
    """Admin chủ động đóng gói ca thi thành file ZIP source và dọn dẹp câu hỏi trong DB"""
    res = database.archive_and_purge_exam_session(hwid, purge_questions=True)
    if not res:
        raise HTTPException(status_code=404, detail="Không tìm thấy ca thi hoặc ca thi chưa có câu hỏi")
    return res

@app.post("/api/admin/reset-session/{hwid}", dependencies=[Depends(require_admin)])
async def api_admin_reset_session(hwid: str):
    """Admin bấm nút Bắt Đầu Đề Mới: Tự động đóng gói lưu trữ đề cũ và làm sạch câu hỏi chuẩn bị cho đề tiếp theo"""
    return database.reset_and_archive_exam_session(hwid)

@app.get("/api/admin/archived-sources", dependencies=[Depends(require_admin)])
async def api_admin_get_archived_sources():
    """Lấy danh sách các file ZIP source đề thi đã lưu trữ"""
    return database.list_archived_exam_sources()

@app.get("/api/admin/download-archive/{filename}", dependencies=[Depends(require_admin)])
async def api_admin_download_archive(filename: str):
    """Tải file ZIP source đề thi đã lưu trữ"""
    import os
    safe_name = os.path.basename(filename)
    file_path = os.path.join(os.path.dirname(__file__), "data", "exam_archives", safe_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File lưu trữ không tồn tại hoặc đã quá 24h")
    return FileResponse(file_path, filename=safe_name, media_type="application/zip")

@app.get("/api/admin/archived-exam-questions/{filename}", dependencies=[Depends(require_admin)])
async def api_admin_get_archived_exam_questions(filename: str):
    """Admin xem lại toàn bộ câu hỏi, ảnh và đáp án của một bài thi đã hoàn thành trong 24h"""
    import os, zipfile, json
    safe_name = os.path.basename(filename)
    file_path = os.path.join(os.path.dirname(__file__), "data", "exam_archives", safe_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File lưu trữ không tồn tại hoặc đã quá 24h")

    try:
        with zipfile.ZipFile(file_path, "r") as z:
            if "questions.json" not in z.namelist():
                raise HTTPException(status_code=400, detail="Không tìm thấy questions.json trong file lưu trữ")
            q_data = json.loads(z.read("questions.json").decode("utf-8"))
            info_txt = z.read("info.txt").decode("utf-8") if "info.txt" in z.namelist() else ""
            return {
                "status": "ok",
                "filename": safe_name,
                "info": info_txt,
                "questions": q_data
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi đọc file lưu trữ: {str(e)}")

@app.post("/api/admin/exam-set-answer", dependencies=[Depends(require_admin)])
async def api_admin_set_exam_answer(payload: SetAnswerModel):
    """Support bấm nút đáp án trên Web -> Ghi nhận và đồng bộ tức thì"""
    success = database.set_question_support_answer(
        hwid=payload.hwid,
        question_index=payload.question_index,
        support_answer=payload.answer
    )
    return {"success": success}

@app.get("/api/admin/generate-pea-source/{hwid}", dependencies=[Depends(require_admin)])
async def api_admin_generate_pea_source(hwid: str):
    """Tạo mã nguồn giải mẫu C / C++ / Java / C# chuẩn xác cho bài thi thực hành PEA"""
    session = database.get_live_exam_session(hwid) if hasattr(database, 'get_live_exam_session') else None
    title = (session.get("exam_title") if session else "PEA Code") or "PEA Code"
    is_java = "JAVA" in title.upper() or "THOI_MA" in title or True

    if is_java:
        pea_code_template = f"""/*
 *  FPT UNIVERSITY - PEA JAVA PRACTICAL EXAM SOLUTION
 *  Exam: {title}
 *  Class: MyString implements IString
 */
package src;

public class MyString implements IString {{

    @Override
    public int f1(String str) {{
        // Yêu cầu f1: Đếm số lượng phần tử / điều kiện chuỗi theo đề bài
        if (str == null || str.isEmpty()) return 0;
        int count = 0;
        for (char c : str.toCharArray()) {{
            if (Character.isDigit(c)) {{
                count++;
            }}
        }}
        return count;
    }}

    @Override
    public String f2(String str) {{
        // Yêu cầu f2: Xử lý chuỗi (chuyển đổi, đảo chuỗi, lọc từ theo đề bài)
        if (str == null || str.isEmpty()) return str;
        String[] words = str.trim().split("\\\\s+");
        StringBuilder sb = new StringBuilder();
        for (String w : words) {{
            if (w.length() > 0) {{
                sb.append(Character.toUpperCase(w.charAt(0)))
                  .append(w.substring(1).toLowerCase())
                  .append(" ");
            }}
        }}
        return sb.toString().trim();
    }}
}}
"""
        return {
            "success": True,
            "filename": "MyString.java",
            "code": pea_code_template
        }
    else:
        pea_code_template = f"""/*
 *  FPT UNIVERSITY - PEA C/C++ PRACTICAL EXAM SOLUTION
 *  Exam: {title}
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

int main() {{
    char str[500];
    if (fgets(str, sizeof(str), stdin)) {{
        str[strcspn(str, "\\n")] = 0;
        printf("OUTPUT:\\n%s\\n", str);
    }}
    return 0;
}}
"""
        return {
            "success": True,
            "filename": "PEA_Solution.c",
            "code": pea_code_template
        }

@app.get("/api/admin/copy-answers/{hwid}", dependencies=[Depends(require_admin)])
async def api_admin_copy_answers(hwid: str):
    """Lấy danh sách đáp án định dạng văn bản để copy nhanh sang tệp tạm"""
    questions = database.get_live_exam_questions(hwid)
    lines = []
    for q in questions:
        idx = q.get("question_index", 0) + 1
        ans = q.get("support_answer") or q.get("current_answer") or "Chưa chọn"
        lines.append(f"Câu {idx:02d}: {ans}")
    return {"success": True, "formatted_text": "\n".join(lines)}

@app.get("/api/admin/pea/download-template/{hwid}")
async def api_admin_pea_download_template(hwid: str):
    """Tải file ZIP mẫu dự án (Starter Project Template) của bài thi thực hành PEA"""
    candidate_files = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_exams", "PEA_peaData_dump.bin"),
        r"D:\Project\Tools FPT\tools\PEA_peaData_dump.bin"
    ]
    zip_data = None
    for fp in candidate_files:
        if os.path.exists(fp):
            with open(fp, "rb") as fh:
                raw_data = fh.read()
            zip_data = exam_parser.extract_pea_starter_zip(raw_data)
            if zip_data:
                break

    if not zip_data:
        return Response(content=b"ZIP Template not found", status_code=404)

    return Response(
        content=zip_data,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=PEA_Starter_Template_{hwid[:8]}.zip"}
    )

@app.get("/api/admin/pea/paper-image/{hwid}")
async def api_admin_pea_paper_image(hwid: str):
    """Tải/Hiển thị ảnh đề thi dài độ phân giải cao của bài thi thực hành PEA"""
    candidate_files = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_exams", "PEA_peaData_dump.bin"),
        r"D:\Project\Tools FPT\tools\PEA_peaData_dump.bin"
    ]
    img_bytes = None
    for fp in candidate_files:
        if os.path.exists(fp):
            with open(fp, "rb") as fh:
                raw_data = fh.read()
            img_bytes = exam_parser.extract_pea_image(raw_data)
            if img_bytes:
                break

    if not img_bytes:
        return Response(content=b"Paper Image not found", status_code=404)

    return Response(
        content=img_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Length": str(len(img_bytes))
        }
    )

@app.post("/api/admin/eos/load-folder-exams", dependencies=[Depends(require_admin)])
async def api_admin_load_folder_exams():
    """Tự động quét thư mục sample_exams đính kèm để nạp tất cả các đề thi .dat/.bin có sẵn bằng bộ de-serializer chuẩn"""
    loaded_papers = []

    candidate_folders = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_exams"),
        r"D:\Project\Tools FPT\tools",
    ]

    scanned_paths = set()
    try:
        for base_folder in candidate_folders:
            if not os.path.exists(base_folder):
                continue
            for root, dirs, files in os.walk(base_folder):
                for f in files:
                    if f.endswith(".dat") or f.endswith(".bin"):
                        fp = os.path.join(root, f)
                        if fp in scanned_paths:
                            continue
                        scanned_paths.add(fp)

                        sz = os.path.getsize(fp)
                        if sz > 2000:
                            file_name = os.path.basename(fp)
                            hwid = "FOLDER_" + hashlib.md5(fp.encode()).hexdigest()[:12].upper()

                            parsed = exam_parser.parse_full_exam_file(fp)
                            exam_title = parsed.get("exam_title", f"EOS/PEA File: {file_name}")
                            questions = parsed.get("questions", [])

                            if questions:
                                database.sync_student_exam_data(
                                    hwid=hwid,
                                    student_name=f"Thí Sinh Đề {file_name}",
                                    exam_title=exam_title,
                                    questions=questions
                                )
                                loaded_papers.append({"file_name": file_name, "hwid": hwid, "questions_count": len(questions)})

        if not loaded_papers:
            return {"success": False, "message": "Không tìm thấy file đề thi nào trong các thư mục mẫu!"}

        return {"success": True, "count": len(loaded_papers), "loaded_papers": loaded_papers}
    except Exception as err:
        return {"success": False, "message": f"Lỗi đọc file đề thi: {str(err)}"}


# Admin tạo và đẩy đề thủ công xuống máy học sinh
class PushExamModel(BaseModel):
    hwid: str
    student_name: Optional[str] = "Thí sinh"
    exam_title: Optional[str] = "Bài thi trực tuyến"
    questions: list  # list of {question_text, question_type, options: [str], correct_answer: str}

@app.post("/api/admin/push-exam", dependencies=[Depends(require_admin)])
async def api_admin_push_exam(payload: PushExamModel):
    """Admin tạo đề thủ công và đẩy vào session của học sinh (HWID bất kỳ)"""
    formatted = []
    for idx, q in enumerate(payload.questions):
        opts = q.get("options", [])
        ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        options_obj = [{"label": ALPHA[i] if i < len(ALPHA) else str(i+1), "text": str(o), "image_base64": ""} for i, o in enumerate(opts)]
        formatted.append({
            "question_index": idx,
            "question_type": q.get("question_type", "radio"),
            "question_text": q.get("question_text", ""),
            "options": options_obj,
            "image_base64": "",
            "selected_answer": "",
            "support_answer": q.get("correct_answer", ""),
        })

    answers = database.sync_student_exam_data(
        hwid=payload.hwid,
        student_name=payload.student_name,
        exam_title=payload.exam_title,
        questions=formatted
    )
    # Nếu có đáp án đúng thì set luôn support_answer
    for idx, q in enumerate(formatted):
        if q.get("support_answer"):
            database.set_question_support_answer(
                hwid=payload.hwid,
                question_index=idx,
                support_answer=q["support_answer"]
            )
    return {"success": True, "pushed": len(formatted)}

@app.delete("/api/admin/exam-session/{hwid}", dependencies=[Depends(require_admin)])
async def api_admin_delete_exam_session(hwid: str):
    """Xoá sạch phiên thi của một học sinh"""
    try:
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM live_exam_questions WHERE hwid=?", (hwid,))
        c.execute("DELETE FROM live_exam_sessions WHERE hwid=?", (hwid,))
        conn.commit()
        conn.close()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ────────────────── Support API Endpoints ──────────────────

@app.post("/api/support/login")
async def api_support_login(payload: SupportLoginModel):
    key = payload.key_code.strip().upper()
    if not database.verify_support_key_checksum(key):
        return JSONResponse(status_code=400, content={"success": False, "message": "Mã Key sai định dạng hoặc mã kiểm tra (checksum) không hợp lệ!"})
    
    k = database.get_support_key(key)
    if not k:
        return JSONResponse(status_code=404, content={"success": False, "message": "Mã Key Support không tồn tại trên hệ thống!"})
    
    if k.get("status") == "suspended":
        return JSONResponse(status_code=403, content={"success": False, "message": "Key của bạn đang bị TẠM KHÓA bởi Quản trị viên!"})
    if k.get("status") == "locked":
        return JSONResponse(status_code=403, content={"success": False, "message": "Key của bạn đã bị KHÓA vĩnh viễn!"})
    
    exp = k.get("expires_at")
    if exp:
        today_str = database.now_vn().strftime("%Y-%m-%d")
        if today_str > exp:
            return JSONResponse(status_code=403, content={"success": False, "message": f"Mã Key đã hết hạn sử dụng vào ngày {exp}!"})
            
    database.update_support_key_last_login(key)
    token = create_support_session_token(key)
    
    res = JSONResponse(content={
        "success": True,
        "message": f"Xin chào {k.get('assigned_name')}! Đăng nhập thành công.",
        "assigned_name": k.get("assigned_name"),
        "key_code": key,
        "redirect": "/support"
    })
    res.set_cookie(
        key=SUPPORT_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=86400 * 3,
        samesite="lax"
    )
    return res

@app.get("/api/support/me")
async def api_support_me(current_support: Dict[str, Any] = Depends(get_current_support)):
    return {
        "success": True,
        "key_code": current_support["key_code"],
        "assigned_name": current_support["assigned_name"],
        "status": current_support["status"],
        "today": database.now_vn().strftime("%Y-%m-%d"),
        "expires_at": current_support.get("expires_at") or "Vĩnh viễn"
    }

@app.get("/api/support/exams")
async def api_support_get_exams(current_support: Dict[str, Any] = Depends(get_current_support)):
    """Chỉ trả về các ca thi và máy được Admin phân công cho Support này trong ngày HÔM NAY"""
    today_vn = database.now_vn().strftime("%Y-%m-%d")
    result = database.get_support_assigned_exams_for_date(current_support["key_code"], today_vn)
    return result

@app.get("/api/support/exam-questions/{hwid}")
async def api_support_get_questions(hwid: str, current_support: Dict[str, Any] = Depends(get_current_support)):
    """Lấy danh sách câu hỏi của thí sinh. Kiểm tra nghiêm ngặt quyền gán máy trong ngày!"""
    today_vn = database.now_vn().strftime("%Y-%m-%d")
    if not database.is_hwid_assigned_to_support(current_support["key_code"], hwid, today_vn):
        raise HTTPException(status_code=403, detail="Bạn không được phân công hỗ trợ máy này trong ngày hôm nay!")
    return database.get_live_exam_questions(hwid)

@app.post("/api/support/exam-set-answer")
async def api_support_set_answer(payload: SupportSetAnswerModel, current_support: Dict[str, Any] = Depends(get_current_support)):
    """Support chọn đáp án cho thí sinh được phân công"""
    today_vn = database.now_vn().strftime("%Y-%m-%d")
    if not database.is_hwid_assigned_to_support(current_support["key_code"], payload.hwid, today_vn):
        raise HTTPException(status_code=403, detail="Bạn không được phân công hỗ trợ máy này trong ngày hôm nay!")
    
    success = database.set_question_support_answer(
        hwid=payload.hwid,
        question_index=payload.question_index,
        support_answer=payload.answer
    )
    return {"success": success}

@app.post("/api/support/reset-session/{hwid}")
async def api_support_reset_session(hwid: str, current_support: Dict[str, Any] = Depends(get_current_support)):
    """Support bấm nút Bắt Đầu Đề Mới cho thí sinh được phân công: Lưu trữ đề cũ và làm sạch câu hỏi cho đề mới"""
    today_vn = database.now_vn().strftime("%Y-%m-%d")
    if not database.is_hwid_assigned_to_support(current_support["key_code"], hwid, today_vn):
        raise HTTPException(status_code=403, detail="Bạn không được phân công hỗ trợ máy này trong ngày hôm nay!")
    res = database.reset_and_archive_exam_session(hwid)
    return res

# ────────────────── Admin Support & Assignment Management APIs ──────────────────

@app.get("/api/admin/support-keys", dependencies=[Depends(require_admin)])
async def api_admin_list_support_keys():
    keys = database.list_support_keys()
    return {"success": True, "keys": keys}

@app.post("/api/admin/support-keys", dependencies=[Depends(require_admin)])
async def api_admin_create_support_key(payload: SupportKeyCreateModel):
    if not payload.assigned_name.strip():
        return JSONResponse(status_code=400, content={"success": False, "message": "Tên người nhận key không được để trống!"})
    
    k = database.create_support_key(
        assigned_name=payload.assigned_name,
        email=payload.email or "",
        phone=payload.phone or "",
        note=payload.note or "",
        expires_at=payload.expires_at or ""
    )
    return {"success": True, "key": k}

@app.post("/api/admin/support-keys/status", dependencies=[Depends(require_admin)])
async def api_admin_update_support_key_status(payload: SupportKeyStatusModel):
    success = database.update_support_key_status(payload.key_code, payload.status)
    if not success:
        return JSONResponse(status_code=400, content={"success": False, "message": "Không tìm thấy key hoặc trạng thái không hợp lệ!"})
    return {"success": True, "message": f"Đã chuyển trạng thái key sang {payload.status}"}

@app.post("/api/admin/support-keys/expiry", dependencies=[Depends(require_admin)])
async def api_admin_update_support_key_expiry(payload: SupportKeyExpiryModel):
    success = database.update_support_key_expiry(payload.key_code, payload.expires_at)
    return {"success": success}

@app.delete("/api/admin/support-keys/{key_code}", dependencies=[Depends(require_admin)])
async def api_admin_delete_support_key(key_code: str):
    success = database.delete_support_key(key_code)
    return {"success": success}

@app.get("/api/admin/support-assignments", dependencies=[Depends(require_admin)])
async def api_admin_list_assignments(support_key: Optional[str] = None, exam_date: Optional[str] = None):
    assignments = database.list_support_assignments(support_key=support_key, exam_date=exam_date)
    return {"success": True, "assignments": assignments}

@app.post("/api/admin/support-assignments", dependencies=[Depends(require_admin)])
async def api_admin_create_assignment(payload: SupportAssignmentCreateModel):
    if not payload.support_key.strip():
        return JSONResponse(status_code=400, content={"success": False, "message": "Chưa chọn mã Key Support!"})
    if not payload.hwid.strip():
        return JSONResponse(status_code=400, content={"success": False, "message": "Chưa nhập mã HWID của thí sinh!"})
    if not payload.exam_date.strip():
        return JSONResponse(status_code=400, content={"success": False, "message": "Chưa chọn ngày thi!"})
    
    assignment = database.create_support_assignment(
        support_key=payload.support_key,
        hwid=payload.hwid,
        student_name=payload.student_name or "",
        exam_date=payload.exam_date,
        exam_shift=payload.exam_shift or "",
        subject=payload.subject or "",
        notes=payload.notes or ""
    )
    return {"success": True, "assignment": assignment}

@app.delete("/api/admin/support-assignments/{assignment_id}", dependencies=[Depends(require_admin)])
async def api_admin_delete_assignment(assignment_id: int):
    success = database.delete_support_assignment(assignment_id)
    return {"success": success}



# ────────────────── Telegram Webhook ──────────────────

@app.post("/api/telegram/webhook")
async def api_telegram_webhook(request: Request):
    try:
        body = await request.json()
        if "callback_query" in body:
            await telegram_bot.process_telegram_callback(body["callback_query"])
    except Exception:
        pass
    return {"ok": True}
