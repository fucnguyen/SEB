@echo off
chcp 65001 >nul
title SEB Licensing Web Portal & Telegram Bot
echo ========================================================
echo   HỆ THỐNG PHÂN PHỐI & KÍCH HOẠT BẢN QUYỀN SEB ONLINE
echo ========================================================
echo.
cd /d "%~dp0"

echo [1/2] Đang kiểm tra môi trường Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LỖI] Máy tính chưa cài đặt Python! Vui lòng tải Python 3.10+ từ python.org
    pause
    exit /b 1
)

echo [2/2] Đang khởi động Server FastAPI tại cổng 8000...
echo.
echo - Trang người dùng (Học sinh): http://localhost:8000
echo - Trang quản trị (Admin):       http://localhost:8000/admin
echo.
echo Nhấn Ctrl+C để dừng server khi không sử dụng.
echo ========================================================
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
