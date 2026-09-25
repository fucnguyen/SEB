import os
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import database
import crypto_engine
import storage
import telegram_bot

# ────────────────── App Lifespan ──────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi tạo cơ sở dữ liệu
    database.init_db()
    print("[Hệ Thống] Database SQLite đã sẵn sàng.")

    # Khởi động Telegram Bot Polling ở chế độ nền
    bot_task = asyncio.create_task(telegram_bot.start_telegram_polling())
    yield
    bot_task.cancel()

app = FastAPI(title="SEB Licensing Portal", lifespan=lifespan)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ────────────────── Pydantic Request Models ──────────────────

class DownloadRequestModel(BaseModel):
    full_name: str
    email: Optional[str] = ""
    note: Optional[str] = ""
    session_id: Optional[str] = ""

class ActivationRequestModel(BaseModel):
    hwid: str
    student_name: Optional[str] = "Học sinh"
    email: Optional[str] = ""
    machine_name: Optional[str] = ""

class ApproveActivationModel(BaseModel):
    hwid: str
    duration: str # 7d, 30d, 120d, 365d, life

class ManualKeyModel(BaseModel):
    hwid: str
    duration: str
    name: Optional[str] = ""

class ChatMessageModel(BaseModel):
    session_id: str
    sender: str
    sender_name: str
    message: str

class SettingsModel(BaseModel):
    telegram_bot_token: Optional[str] = ""
    telegram_chat_id: Optional[str] = ""
    r2_endpoint_url: Optional[str] = ""
    r2_bucket_name: Optional[str] = ""
    r2_access_key: Optional[str] = ""
    r2_secret_key: Optional[str] = ""

# ────────────────── Web Pages ──────────────────

@app.get("/", response_class=HTMLResponse)
async def page_index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/admin", response_class=HTMLResponse)
async def page_admin(request: Request):
    return templates.TemplateResponse(request=request, name="admin.html")

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
        ip_address=client_ip
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
    Stream file cài đặt ~205MB cục bộ với BẢO MẬT KHÓA THEO ĐỊA CHỈ IP (IP-BINDING):
    - Chỉ DUY NHẤT IP của máy tính lúc xin phép mới được tải.
    - Mang link sang máy khác hoặc chia sẻ cho người khác sẽ bị chặn 403 Forbidden ngay lập tức!
    """
    row = database.get_request_by_download_token(token)
    if not row:
        raise HTTPException(status_code=403, detail="Mã tải không hợp lệ hoặc đã hết hạn!")

    # 1. Kiểm tra thời hạn 30 phút của link
    exp_str = row.get("token_expires_at")
    if exp_str:
        exp_time = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() > exp_time:
            raise HTTPException(status_code=403, detail="Đường link tải này đã hết hạn (30 phút). Vui lòng gửi yêu cầu xin duyệt lại!")

    # 2. KIỂM TRA ĐỊA CHỈ IP (IP-Binding)
    current_ip = get_client_ip(request)
    registered_ip = row.get("ip_address")

    if registered_ip and registered_ip not in ("127.0.0.1", "localhost"):
        if current_ip != registered_ip:
            raise HTTPException(
                status_code=403,
                detail=f"CẢNH BÁO BẢO MẬT: Đường link tải này chỉ cấp riêng cho địa chỉ IP ({registered_ip}) của học sinh đã xin duyệt ban đầu. "
                       f"IP của máy hiện tại là ({current_ip}). Bạn tuyệt đối KHÔNG ĐƯỢC chia sẻ link tải cho máy khác!"
            )

    # 3. Nếu cấu hình Cloudflare R2, redirect sang presigned URL bảo mật
    cloud_url, is_cloud = storage.generate_download_url(token)
    if is_cloud:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=cloud_url)

    # 4. Stream file từ máy chủ
    file_path = storage.get_local_setup_file()
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File cài đặt chưa được tải lên máy chủ!")

    return FileResponse(
        path=file_path,
        filename="Setup_ThiTrucTuyen_v2.exe",
        media_type="application/octet-stream"
    )

# ────────────────── SEB Launcher Online License API ──────────────────

@app.post("/api/request-activation")
async def api_request_activation(req: ActivationRequestModel, request: Request, bg_tasks: BackgroundTasks):
    """
    Được gọi tự động bởi SEB_Launcher trên máy học sinh.
    Gửi thông tin mã máy HWID lên Server/Telegram để Admin duyệt.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
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
        # Kiểm tra ngày hết hạn theo giờ UTC/Server
        exp_str = lic["expires_at"]
        if exp_str:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
            if datetime.now() >= exp_date:
                database.lock_license(hwid)
                return {"status": "expired", "message": "Bản quyền đã hết hạn sử dụng."}

        return {
            "status": "active",
            "license_key": lic["license_key"],
            "expires_at": lic["expires_at"],
            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    elif status == "locked":
        return {
            "status": "locked",
            "message": "Mã máy này đã bị Quản trị viên KHÓA KHẨN CẤP. Phần mềm sẽ tự hủy."
        }

    return {"status": "pending", "message": "Đang chờ Quản trị viên duyệt qua Telegram/Web..."}

# ────────────────── Admin Management API ──────────────────

@app.get("/api/admin/stats")
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

@app.get("/api/admin/download-requests")
async def api_admin_list_downloads():
    return database.list_download_requests(50)

@app.post("/api/admin/approve-download")
async def api_admin_approve_download(payload: dict):
    req_id = payload.get("request_id")
    token = str(uuid.uuid4())
    expires_at = (datetime.now() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    success = database.approve_download_request(req_id, token, expires_at)
    return {"success": success}

@app.post("/api/admin/reject-download")
async def api_admin_reject_download(payload: dict):
    req_id = payload.get("request_id")
    success = database.reject_download_request(req_id)
    return {"success": success}

@app.get("/api/admin/licenses")
async def api_admin_list_licenses():
    return database.list_licenses(100)

@app.post("/api/admin/approve-activation")
async def api_admin_approve_activation(payload: ApproveActivationModel):
    hwid = payload.hwid.strip()
    duration = payload.duration
    now = datetime.now()

    if duration == "7d": exp_date = now + timedelta(days=7)
    elif duration == "30d": exp_date = now + timedelta(days=30)
    elif duration == "120d": exp_date = now + timedelta(days=120)
    elif duration == "365d": exp_date = now + timedelta(days=365)
    elif duration == "life": exp_date = now + timedelta(days=3650)
    else: exp_date = now + timedelta(days=30)

    exp_str = exp_date.strftime("%Y-%m-%d %H:%M:%S")
    license_key = crypto_engine.generate_license(hwid, exp_str)
    success = database.approve_license(hwid, license_key, exp_str, duration)
    return {"success": success, "license_key": license_key, "expires_at": exp_str}

@app.post("/api/admin/lock-license")
async def api_admin_lock_license(payload: dict):
    hwid = payload.get("hwid", "")
    success = database.lock_license(hwid)
    return {"success": success}

@app.post("/api/admin/unlock-license")
async def api_admin_unlock_license(payload: dict):
    hwid = payload.get("hwid", "")
    success = database.unlock_license(hwid)
    return {"success": success}

@app.post("/api/admin/delete-license")
async def api_admin_delete_license(payload: dict):
    hwid = payload.get("hwid", "")
    success = database.delete_license(hwid)
    return {"success": success}

@app.post("/api/admin/manual-generate-key")
async def api_admin_manual_generate_key(payload: ManualKeyModel):
    hwid = payload.hwid.strip()
    duration = payload.duration
    name = payload.name.strip() or "Học sinh thủ công"
    now = datetime.now()

    if duration == "7d": exp_date = now + timedelta(days=7)
    elif duration == "30d": exp_date = now + timedelta(days=30)
    elif duration == "120d": exp_date = now + timedelta(days=120)
    elif duration == "365d": exp_date = now + timedelta(days=365)
    elif duration == "life": exp_date = now + timedelta(days=3650)
    else: exp_date = now + timedelta(days=30)

    exp_str = exp_date.strftime("%Y-%m-%d %H:%M:%S")
    license_key = crypto_engine.generate_license(hwid, exp_str)
    req_id = "MANUAL_" + uuid.uuid4().hex[:8].upper()

    database.create_or_update_activation_request(req_id, hwid, name, "", "Manual PC", "127.0.0.1")
    database.approve_license(hwid, license_key, exp_str, duration)

    return {"success": True, "license_key": license_key, "expires_at": exp_str}

@app.get("/api/admin/settings")
async def api_admin_get_settings():
    return database.get_all_settings()

@app.post("/api/admin/settings")
async def api_admin_save_settings(payload: SettingsModel):
    for k, v in payload.dict().items():
        if v is not None:
            database.set_setting(k, v)
    return {"success": True}

@app.post("/api/admin/test-telegram")
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

# ────────────────── Live Chat API ──────────────────

@app.get("/api/chat/messages")
async def api_get_chat_messages(session_id: str):
    return database.get_chat_messages(session_id)

@app.post("/api/chat/send")
async def api_send_chat_message(msg: ChatMessageModel):
    res = database.add_chat_message(
        session_id=msg.session_id,
        sender=msg.sender,
        sender_name=msg.sender_name,
        message=msg.message
    )
    return {"success": True, "data": res}

@app.get("/api/admin/chat-sessions")
async def api_admin_chat_sessions():
    return database.list_active_chat_sessions()

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
