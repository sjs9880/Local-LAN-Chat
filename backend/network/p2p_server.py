import socket
import threading

class P2PServer:
    """수신용 단독 TCP 서버. 동적 포트 할당 기능을 포함합니다."""
    def __init__(self, host='0.0.0.0', start_port=50001, max_port=50100):
        self.host = host
        self.port = start_port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.running = False
        
        # 포트 동적 할당 로직 (Port Fallback)
        bound = False
        for p in range(start_port, max_port + 1):
            try:
                self.server_socket.bind((self.host, p))
                self.port = p
                bound = True
                break
            except OSError:
                continue
        
        if not bound:
            raise RuntimeError(f"사용 가능한 TCP 포트를 찾을 수 없습니다. ({start_port}~{max_port})")
            
        print(f"[TCP Server] 바인딩 성공 (Port: {self.port})")

    def start(self, connection_callback):
        """
        connection_callback: 연결이 들어왔을 때 호출될 함수
        형태: def callback(client_sock, addr): ...
        """
        self.running = True
        self.server_socket.listen(10)
        self.thread = threading.Thread(target=self._accept_loop, args=(connection_callback,), daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        try:
            self.server_socket.close()
        except:
            pass

    def _accept_loop(self, callback):
        while self.running:
            try:
                client_sock, addr = self.server_socket.accept()
                # 수락된 소켓은 상위 로직(콜백)으로 넘겨서 데이터 수신을 처리
                if callback:
                    threading.Thread(target=callback, args=(client_sock, addr), daemon=True).start()
            except Exception as e:
                if self.running:
                    print(f"[TCP Server] 수락 대기 오류: {e}")
