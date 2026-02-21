import socket
import threading
import json
import time
import uuid

class PeerDiscovery:
    def __init__(self, nickname: str, tcp_port: int, room_name: str = "Lobby", is_private: bool = False, port: int = 50000, broadcast_interval: int = 3):
        self.nickname = nickname
        self.tcp_port = tcp_port
        self.room_name = room_name
        self.is_private = is_private
        
        self.port = port
        self.broadcast_interval = broadcast_interval
        self.running = False
        
        self.session_id = str(uuid.uuid4())[:8]
        self.local_ip = self._get_local_ip()
        self.peers = {}  # { session_id: {'nickname': ..., 'ip': ..., ...} }
        
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # UDP 브로드캐스트 허용
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # 포트 재사용 허용 (동일 로컬 PC에서 여러 개 띄울 때 유용할 수 있음)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # 수신 바인딩. 실패 시 다음 포트로 Fallback 하는 로직은 상위 Engine이나 별도 래퍼에서 처리 가능
        try:
            self.udp_socket.bind(('', self.port))
            print(f"[Discovery] UDP 바인딩 성공 (Port: {self.port})")
        except Exception as e:
            print(f"[Discovery] UDP 바인딩 실패: {e}")
            raise e

    @staticmethod
    def _get_local_ip() -> str:
        """실제 LAN 인터페이스 IP를 감지합니다."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return '127.0.0.1'

    @staticmethod
    def ip_short_id(ip: str) -> str:
        """IP 주소의 뒤 두 옥텟을 000.000 형식으로 반환합니다. (예: 192.168.0.121 → 000.121)"""
        parts = ip.split('.')
        if len(parts) == 4:
            return f"{int(parts[2]):03d}.{int(parts[3]):03d}"
        return "???.???"

    def start(self):
        """탐색(브로드캐스트 발송) ও 수신 스레드 동시 시작"""
        self.running = True
        
        # 1. 다른 피어의 브로드캐스트 수신 스레드
        self.listen_thread = threading.Thread(target=self._listen_for_peers, daemon=True)
        self.listen_thread.start()
        
        # 2. 내 존재를 알리는 브로드캐스트 발송 스레드
        self.broadcast_thread = threading.Thread(target=self._broadcast_presence, daemon=True)
        self.broadcast_thread.start()
        
        print(f"[Discovery] Peer Discovery 시작됨... (닉네임: {self.nickname}_{self.session_id})")

    def stop(self):
        self.running = False
        self.udp_socket.close()
        print("[Discovery] Peer Discovery 중지됨.")

    def _broadcast_presence(self):
        """주기적으로 네트워크에 내 정보를 브로드캐스트"""
        while self.running:
            try:
                # 매 루프마다 최신 속성값으로 메시지 생성 (닉네임 등 변경사항 반영)
                message = {
                    "type": "DISCOVERY",
                    "nickname": self.nickname,
                    "session_id": self.session_id,
                    "tcp_port": self.tcp_port,
                    "room_name": self.room_name,
                    "is_private": self.is_private
                }
                data = json.dumps(message).encode('utf-8')
                # 255.255.255.255 브로드캐스트 주소로 전송
                self.udp_socket.sendto(data, ('<broadcast>', self.port))
            except Exception as e:
                # 소켓 닫힘 등의 에러 무시
                pass
            time.sleep(self.broadcast_interval)

    def _listen_for_peers(self):
        """네트워크에서 다른 피어들의 DISCOVERY 메시지 수신"""
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                ip = addr[0]
                
                # 본인의 메시지도 캡처될 수 있으나, 처리 과정에서 본인의 session_id면 무시(또는 필터)할 수 있음
                
                try:
                    payload = json.loads(data.decode('utf-8'))
                    if payload.get("type") == "DISCOVERY":
                        nickname = payload.get("nickname", "Unknown")
                        session_id = payload.get("session_id", "0000")
                        tcp_port = payload.get("tcp_port", 0)
                        room_name = payload.get("room_name", "Lobby")
                        is_private = payload.get("is_private", False)
                        
                        # 내 자신의 디스커버리 패킷이면 리스트에 넣지 않음
                        if session_id == self.session_id:
                            continue

                        # 피어 리스트 갱신 (Key를 ip가 아닌 고유 session_id로 두어 로컬 다중 테스트 지원)
                        self.peers[session_id] = {
                            "ip": ip,
                            "tcp_port": tcp_port,
                            "nickname": nickname,
                            "room_name": room_name,
                            "is_private": is_private,
                            "last_seen": time.time()
                        }
                except json.JSONDecodeError:
                    pass
            except Exception as e:
                if self.running:
                    print(f"[Discovery] 수신 오류: {e}")

    def get_active_peers(self, timeout_seconds=10):
        """일정 시간(timeout_seconds) 이내에 신호가 있었던 활성 피어만 반환"""
        current_time = time.time()
        active = {}
        for sid, info in list(self.peers.items()):
            if current_time - info["last_seen"] <= timeout_seconds:
                active[sid] = info
            else:
                # 타임아웃된 유저는 리스트에서 제거 (오프라인 처리)
                del self.peers[sid]
        return active

if __name__ == "__main__":
    # 단독 테스트용 코드
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "TestUser"
    discovery = PeerDiscovery(nickname=name, tcp_port=50001, room_name="TestRoom", is_private=False)
    discovery.start()
    
    try:
        while True:
            time.sleep(3)
            print("--- 현재 접속 중인 피어 ---")
            for sid, info in discovery.get_active_peers().items():
                print(f"{info['ip']} : {info['nickname']} ({sid})")
    except KeyboardInterrupt:
        discovery.stop()
