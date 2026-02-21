import customtkinter as ctk

class LobbyView(ctk.CTkFrame):
    """로비: 현재 참여 가능한 P2P 세션(채팅방) 리스트 및 방 만들기 뷰"""
    def __init__(self, master, on_create_room, on_join_room, on_save_config, **kwargs):
        super().__init__(master, fg_color="white", **kwargs)

        self.on_create_room = on_create_room
        self.on_join_room   = on_join_room
        self.on_save_config = on_save_config

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1) # 좌측 패널 (방 목록)
        self.grid_columnconfigure(1, weight=0) # 우측 패널 (고정 너비)

        # ==========================================
        # 좌측 패널: 방 목록 영역
        # ==========================================
        left_panel = ctk.CTkFrame(self, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left_panel.grid_rowconfigure(1, weight=1)
        left_panel.grid_columnconfigure(0, weight=1)

        # 좌측 상단: 타이틀 및 새로고침 버튼
        left_title_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        left_title_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        left_title_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left_title_frame, text="세션 리스트", font=("Arial", 18, "bold")).grid(row=0, column=0, sticky="w")
        
        self.refresh_btn = ctk.CTkButton(left_title_frame, text="새로고침", width=120)
        self.refresh_btn.grid(row=0, column=1, sticky="e")

        # 좌측 하단: 방 목록 스크롤 뷰
        self.room_scroll = ctk.CTkScrollableFrame(left_panel, fg_color="white")
        self.room_scroll.grid(row=1, column=0, sticky="nsew")

        # ==========================================
        # 우측 패널: 설정 및 방 개설 영역
        # ==========================================
        right_panel = ctk.CTkFrame(self, fg_color="white", width=250)
        right_panel.grid(row=0, column=1, sticky="ns", padx=(5, 10), pady=10)
        # 너비 고정을 위해 grid_propagate 방지 및 최소 크기 설정은 하지 않고 width 속성 사용 활용

        # ------ 우측 상단: 내 닉네임 설정 ------
        ctk.CTkLabel(right_panel, text="닉네임 설정", font=("Arial", 14, "bold")).pack(pady=(20, 5), padx=15, anchor="w")
        
        self.nickname_entry = ctk.CTkEntry(right_panel, placeholder_text="닉네임 입력")
        self.nickname_entry.pack(pady=5, padx=15, fill="x")

        self.save_cfg_btn = ctk.CTkButton(right_panel, text="저장", command=self._handle_save_config)
        self.save_cfg_btn.pack(pady=(5, 20), padx=15, fill="x")

        # ------ 우측 하단: 방 개설하기 ------
        ctk.CTkLabel(right_panel, text="세션 생성", font=("Arial", 14, "bold")).pack(pady=(10, 5), padx=15, anchor="w")

        self.new_room_name = ctk.CTkEntry(right_panel, placeholder_text="세션 이름")
        self.new_room_name.pack(pady=5, padx=15, fill="x")

        self.new_room_pw = ctk.CTkEntry(right_panel, placeholder_text="비밀번호 (선택)", show="*")
        self.new_room_pw.pack(pady=5, padx=15, fill="x")

        self.create_btn = ctk.CTkButton(right_panel, text="세션 만들기 (+)", command=self._handle_create_room)
        self.create_btn.pack(pady=15, padx=15, fill="x")

    def _handle_save_config(self):
        nick = self.nickname_entry.get().strip()
        if nick:
            self.on_save_config(nick)

    def _handle_create_room(self):
        r_name = self.new_room_name.get().strip() or "Local LAN Chat Room"
        r_pw   = self.new_room_pw.get().strip()
        self.on_create_room(r_name, r_pw)

    def render_room_list(self, rooms: dict):
        """rooms = { "방이름": {"is_private": bool, "count": int} } 형식의 집계 데이터"""
        for widget in self.room_scroll.winfo_children():
            widget.destroy()

        if not rooms:
            ctk.CTkLabel(self.room_scroll, text="현재 네트워크에 개설된 방이 없습니다.", text_color="gray").pack(pady=20)
            return

        for room_name, info in rooms.items():
            frame = ctk.CTkFrame(self.room_scroll)
            frame.pack(fill="x", pady=5, padx=5)

            lock_str = "🔒(비공개)" if info["is_private"] else "🔓(공개)"
            text_str = f"[{room_name}] - {lock_str} / 참여인원: {info['count']}명 탐지됨"

            lbl = ctk.CTkLabel(frame, text=text_str, font=("Arial", 14))
            lbl.pack(side="left", padx=10, pady=10)

            btn = ctk.CTkButton(frame, text="참여하기", width=80,
                                command=lambda r=room_name, p=info["is_private"]: self._handle_join_btn(r, p))
            btn.pack(side="right", padx=10, pady=10)

    def _handle_join_btn(self, room_name, is_private):
        if is_private:
            dialog = ctk.CTkInputDialog(text=f"'{room_name}' 방의 비밀번호를 입력하세요:", title="비공개 세션 입장")
            pw = dialog.get_input()
            if pw is not None:
                self.on_join_room(room_name, pw.strip())
        else:
            self.on_join_room(room_name, "")

    def set_config_values(self, nickname):
        self.nickname_entry.delete(0, "end")
        self.nickname_entry.insert(0, nickname)
