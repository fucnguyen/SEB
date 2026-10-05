import os
import time
import httpx
import boto3
from botocore.config import Config
from typing import Optional, Tuple, Dict, Any
import database

LOCAL_SETUP_PATH = r"d:\File cài đặt\SEB_Licensing\Setup_ThiTrucTuyen_v2.exe"

# Bộ nhớ đệm danh sách Asset ID trên GitHub Releases để tránh gọi API lặp lại
_GITHUB_ASSET_CACHE: Dict[str, Any] = {}

FALLBACK_ASSET_IDS = {
    "Setup_ThiTrucTuyen_macOS.zip": 613054591,
    "Setup_ThiTrucTuyen_v2.exe": 613055448
}

def get_s3_client():
    endpoint_url = database.get_setting("r2_endpoint_url").strip()
    access_key = database.get_setting("r2_access_key").strip()
    secret_key = database.get_setting("r2_secret_key").strip()

    if not endpoint_url or not access_key or not secret_key:
        return None

    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4")
        )
        return s3
    except Exception:
        return None

def get_github_signed_asset_url(system_type: str = "SEB") -> Optional[str]:
    """
    Tạo Pre-signed AWS S3 CDN URL trực tiếp từ GitHub Release Repo.
    Khi học sinh bấm tải, server lấy URL ký của AWS S3 từ GitHub API và redirect 302:
    - Băng thông siêu tốc độ từ GitHub/AWS S3 Edge CDN.
    - Học sinh không cần đăng nhập GitHub, không bao giờ bị lỗi 404.
    - Hỗ trợ tải tiếp (Resume HTTP 206) và tải đa luồng (IDM).
    """
    token = (os.environ.get("GITHUB_TOKEN") or database.get_setting("github_token") or "").strip()
    repo = (os.environ.get("GITHUB_REPO") or database.get_setting("github_repo") or "fucnguyen/SEB").strip()
    tag = (database.get_setting("github_release_tag") or "v2.0").strip()

    if not repo:
        return None

    sys_upper = (system_type or "SEB").upper()
    if sys_upper in ["MAC", "MACOS", "SEB_MAC"]:
        target_name = "Setup_ThiTrucTuyen_macOS.zip"
    elif sys_upper == "EOS":
        target_name = "Setup_ThiTrucTuyen_EOS_v2.exe"
    else:
        target_name = "Setup_ThiTrucTuyen_v2.exe"

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "SEB-Licensing-Server"
    }
    if token:
        headers["Authorization"] = f"token {token}"

    global _GITHUB_ASSET_CACHE
    now = time.time()
    cached_tag = _GITHUB_ASSET_CACHE.get("tag")
    cached_time = _GITHUB_ASSET_CACHE.get("time", 0)

    # Cache danh sách Asset trong 15 phút
    if cached_tag != tag or (now - cached_time) > 900:
        try:
            with httpx.Client(timeout=10.0) as client:
                r = client.get(f"https://api.github.com/repos/{repo}/releases/tags/{tag}", headers=headers)
                if r.status_code == 200:
                    assets_map = {a["name"]: a["id"] for a in r.json().get("assets", [])}
                    _GITHUB_ASSET_CACHE = {"tag": tag, "time": now, "assets": assets_map}
        except Exception as e:
            print(f"[Storage] Không thể làm mới GitHub Release Assets: {e}")

    assets = _GITHUB_ASSET_CACHE.get("assets", {})
    asset_id = assets.get(target_name) or FALLBACK_ASSET_IDS.get(target_name)

    if asset_id:
        try:
            asset_headers = {
                "Accept": "application/octet-stream",
                "User-Agent": "SEB-Licensing-Server"
            }
            if token:
                asset_headers["Authorization"] = f"token {token}"
            # allow_redirects=False -> GitHub trả về 302 Found kèm header Location chứa S3 Signed URL
            with httpx.Client(follow_redirects=False, timeout=10.0) as client:
                r_asset = client.get(
                    f"https://api.github.com/repos/{repo}/releases/assets/{asset_id}",
                    headers=asset_headers
                )
                location = r_asset.headers.get("location") or r_asset.headers.get("Location")
                if location and location.startswith("http"):
                    return location
        except Exception as e:
            print(f"[Storage] Lỗi sinh GitHub CDN Signed URL: {e}")

    return None

def generate_download_url(token: str, expiration_seconds: int = 1800, system_type: str = "SEB") -> Tuple[str, bool]:
    """
    Sinh đường dẫn tải file cài đặt. Trả về (url, is_external_redirect).
    1. Ưu tiên Cloudflare R2 nếu có cấu hình.
    2. Ưu tiên GitHub AWS S3 CDN Pre-signed URL (tốc độ cao, không lỗi 404, không giới hạn IP).
    3. Link ngoài cấu hình trong Admin Settings (nếu có).
    4. Stream nội bộ từ ổ cứng máy chủ nếu file có sẵn trên máy chủ.
    """
    # 1. Cloudflare R2
    s3 = get_s3_client()
    bucket_name = database.get_setting("r2_bucket_name").strip()
    file_key = database.get_setting("r2_file_key", "Setup_ThiTrucTuyen_v2.exe").strip()

    if s3 and bucket_name:
        try:
            presigned_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket_name, "Key": file_key},
                ExpiresIn=expiration_seconds
            )
            return presigned_url, True
        except Exception:
            pass

    # 2. GitHub Pre-signed AWS S3 CDN URL (Siêu tốc, hoạt động hoàn hảo cả với Private Repo)
    gh_s3_url = get_github_signed_asset_url(system_type=system_type)
    if gh_s3_url:
        return gh_s3_url, True

    # 3. External configured URL
    sys_upper = (system_type or "SEB").upper()
    if sys_upper in ["MAC", "MACOS", "SEB_MAC"]:
        external_url = database.get_setting("external_download_url_mac").strip() or database.get_setting("external_download_url").strip()
    elif sys_upper == "EOS":
        external_url = database.get_setting("external_download_url_eos").strip() or database.get_setting("external_download_url").strip()
    else:
        external_url = database.get_setting("external_download_url_seb").strip() or database.get_setting("external_download_url").strip()

    if external_url and not "github.com/fucnguyen/SEB/releases/download" in external_url:
        return external_url, True

    # 4. Stream nội bộ nếu file có sẵn trên máy chủ
    file_path, _ = get_local_setup_file(system_type)
    if file_path and os.path.exists(file_path):
        return f"/api/download/stream?token={token}", False

    # 5. Nếu không có file cục bộ, vẫn dùng link GitHub công khai hoặc nội bộ
    if external_url:
        return external_url, True

    return f"/api/download/stream?token={token}", False

def get_local_setup_file(system_type: str = "SEB") -> Tuple[Optional[str], str]:
    sys_upper = (system_type or "SEB").upper()
    if sys_upper in ["MAC", "MACOS", "SEB_MAC"]:
        filename = "Setup_ThiTrucTuyen_macOS.zip"
        candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "Setup_ThiTrucTuyen_macOS.zip"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "Setup_ThiTrucTuyen_macOS.zip"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Output", "Setup_ThiTrucTuyen_macOS.zip"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "SEB_Mac_Build_Package", "Setup_ThiTrucTuyen_macOS.zip")
        ]
    else:
        filename = "Setup_ThiTrucTuyen_v2.exe"
        candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "Setup_ThiTrucTuyen_v2.exe"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "Setup_ThiTrucTuyen_v2.exe"),
            LOCAL_SETUP_PATH,
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Setup_ThiTrucTuyen_v2.exe"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Output", "Setup_ThiTrucTuyen_v2.exe")
        ]
    for p in candidates:
        if os.path.exists(p):
            return p, filename
    return None, filename
