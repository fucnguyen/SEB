import httpx
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import database
import crypto_engine

API_URL = "https://api.telegram.org/bot{token}/{method}"

def get_bot_credentials():
    token = database.get_setting("telegram_bot_token").strip()
    chat_id = database.get_setting("telegram_chat_id").strip()
    enabled = database.get_setting("telegram_notifications_enabled", "true").lower() == "true"
    return token, chat_id, enabled

async def send_telegram_request(method: str, payload: dict) -> Optional[dict]:
    token, _, enabled = get_bot_credentials()
    if not token or not enabled:
        return None
    url = API_URL.format(token=token, method=method)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        print(f"[Telegram Error] {e}")
    return None

async def notify_download_request(req: Dict[str, Any]):
    _, chat_id, enabled = get_bot_credentials()
    if not chat_id or not enabled:
        return

    text = (
        "🔔 <b>YÊU CẦU TẢI PHẦN MỀM THI (~200MB)</b>\n\n"
        f"👤 <b>Học sinh:</b> {req.get('full_name', 'N/A')}\n"
        f"📧 <b>Email:</b> {req.get('email', 'Chưa cung cấp')}\n"
        f"📝 <b>Lời nhắn:</b> {req.get('note', 'Không có')}\n"
        f"🌐 <b>IP:</b> {req.get('ip_address', 'N/A')}\n"
        f"⏰ <b>Thời gian:</b> {req.get('created_at', 'N/A')}"
    )

    req_id = req["request_id"]
    inline_keyboard = [
        [
            {"text": "✅ Cho phép tải", "callback_data": f"dl_app:{req_id}"},
            {"text": "❌ Từ chối", "callback_data": f"dl_rej:{req_id}"}
        ]
    ]

    await send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": inline_keyboard}
    })

async def notify_activation_request(lic: Dict[str, Any]):
    _, chat_id, enabled = get_bot_credentials()
    if not chat_id or not enabled:
        return

    hwid = lic.get("hwid", "N/A")
    short_hwid = hwid[:24] + "..." if len(hwid) > 24 else hwid
    text = (
        "💻 <b>YÊU CẦU KÍCH HOẠT MÃ MÁY (HWID)</b>\n\n"
        f"👤 <b>Học sinh:</b> {lic.get('student_name', 'N/A')}\n"
        f"📧 <b>Email:</b> {lic.get('email', 'Chưa cung cấp')}\n"
        f"🖥️ <b>Tên máy tính:</b> {lic.get('machine_name', 'N/A')}\n"
        f"🔑 <b>Mã máy (HWID):</b>\n<code>{hwid}</code>\n"
        f"⏰ <b>Thời gian:</b> {lic.get('created_at', 'N/A')}"
    )

    req_id = lic["request_id"]
    inline_keyboard = [
        [
            {"text": "🚀 7 Ngày", "callback_data": f"act:7d:{req_id}"},
            {"text": "🚀 30 Ngày", "callback_data": f"act:30d:{req_id}"}
        ],
        [
            {"text": "🚀 1 Kỳ (120N)", "callback_data": f"act:120d:{req_id}"},
            {"text": "🚀 1 Năm (365N)", "callback_data": f"act:365d:{req_id}"}
        ],
        [
            {"text": "🚀 Vĩnh viễn", "callback_data": f"act:life:{req_id}"},
            {"text": "🔒 Từ chối / Khóa", "callback_data": f"act:lock:{req_id}"}
        ]
    ]

    await send_telegram_request("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": inline_keyboard}
    })

async def process_telegram_callback(callback_query: dict):
    cb_id = callback_query.get("id")
    data = callback_query.get("data", "")
    message = callback_query.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    original_text = message.get("text", "")

    # Trả lời Telegram rằng đã nhận callback
    await send_telegram_request("answerCallbackQuery", {
        "callback_query_id": cb_id,
        "text": "Đã xử lý yêu cầu!"
    })

    if not data or ":" not in data:
        return

    parts = data.split(":")
    action = parts[0]

    # 1. Xử lý yêu cầu tải file
    if action == "dl_app":
        req_id = parts[1]
        token = str(uuid.uuid4())
        expires_at = (datetime.now() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
        success = database.approve_download_request(req_id, token, expires_at)
        new_text = original_text + f"\n\n👉 <b>KẾT QUẢ:</b> ✅ ĐÃ PHÊ DUYỆT CHO TẢI (Hạn link: 30 phút)"
        await send_telegram_request("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": new_text,
            "parse_mode": "HTML"
        })

    elif action == "dl_rej":
        req_id = parts[1]
        database.reject_download_request(req_id)
        new_text = original_text + f"\n\n👉 <b>KẾT QUẢ:</b> ❌ ĐÃ TỪ CHỐI TẢI FILE"
        await send_telegram_request("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": new_text,
            "parse_mode": "HTML"
        })

    # 2. Xử lý kích hoạt mã máy HWID
    elif action == "act":
        duration = parts[1]
        req_id = parts[2]
        lic = database.get_license_by_request_id(req_id)
        if not lic:
            return

        hwid = lic["hwid"]
        now = datetime.now()

        if duration == "7d":
            exp_date = now + timedelta(days=7)
            label = "7 Ngày"
        elif duration == "30d":
            exp_date = now + timedelta(days=30)
            label = "30 Ngày"
        elif duration == "120d":
            exp_date = now + timedelta(days=120)
            label = "1 Học kỳ (120 Ngày)"
        elif duration == "365d":
            exp_date = now + timedelta(days=365)
            label = "1 Năm"
        elif duration == "life":
            exp_date = now + timedelta(days=3650) # 10 năm
            label = "Vĩnh viễn (10 Năm)"
        elif duration == "lock":
            database.lock_license(hwid)
            new_text = original_text + f"\n\n👉 <b>KẾT QUẢ:</b> 🔒 ĐÃ KHÓA MÃ MÁY NÀY!"
            await send_telegram_request("editMessageText", {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": new_text,
                "parse_mode": "HTML"
            })
            return
        else:
            return

        exp_str = exp_date.strftime("%Y-%m-%d %H:%M:%S")
        license_key = crypto_engine.generate_license(hwid, exp_str)
        database.approve_license(hwid, license_key, exp_str, duration)

        new_text = (
            original_text + 
            f"\n\n👉 <b>KẾT QUẢ:</b> 🚀 <b>ĐÃ DUYỆT THÀNH CÔNG!</b>\n"
            f"📅 Thời hạn: <b>{label}</b> (Hết hạn: {exp_str})\n"
            f"💻 Phần mềm trên máy học sinh sẽ tự động mở khóa ngay lập tức!"
        )
        await send_telegram_request("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": new_text,
            "parse_mode": "HTML"
        })

# ────────────────── Background Polling Loop ──────────────────
# Giúp bot hoạt động ngay cả khi chạy trên Localhost mà không cần cấu hình Domain/SSL

async def start_telegram_polling():
    last_update_id = 0
    print("[Telegram Bot] Khởi động vòng lặp kiểm tra tin nhắn và nút bấm...")
    while True:
        token, _, enabled = get_bot_credentials()
        if not token or not enabled:
            await asyncio.sleep(5)
            continue

        try:
            url = API_URL.format(token=token, method="getUpdates")
            params = {"offset": last_update_id + 1, "timeout": 15}
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        last_update_id = max(last_update_id, update["update_id"])
                        if "callback_query" in update:
                            await process_telegram_callback(update["callback_query"])
        except Exception:
            pass
        await asyncio.sleep(1)
