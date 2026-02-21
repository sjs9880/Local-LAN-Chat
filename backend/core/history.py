import threading
import time
from typing import List, Dict

class VectorClock:
    """피어 간 이벤트 순서를 결정짓는 논리적 클락"""
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.clock: Dict[str, int] = {node_id: 0}
        self.lock = threading.Lock()

    def increment(self):
        with self.lock:
            self.clock[self.node_id] = self.clock.get(self.node_id, 0) + 1
            return self.clock.copy()  # get_clock() 호출 시 같은 lock 재진입으로 데드락 발생하므로 직접 복사

    def merge(self, other_clock: Dict[str, int]):
        """타 피어의 클락과 병합하여 최대값으로 동기화"""
        with self.lock:
            for node, count in other_clock.items():
                self.clock[node] = max(self.clock.get(node, 0), count)

    def get_clock(self) -> Dict[str, int]:
        with self.lock:
            return self.clock.copy()


class ChatHistoryManager:
    """P2P 대화 일지 및 동기화를 관리하는 모듈"""
    def __init__(self, local_session_id: str):
        self.local_session_id = local_session_id
        self.vector_clock = VectorClock(local_session_id)
        self.messages: List[dict] = []
        self._seen_ids: set = set()
        self.lock = threading.Lock()

    def add_local_message(self, sender_nickname: str, content: str = "", msg_type: str = "MESSAGE", extra: dict = None) -> dict:
        """내가 전송하는 새 메시지(또는 이벤트)를 기록하고 클락을 증가시킴"""
        vclock = self.vector_clock.increment()
        msg_obj = {
            "type": msg_type,
            "msg_id": f"{self.local_session_id}_{vclock[self.local_session_id]}",
            "sender_session": self.local_session_id,
            "sender_nickname": sender_nickname,
            "content": content,
            "timestamp": time.time(),
            "vclock": vclock
        }
        if extra:
            msg_obj.update(extra)
            
        with self.lock:
            self.messages.append(msg_obj)
            self._seen_ids.add(msg_obj["msg_id"])
        return msg_obj

    def receive_remote_message(self, msg_obj: dict) -> bool:
        """다른 피어로부터 수신한 메시지를 기록하고 클락을 동기화함"""
        msg_id = msg_obj.get("msg_id")
        remote_vclock = msg_obj.get("vclock", {})
        
        with self.lock:
            # 중복 수신 방지 — O(1) set 조회
            if msg_id in self._seen_ids:
                return False

            self.messages.append(msg_obj)
            self._seen_ids.add(msg_id)
            # 수신 시점 기준으로 정렬 (실제론 Vector Clock 대조나 Timestamp 기반 정렬 등 활용)
            self.messages.sort(key=lambda x: x.get("timestamp", 0))
            
        # 벡터 클락 동기화
        if remote_vclock:
            self.vector_clock.merge(remote_vclock)
            
        return True

    def get_history_snapshot(self) -> List[dict]:
        with self.lock:
            return self.messages.copy()
