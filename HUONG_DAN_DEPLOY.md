# HƯỚNG DẪN TRIỂN KHAI (DEPLOY) WEB PORTAL LÊN SERVER ONLINE

Hệ thống **SEB_WebPortal** được thiết kế siêu nhẹ, tương thích với mọi môi trường Linux/Windows và nền tảng đám mây. Dưới đây là 3 cách triển khai phổ biến nhất:

---

## CÁCH 1: BIẾN CHÍNH MÁY TÍNH CỦA BẠN THÀNH SERVER ONLINE (MIỄN PHÍ 100%, KHÔNG CẦN THUÊ VPS)
> Dành cho người muốn chạy thử nghiệm ngay lập tức, không tốn 1 xu chi phí và không cần cấu hình Router/Mở port mạng!

Chúng ta sử dụng công nghệ **Cloudflare Tunnel (`cloudflared`)** chính hãng của Cloudflare:
1. Bạn chạy file `Chay_Web_Va_Telegram_Bot.bat` trên máy tính.
2. Tải công cụ miễn phí `cloudflared.exe` từ Cloudflare: https://github.com/cloudflare/cloudflared/releases
3. Mở CMD gõ:
   ```cmd
   cloudflared.exe tunnel --url http://localhost:8000
   ```
4. Ngay lập tức Cloudflare sẽ cấp cho bạn một đường link HTTPS công khai (ví dụ: `https://free-exam-subdomain.trycloudflare.com`).
5. **Học sinh ở bất cứ đâu trên thế giới đều vào link đó để xin tải file và kích hoạt máy bình thường!**

---

## CÁCH 2: TRIỂN KHAI LÊN VPS LINUX (UBUNTU) — KHUYÊN DÙNG CHO HỆ THỐNG THẬT
> Ổn định 24/7, tốc độ mạng cực nhanh tại Việt Nam (Chi phí thuê VPS ~50.000đ - 100.000đ/tháng tại VietPN, CloudFly, BKHost, Hetzner...).

### Bước 1: Cài đặt Docker trên VPS Ubuntu
Đăng nhập SSH vào VPS của bạn và chạy lệnh:
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
```

### Bước 2: Tải thư mục `SEB_WebPortal` lên VPS
Sử dụng WinSCP, FileZilla hoặc lệnh Git để copy toàn bộ thư mục `SEB_WebPortal` và file `Setup_ThiTrucTuyen_v2.exe` lên VPS.

### Bước 3: Khởi động hệ thống
Di chuyển vào thư mục và chạy 1 lệnh duy nhất:
```bash
docker compose up -d --build
```
Hệ thống sẽ tự động chạy ngầm 24/7 và tự khởi động lại khi VPS reboot.

### Bước 4: Trỏ Tên Miền & Bật Bảo Vệ Cloudflare (Chống Đục Web 100%)
1. Mua 1 tên miền (ví dụ: `thitructuyen.vn` hoặc dùng tên miền miễn phí).
2. Trỏ DNS của tên miền về địa chỉ IP của VPS thông qua **Cloudflare**.
3. **Bật biểu tượng đám mây màu cam (Proxied)** trên Cloudflare:
   - IP gốc của VPS sẽ được giấu kín 100% (Hacker không thể tấn công DDoS hay quét cổng IP của bạn).
   - Tự động có chứng chỉ bảo mật HTTPS/SSL màu xanh miễn phí.
   - Bật thêm tính năng **Cloudflare WAF** và **Turnstile (Captcha vô hình)**.

---

## CÁCH 3: DEPLOY MIỄN PHÍ LÊN RENDER.COM
1. Đăng ký tài khoản miễn phí tại: https://render.com
2. Tạo mới một **Web Service**:
   - Runtime: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port 10000`
3. Render sẽ tự động cấp một đường link online dạng `https://ten-app.onrender.com` có sẵn HTTPS!

---

## CÁCH CẤU HÌNH PHẦN MỀM `SEB_Launcher` KẾT NỐI VỚI SERVER ONLINE

Khi bạn đã có link web online (ví dụ: `https://thi.tenmiencuaban.com`):
1. Bên cạnh file `SEB_Launcher.exe` (hoặc trong thư mục bộ cài), bạn chỉ cần tạo 1 file text tên là **`server_url.txt`**.
2. Bên trong file `server_url.txt` chỉ cần ghi 1 dòng duy nhất là địa chỉ web của bạn:
   ```text
   https://thi.tenmiencuaban.com
   ```
3. `SEB_Launcher.exe` sẽ tự động đọc file này và kết nối thẳng lên Server Online của bạn!
