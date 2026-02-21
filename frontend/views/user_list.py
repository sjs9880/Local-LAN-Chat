import customtkinter as ctk
from backend.network.discovery import PeerDiscovery


class UserListView(ctk.CTkFrame):
    """좌측 패널: 접속 중인 로컬 네트워크 사용자 리스트"""
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="white", **kwargs)

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 상단 타이틀
        self.title_label = ctk.CTkLabel(self, text="접속자 목록", font=("Arial", 16, "bold"))
        self.title_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")

        # 유저 목록 스크롤 영역
        self.scrollable_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scrollable_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=(0, 5))

        # 방 나가기 (로비로 돌아가기) 버튼
        self.leave_btn = ctk.CTkButton(self, text="방 나가기", fg_color="#D9534F", hover_color="#C9302C")
        self.leave_btn.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")

    def update_users(self, peers: dict, my_session_id: str = "", my_nickname: str = "", my_short_id: str = ""):
        """P2PEngine에서 전달받은 피어 딕셔너리를 기반으로 목록 뷰를 갱신합니다."""
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        if my_nickname and my_short_id:
            btn = ctk.CTkButton(
                self.scrollable_frame,
                text=f"🔵 {my_nickname} #{my_short_id} (나)",
                anchor="w",
                fg_color="transparent",
                text_color="#1a1a1a",
                hover_color="#f2f2f7"
            )
            btn.pack(fill="x", pady=2, padx=2)

        for session_id, info in peers.items():
            if session_id == my_session_id:
                continue

            nickname = info.get("nickname", "Unknown")
            ip = info.get("ip", "")
            short_id = PeerDiscovery.ip_short_id(ip)

            btn = ctk.CTkButton(
                self.scrollable_frame,
                text=f"🟢 {nickname} #{short_id}",
                anchor="w",
                fg_color="transparent",
                text_color="#1a1a1a",
                hover_color="#f2f2f7"
            )
            btn.pack(fill="x", pady=2, padx=2)

