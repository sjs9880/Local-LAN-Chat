import hashlib
import json
import os
import struct
import threading
import time
import uuid
from typing import Callable, Optional

from backend.core.history import ChatHistoryManager
from backend.core.security import SessionSecurity
from backend.network.discovery import PeerDiscovery
from backend.network.p2p_client import P2PClient
from backend.network.p2p_server import P2PServer
from backend.utils.file_manager import BandwidthThrottler, FileManager


MAX_PACKET_SIZE = 50 * 1024 * 1024  # 50 MB — OOM DoS 방어용 상한


class P2PEngine:
    """Core backend controller for discovery, messaging, and file transfer."""

    def __init__(self, nickname: str, password: str = "", room_name: str = "Lobby"):
        self.nickname = nickname
        self.room_name = room_name
        self.security = SessionSecurity(password, room_name=room_name)

        self.tcp_server = P2PServer()
        self.discovery = PeerDiscovery(
            nickname=self.nickname,
            tcp_port=self.tcp_server.port,
            room_name=self.room_name,
            is_private=self.security.is_encrypted,
        )

        self.history_mgr = ChatHistoryManager(self.discovery.session_id)

        self.active_file_requests = {}  # {req_id: request_packet}
        self.outgoing_file_requests = {}  # {req_id: {...}}
        self.download_paths = {}  # {req_id: temp_save_path}

        self.on_file_transfer_completed: Optional[Callable] = None  # (req_id, final_path)
        self.on_message_received: Optional[Callable] = None
        self.on_peer_updated: Optional[Callable] = None
        self.on_file_requested: Optional[Callable] = None
        self.on_chat_history_received: Optional[Callable] = None

        self._running = False

    def start(self):
        self._running = True
        self.tcp_server.start(self._handle_incoming_tcp)
        self.discovery.start()
        threading.Thread(target=self._peer_monitor_loop, daemon=True).start()
        print(
            f"[Engine] started (nick={self.nickname}, tcp={self.tcp_server.port}, encrypted={self.security.is_encrypted})"
        )

    def stop(self):
        # 1. 종료 전 진행 중인 파일 공유가 있다면 취소 패킷을 동일 방에 브로드캐스트
        for req_id in list(self.outgoing_file_requests.keys()):
            try:
                self.cancel_file_sharing(req_id)
            except Exception as e:
                print(f"[Engine] cancel_file_sharing error on stop ({req_id}): {e}")

        # 2. 메인 스레드 플래그 다운
        self._running = False
        try:
            self.discovery.stop()
        except Exception as e:
            print(f"[Engine] discovery stop error: {e}")

        try:
            self.tcp_server.stop()
        except Exception as e:
            print(f"[Engine] tcp stop error: {e}")

        for req_id, info in list(self.outgoing_file_requests.items()):
            if info.get("is_zip"):
                path = info.get("filepath")
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError as e:
                        print(f"[Engine] temp cleanup failed ({req_id}): {e}")

        # 수신 중이던 .part 임시파일 및 임시 폴더 정리
        temp_dirs = set()
        for req_id, part_path in list(self.download_paths.items()):
            if part_path and part_path.endswith(".part") and os.path.exists(part_path):
                try:
                    os.remove(part_path)
                    print(f"[Engine] cleaned up .part file ({req_id}): {part_path}")
                    temp_dirs.add(os.path.dirname(os.path.abspath(part_path)))
                except OSError as e:
                    print(f"[Engine] .part cleanup failed ({req_id}): {e}")
        for temp_dir in temp_dirs:
            try:
                os.rmdir(temp_dir)
            except OSError:
                pass
        print("[Engine] stopped")

    def _my_short_id(self) -> str:
        return PeerDiscovery.ip_short_id(self.discovery.local_ip)

    def _broadcast_to_room(self, packet: dict) -> int:
        """packet을 직렬화·암호화 후 동일 방의 모든 피어에게 전송하고 성공 수를 반환합니다."""
        enc_data = self.security.encrypt(json.dumps(packet).encode("utf-8"))
        success_count = 0
        for info in self.discovery.get_active_peers().values():
            if info.get("room_name") == self.room_name and P2PClient.send_data(info["ip"], info["tcp_port"], enc_data):
                success_count += 1
        return success_count

    def send_chat_message(self, target_session_id: str, message: str) -> bool:
        peers = self.discovery.get_active_peers()
        if target_session_id not in peers:
            print(f"[Engine] peer not found: {target_session_id}")
            return False

        target = peers[target_session_id]
        packet = self.history_mgr.add_local_message(
            sender_nickname=self.nickname,
            content=message,
            extra={"sender_short_id": self._my_short_id()},
        )
        raw_data = json.dumps(packet).encode("utf-8")
        encrypted_data = self.security.encrypt(raw_data)
        return P2PClient.send_data(target["ip"], target["tcp_port"], encrypted_data)

    def broadcast_chat_message(self, message: str) -> bool:
        packet = self.history_mgr.add_local_message(
            sender_nickname=self.nickname,
            content=message,
            extra={"sender_short_id": self._my_short_id()},
        )
        return self._broadcast_to_room(packet) > 0

    def broadcast_file_request(self, paths: list[str], speed_limit_bytes: int = 0) -> tuple[bool, dict, str]:
        req_id = str(uuid.uuid4())
        meta = FileManager.prepare_transfer(paths, f"temp_{req_id}.zip")
        file_sha256 = FileManager.sha256_file(meta["target_path"])

        self.outgoing_file_requests[req_id] = {
            "filepath": meta["target_path"],
            "is_zip": meta["is_zip"],
            "speed_limit": speed_limit_bytes,
            "file_size": meta["size"],
            "file_sha256": file_sha256,
        }

        extra_info = {
            "req_id": req_id,
            "file_name": meta["name"],
            "file_size": meta["size"],
            "is_zip": meta["is_zip"],
            "file_sha256": file_sha256,
            "sender_short_id": self._my_short_id(),
        }
        packet = self.history_mgr.add_local_message(
            sender_nickname=self.nickname,
            content=f"File share: {meta['name']}",
            msg_type="FILE_REQ",
            extra=extra_info,
        )

        return self._broadcast_to_room(packet) > 0, meta, req_id

    def cancel_file_sharing(self, req_id: str):
        if req_id in self.outgoing_file_requests:
            info = self.outgoing_file_requests.pop(req_id)
            if info.get("is_zip"):
                file_path = info.get("filepath")
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError as e:
                        print(f"[Engine] cancel cleanup failed ({req_id}): {e}")

        packet = self.history_mgr.add_local_message(
            sender_nickname=self.nickname,
            content="File sharing canceled.",
            msg_type="FILE_CANCEL",
            extra={
                "req_id": req_id,
                "sender_short_id": self._my_short_id(),
            },
        )

        self._broadcast_to_room(packet)

    def accept_file_transfer(self, req_id: str, save_path: str) -> bool:
        if req_id not in self.active_file_requests:
            return False

        req_info = self.active_file_requests[req_id]
        sender_session = req_info.get("sender_session")
        peers = self.discovery.get_active_peers()
        if sender_session not in peers:
            return False

        self.download_paths[req_id] = save_path
        target = peers[sender_session]

        packet = {"type": "FILE_ACCEPT", "req_id": req_id, "sender_session": self.discovery.session_id}
        enc_data = self.security.encrypt(json.dumps(packet).encode("utf-8"))
        return P2PClient.send_data(target["ip"], target["tcp_port"], enc_data)

    def reject_file_transfer(self, req_id: str):
        if req_id in self.active_file_requests:
            del self.active_file_requests[req_id]

    def _recv_exact(self, sock, count):
        buf = b""
        while count > 0:
            newbuf = sock.recv(count)
            if not newbuf:
                return None
            buf += newbuf
            count -= len(newbuf)
        return buf

    def _handle_incoming_tcp(self, client_sock, addr):
        try:
            client_sock.settimeout(10.0)

            length_bytes = self._recv_exact(client_sock, 4)
            if not length_bytes:
                return
            msg_len = struct.unpack("!I", length_bytes)[0]
            if msg_len > MAX_PACKET_SIZE:
                print(f"[Engine] packet too large ({msg_len} bytes), closing connection from {addr}")
                client_sock.close()
                return

            first_packet = self._recv_exact(client_sock, msg_len)
            if not first_packet:
                return

            decrypted_data = self.security.decrypt(first_packet)
            packet = json.loads(decrypted_data.decode("utf-8"))
            packet_type = packet.get("type")

            if packet_type in ("MESSAGE", "FILE_REQ", "FILE_CANCEL", "FILE_DOWNLOADED"):
                is_new = self.history_mgr.receive_remote_message(packet)
                if is_new:
                    if packet_type == "FILE_REQ":
                        req_id = packet.get("req_id")
                        if req_id:
                            self.active_file_requests[req_id] = packet
                    if self.on_message_received:
                        self.on_message_received(packet)

            elif packet_type == "CHAT_HISTORY":
                messages = packet.get("messages", [])
                new_messages = []
                for msg in messages:
                    if self.history_mgr.receive_remote_message(msg):
                        new_messages.append(msg)
                if new_messages and self.on_chat_history_received:
                    self.on_chat_history_received(new_messages)
                print(f"[Engine] chat history received: total={len(messages)}, new={len(new_messages)}")

            elif packet_type == "FILE_ACCEPT":
                req_id = packet.get("req_id")
                if req_id not in self.outgoing_file_requests:
                    return

                out_info = self.outgoing_file_requests[req_id]
                sender_session = packet.get("sender_session")
                peers = self.discovery.get_active_peers()
                target_info = peers.get(sender_session)
                if not target_info:
                    print(f"[Engine] file accept peer not found: {sender_session}")
                    return

                target_ip = target_info["ip"]
                target_port = target_info["tcp_port"]

                def send_task():
                    throttler = BandwidthThrottler(out_info.get("speed_limit", 0))
                    success = P2PClient.send_file_stream(
                        target_ip,
                        target_port,
                        out_info["filepath"],
                        req_id,
                        self.security,
                        throttler,
                        expected_size=out_info.get("file_size"),
                        expected_sha256=out_info.get("file_sha256"),
                    )
                    if success:
                        active_peers = self.discovery.get_active_peers()
                        dl_nickname = active_peers.get(sender_session, {}).get("nickname", "Unknown")
                        dl_short_id = PeerDiscovery.ip_short_id(target_ip)
                        dl_packet = self.history_mgr.add_local_message(
                            sender_nickname=self.nickname,
                            content=f"Downloaded: {req_id}",
                            msg_type="FILE_DOWNLOADED",
                            extra={
                                "req_id": req_id,
                                "downloader_nickname": dl_nickname,
                                "downloader_short_id": dl_short_id,
                                "sender_short_id": self._my_short_id(),
                            },
                        )
                        self._broadcast_to_room(dl_packet)
                        if self.on_message_received:
                            self.on_message_received(dl_packet)

                threading.Thread(target=send_task, daemon=True).start()

            elif packet_type == "FILE_STREAM_START":
                client_sock.settimeout(None)
                req_id = packet.get("req_id")
                if not req_id:
                    print("[Engine] invalid FILE_STREAM_START: missing req_id")
                    return

                if req_id not in self.download_paths or req_id not in self.active_file_requests:
                    print(f"[Engine] rejected FILE_STREAM_START (not accepted): {req_id}")
                    return

                req_info = self.active_file_requests[req_id]
                sender_session = req_info.get("sender_session")
                peers = self.discovery.get_active_peers()
                sender_peer = peers.get(sender_session)
                if not sender_peer or sender_peer.get("ip") != addr[0]:
                    print(f"[Engine] rejected FILE_STREAM_START (sender mismatch): {req_id}")
                    return

                save_path = self.download_paths[req_id]
                is_zip = bool(req_info.get("is_zip", False))
                expected_size = req_info.get("file_size", packet.get("expected_size"))
                expected_sha256 = (req_info.get("file_sha256") or packet.get("expected_sha256") or "").lower()

                save_dir = os.path.dirname(os.path.abspath(save_path))
                os.makedirs(save_dir, exist_ok=True)

                bytes_received = 0
                hasher = hashlib.sha256()
                try:
                    with open(save_path, "wb") as f:
                        while True:
                            chunk_len_bytes = self._recv_exact(client_sock, 4)
                            if not chunk_len_bytes:
                                break
                            chunk_len = struct.unpack("!I", chunk_len_bytes)[0]
                            if chunk_len <= 0:
                                raise ValueError(f"Invalid chunk length: {chunk_len}")
                            if chunk_len > MAX_PACKET_SIZE:
                                raise ValueError(f"Chunk too large: {chunk_len} bytes")

                            enc_chunk = self._recv_exact(client_sock, chunk_len)
                            if not enc_chunk:
                                raise ValueError("Incomplete chunk payload.")

                            raw_chunk = self.security.decrypt(enc_chunk)
                            f.write(raw_chunk)
                            bytes_received += len(raw_chunk)
                            hasher.update(raw_chunk)

                    if expected_size is not None and bytes_received != int(expected_size):
                        raise ValueError(f"Size mismatch (expected={expected_size}, actual={bytes_received})")

                    actual_sha256 = hasher.hexdigest().lower()
                    if expected_sha256 and actual_sha256 != expected_sha256:
                        raise ValueError("SHA-256 mismatch for received file stream.")

                    if is_zip:
                        extract_dir = save_path + "_extracted"
                        FileManager.extract_zip(save_path, extract_dir)
                        final_path = extract_dir
                    else:
                        final_path = save_path

                    print(f"[Engine] file receive completed: {final_path}")
                    if self.on_file_transfer_completed:
                        self.on_file_transfer_completed(req_id, final_path)
                except Exception as e:
                    print(f"[Engine] file stream validation failed ({req_id}): {e}")
                    try:
                        if os.path.isdir(save_path):
                            import shutil

                            shutil.rmtree(save_path)
                        elif os.path.exists(save_path):
                            os.remove(save_path)
                    except OSError:
                        pass
                finally:
                    self.download_paths.pop(req_id, None)

        except Exception as e:
            print(f"[Engine] TCP handler error ({addr}): {type(e).__name__}: {e}")
        finally:
            client_sock.close()

    def _send_chat_history_to(self, target_ip: str, target_port: int):
        messages = self.history_mgr.get_history_snapshot()
        if not messages:
            return
        packet = {"type": "CHAT_HISTORY", "messages": messages}
        raw_data = json.dumps(packet).encode("utf-8")
        encrypted_data = self.security.encrypt(raw_data)
        P2PClient.send_data(target_ip, target_port, encrypted_data)
        print(f"[Engine] sent chat history ({len(messages)}) -> {target_ip}:{target_port}")

    def _peer_monitor_loop(self):
        last_peers_keys = set()
        while self._running:
            current_peers = self.discovery.get_active_peers()
            current_keys = set(current_peers.keys())

            if current_keys != last_peers_keys:
                if self.room_name != "__LOBBY__":
                    new_peer_ids = current_keys - last_peers_keys
                    for sid in new_peer_ids:
                        info = current_peers.get(sid, {})
                        if info.get("room_name") == self.room_name:
                            threading.Thread(
                                target=self._send_chat_history_to,
                                args=(info["ip"], info["tcp_port"]),
                                daemon=True,
                            ).start()

                if self.on_peer_updated:
                    self.on_peer_updated(current_peers)
                last_peers_keys = current_keys

            time.sleep(2)
