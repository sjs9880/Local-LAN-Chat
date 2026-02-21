import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_PACKET_TTL = 300  # 초 — 재전송 공격 방어용 Fernet TTL


class SessionSecurity:
    """비밀번호 기반 양방향 암호화 처리 클래스 (AES)"""

    def __init__(self, password: str, room_name: str = ""):
        self.password = password
        self.is_encrypted = bool(password)

        if self.is_encrypted:
            # room_name 기반 동적 솔트 — 방마다 키가 달라 크로스-룸 재전송 불가
            salt = hashlib.sha256(room_name.encode()).digest() if room_name else b"lan_chat_default_salt"
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=480000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
            self.fernet = Fernet(key)

    def encrypt(self, data: bytes) -> bytes:
        if not self.is_encrypted:
            return data
        return self.fernet.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        if not self.is_encrypted:
            return data
        try:
            return self.fernet.decrypt(data, ttl=_PACKET_TTL)
        except InvalidToken:
            raise ValueError("암호 복호화 실패: 비밀번호가 다르거나 패킷이 만료/손상되었습니다.")
        except Exception:
            raise ValueError("암호 복호화 실패: 비밀번호가 다르거나 패킷이 손상되었습니다.")
