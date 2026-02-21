import json
import socket
import struct

from backend.core.security import SessionSecurity
from backend.utils.file_manager import BandwidthThrottler


class P2PClient:
    """Outbound TCP client helper."""

    @staticmethod
    def send_data(ip: str, port: int, payload: bytes) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5.0)
                sock.connect((ip, port))
                sock.sendall(struct.pack("!I", len(payload)) + payload)
                return True
        except Exception as e:
            print(f"[TCP Client] send failed ({ip}:{port}): {e}")
            return False

    @staticmethod
    def send_file_stream(
        ip: str,
        port: int,
        filepath: str,
        req_id: str,
        security: SessionSecurity,
        throttler: BandwidthThrottler,
        expected_size: int | None = None,
        expected_sha256: str | None = None,
    ) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(30.0)
                sock.connect((ip, port))

                header = {
                    "type": "FILE_STREAM_START",
                    "req_id": req_id,
                    "expected_size": expected_size,
                    "expected_sha256": expected_sha256,
                }
                enc_header = security.encrypt(json.dumps(header).encode("utf-8"))
                sock.sendall(struct.pack("!I", len(enc_header)) + enc_header)

                chunk_size = 65536
                with open(filepath, "rb") as f:
                    while True:
                        raw_chunk = f.read(chunk_size)
                        if not raw_chunk:
                            break

                        enc_chunk = security.encrypt(raw_chunk)
                        throttler.wait_for_tokens(len(enc_chunk))
                        sock.sendall(struct.pack("!I", len(enc_chunk)) + enc_chunk)

                return True
        except Exception as e:
            print(f"[File Transfer] stream send error: {e}")
            return False
