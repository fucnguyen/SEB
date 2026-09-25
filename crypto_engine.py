import base64
import xml.etree.ElementTree as ET
from typing import Optional, Tuple
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# Khóa bí mật RSA-2048 (trùng khớp 100% với C# SEB_KeyGen và Android Kotlin)
RSA_PRIVATE_KEY_XML = """<RSAKeyValue><Modulus>ugM4JEATP71v+I5yfNUDEQuFNw0W2VZ+BJ7qYOxoCYPmaTlgBvjPtzyweru6hynb6qbxAPtXHVWAYh+KpCV4cRyfBz048EtdeV4vZPAPdjeGlCjVzrBgOUq1ykHmEJoLFsrsKNdcTUNIXh+g5rDFjL0mHQmieb8iaR9XXCNn/W2xwbqf3XGKSuzZXfZ++uooCzOhsd4MtFhYMZJKTe8OLmm2GOTJabKM4l4vPkY+iEyA07qmzVkJg1Ck37lf66hyChu7/RCyOWxHVdoOUne4PjxxXMKKEPlhOiNCrtsvReRNgzEMlIciMzNAt3H9oE8R04VroK7YtdD0AMUXTVr3AQ==</Modulus><Exponent>AQAB</Exponent><P>9Ln4fnJ9nziyrYkWdDq51Z1+tNJwB6Aut4pHW+TPDJIb4b3AR3pnWnRGFwrdyu4ZrprtvUTH/Gtsz99hUGvLOxE7GfaZ2rx+8p9ZMgvr8HgpauIFJevv74YPE5RYlohWSZrX0IdmfjtW7Rjk5/AlL+d2BxfhAJTTC61jvAlAO5M=</P><Q>wpTX0dHud5EjL0Y+A4LWPWC+d2dEoAH6mXAwE7H315i5PDWuoEi7W2RjCRDqQ7meW8ixhDB64T3js2fycGe+fREJjd8KaC8CFmA/GnGi7fd/Isy6Ztw1tL2be84jhLrk7PvgnqSY9YYZho+wuT7fEafpD1Wr8oDk9Z7zYYU+p5s=</Q><DP>Fq9ifH4qbOb5kSKDBVUoQsftpd9X6S0NB5B22urT0ot8sClBuJ59FCJxGNO2CYiWstvDq+bDTv+6P26qe6TyWtBXFSoJyv/sGJtyzjPStCC/XhwDdCdxv1dC8IKwz4tlzD7hQIA8nPjtLt8+4M0e9VjUVQX+omopQgzZkOWeoac=</DP><DQ>QzpP0sOYg6EWqfe351imErDBPdnlIO9uGONlCPj9K3Ut0rqtad2XNf1aJkC838dbClUt2AE0A2xxpoOshN+jNezUAztjihlrvDVmuAk5BMT1HR3k7TL6L0cvWDghl3NHMwXXVpiB7Jp3aUFuCqLJSX1dDZpI/VFBSgewCSqTOi8=</DQ><InverseQ>jNghW7b0tTu9aGxw8NfCn2YLze/1haBHOly3NJpRJ3Qfsf6y7eXObFMu2+vcW41WwbMIHyQaQT+ravkskvD1MQyk8SOvLVoeFHcl7hUHqm+nnsBdT0772PpFyfxkrINPHS9Dw5FUN1I83mOyt+oK6Ot0ZSKwBaS/34oyvLX1INY=</InverseQ><D>ENqN0asEk3fkl07AzNK4DmlOzqge895EWMLVVabV3lbXH52VN8x/dYjILLaptelzBZXOrFoZkIzYrwtQkoLaoNUJC6zeZddORtrjzG971yg8x1vT04Bjl41PX14NLF/otU35i9HHiTCZc/3FpGFL5O6Wb3caA5Hv2jp+vdhvaaTI8nSMdb7qsj2U8I95vHNXCO+jwRlvEPC15KZIPuQiumRSTMKbiW3q+/QtxOBOEjkhahLxYcPQgVYVtSsv+Q1/pqP0LYZDp3mzEjmvCE14vqDjtjaLIHge3O4ewMK0m3EapJ5hFMGGasRNtBT/QzyWFjaq7ZEaryDTjMmSIVrraQ==</D></RSAKeyValue>"""

AES_KEY = "SEB_AES_Key_123!@#"
SALT = b"SebSaltKey_123"

def _b64_to_int(s: str) -> int:
    return int.from_bytes(base64.b64decode(s), byteorder="big")

def _load_rsa_private_key() -> rsa.RSAPrivateKey:
    root = ET.fromstring(RSA_PRIVATE_KEY_XML)
    n = _b64_to_int(root.find("Modulus").text)
    e = _b64_to_int(root.find("Exponent").text)
    d = _b64_to_int(root.find("D").text)
    p = _b64_to_int(root.find("P").text)
    q = _b64_to_int(root.find("Q").text)
    dmp1 = _b64_to_int(root.find("DP").text)
    dmq1 = _b64_to_int(root.find("DQ").text)
    iqmp = _b64_to_int(root.find("InverseQ").text)

    public_numbers = rsa.RSAPublicNumbers(e, n)
    private_numbers = rsa.RSAPrivateNumbers(
        p=p, q=q, d=d, dmp1=dmp1, dmq1=dmq1, iqmp=iqmp,
        public_numbers=public_numbers
    )
    return private_numbers.private_key()

_PRIVATE_KEY = _load_rsa_private_key()

def _derive_aes_key_iv() -> Tuple[bytes, bytes]:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=48, # 32 bytes AES Key + 16 bytes IV
        salt=SALT,
        iterations=10000,
    )
    derived = kdf.derive(AES_KEY.encode("utf-8"))
    return derived[:32], derived[32:48]

def encrypt_aes(plain_text: str) -> str:
    key, iv = _derive_aes_key_iv()
    data = plain_text.encode("utf-8")
    pad_len = 16 - (len(data) % 16)
    padded = data + bytes([pad_len] * pad_len)
    
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ct = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ct).decode("ascii")

def decrypt_aes(cipher_b64: str) -> Optional[str]:
    try:
        key, iv = _derive_aes_key_iv()
        ct = base64.b64decode(cipher_b64)
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        pt = decryptor.update(ct) + decryptor.finalize()
        pad_len = pt[-1]
        if pad_len < 1 or pad_len > 16:
            return None
        return pt[:-pad_len].decode("utf-8")
    except Exception:
        return None

def generate_license(hwid: str, expiry_date_str: str, pin: str = "NO_PIN") -> str:
    """
    Tạo License Key chuẩn theo format C#: {hwid}|{yyyy-MM-dd HH:mm:ss}|{pin}
    Ký số bằng RSA-2048 SHA-256 rồi mã hóa AES-256.
    """
    payload = f"{hwid.strip()}|{expiry_date_str.strip()}|{pin.strip()}"
    data_bytes = payload.encode("utf-8")
    signature_bytes = _PRIVATE_KEY.sign(
        data_bytes,
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    signature_b64 = base64.b64encode(signature_bytes).decode("ascii")
    combined = f"{payload}::{signature_b64}"
    return encrypt_aes(combined)

def verify_license(license_key: str) -> Optional[dict]:
    """
    Giải mã và kiểm tra tính hợp lệ của license key.
    Trả về dict {'hwid': ..., 'expiry': ..., 'pin': ...} nếu hợp lệ, None nếu lỗi.
    """
    decrypted = decrypt_aes(license_key)
    if not decrypted or "::" not in decrypted:
        return None
    
    parts = decrypted.split("::")
    if len(parts) != 2:
        return None
    
    payload, sig_b64 = parts[0], parts[1]
    data_bytes = payload.encode("utf-8")
    
    try:
        sig_bytes = base64.b64decode(sig_b64)
        public_key = _PRIVATE_KEY.public_key()
        public_key.verify(
            sig_bytes,
            data_bytes,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        
        payload_parts = payload.split("|")
        if len(payload_parts) < 2:
            return None
            
        return {
            "hwid": payload_parts[0].strip(),
            "expiry": payload_parts[1].strip(),
            "pin": payload_parts[2].strip() if len(payload_parts) >= 3 else "NO_PIN"
        }
    except Exception:
        return None
