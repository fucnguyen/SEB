import os
import boto3
from botocore.config import Config
from typing import Optional, Tuple
import database

LOCAL_SETUP_PATH = r"d:\File cài đặt\SEB_Licensing\Setup_ThiTrucTuyen_v2.exe"

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

def generate_download_url(token: str, expiration_seconds: int = 1800, system_type: str = "SEB") -> Tuple[str, bool]:
    """
    Sinh đường dẫn tải file cài đặt.
    Trả về (url, is_presigned_cloud).
    Nếu có cấu hình Cloudflare R2 -> trả về Presigned URL thời hạn 30 phút.
    Nếu chưa cấu hình -> trả về API stream cục bộ của server: /api/download/stream?token={token}
    """
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

    # 2. Link lưu trữ đám mây ngoài (GitHub Release, S3, Drive, v.v.)
    if system_type and system_type.upper() == "EOS":
        external_url = database.get_setting("external_download_url_eos").strip() or database.get_setting("external_download_url").strip()
    else:
        external_url = database.get_setting("external_download_url_seb").strip() or database.get_setting("external_download_url").strip()

    if external_url:
        return external_url, True

    # 3. Fallback to local server stream
    return f"/api/download/stream?token={token}", False

def get_local_setup_file() -> Optional[str]:
    # Kiểm tra file ở các vị trí khả dĩ (cả Windows và Linux Server)
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "Setup_ThiTrucTuyen_v2.exe"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "Setup_ThiTrucTuyen_v2.exe"),
        LOCAL_SETUP_PATH,
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Setup_ThiTrucTuyen_v2.exe"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Output", "Setup_ThiTrucTuyen_v2.exe")
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None
