import customtkinter as ctk
import tkinter as tk
import time

# 말풍선 색상
BUBBLE_OUT_BG  = "#1f538d"   # 내 메시지 (iMessage 스타일 파란색)
BUBBLE_OUT_FG  = "#ffffff"   # 내 메시지 텍스트
BUBBLE_IN_BG   = "#F2F2F7"   # 상대 메시지 (투명하고 밝은 톤의 모던한 회색)
BUBBLE_IN_FG   = "#000000"   # 상대 메시지 텍스트
TIME_OUT_COLOR = "#8CB9FF"   # 내 메시지 시간
TIME_IN_COLOR  = "#8E8E93"   # 상대 메시지 시간
NAME_COLOR     = "#8E8E93"   # 닉네임 색상

class ChatPanelView(ctk.CTkFrame):
    """우측 패널: 말풍선이 출력되는 텍스트 채팅창 및 입력 뷰"""
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="white", **kwargs)

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 상단 타이틀
        self.top_frame = ctk.CTkFrame(self, height=40, fg_color="transparent")
        self.top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        self.title_label = ctk.CTkLabel(self.top_frame, text="전체 네트워크 채널", font=("Arial", 16, "bold"))
        self.title_label.pack(side="left")
        self.warning_label = ctk.CTkLabel(
            self.top_frame,
            text="⚠ 암호화되지 않은 세션 — 모든 대화 및 파일 내용이 패킷에 노출됩니다",
            font=("Arial", 11),
            text_color="#FF6B00",
        )
        # 기본적으로 숨김 (방 진입 시 set_encryption_status로 제어)

        # 중앙 스크롤 뷰
        self.chat_scroll = ctk.CTkScrollableFrame(self, fg_color="white")
        self.chat_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)

        # 하단 입력 영역
        self.input_frame = ctk.CTkFrame(self, fg_color="white")
        self.input_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(5, 10))
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.msg_entry = ctk.CTkEntry(self.input_frame, placeholder_text="메시지를 입력하세요...")
        self.msg_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self.send_btn = ctk.CTkButton(self.input_frame, text="전송", width=60)
        self.send_btn.grid(row=0, column=1)

        self.attach_btn = ctk.CTkButton(self.input_frame, text="공유", width=70, command=self.toggle_share_menu)
        self.attach_btn.grid(row=0, column=2, padx=(5, 0))

        self.on_attach_file_callback = None
        self.on_attach_folder_callback = None
        self.share_menu = None
        self.share_menu_active = False

    def toggle_share_menu(self):
        """공유 버튼 클릭 시 파일/폴더 선택 플로팅 메뉴 표시 토글"""
        if self.share_menu_active:
            self._close_share_menu()
            return

        self.share_menu = ctk.CTkFrame(self, fg_color="white", corner_radius=6, border_width=1, border_color="gray70")
        
        btn_file = ctk.CTkButton(self.share_menu, text="파일", width=70, height=28, fg_color="transparent", 
                                 text_color="black", hover_color="gray90",
                                 command=self._click_file)
        btn_file.pack(pady=(4, 2), padx=4)
        
        btn_folder = ctk.CTkButton(self.share_menu, text="폴더", width=70, height=28, fg_color="transparent", 
                                   text_color="black", hover_color="gray90",
                                   command=self._click_folder)
        btn_folder.pack(pady=(2, 4), padx=4)
        
        # 입력 프레임 바로 위 우측에 배치 (위치 미세 조정)
        self.share_menu.place(relx=1.0, rely=1.0, x=-15, y=-55, anchor="se")
        self.share_menu_active = True
        
        if not getattr(self, "_click_bound", False):
            self.winfo_toplevel().bind("<Button-1>", self._on_any_click, add="+")
            self._click_bound = True

    def _on_any_click(self, event):
        if not self.share_menu_active or not self.share_menu or not self.share_menu.winfo_exists():
            return
            
        widget_str = str(event.widget)
        if widget_str.startswith(str(self.share_menu)) or widget_str.startswith(str(self.attach_btn)):
            return
            
        self._close_share_menu()

    def _close_share_menu(self):
        if self.share_menu and self.share_menu.winfo_exists():
            self.share_menu.destroy()
            self.share_menu = None
        self.share_menu_active = False

    def _click_file(self):
        self._close_share_menu()
        if self.on_attach_file_callback:
            self.on_attach_file_callback()

    def _click_folder(self):
        self._close_share_menu()
        if self.on_attach_folder_callback:
            self.on_attach_folder_callback()

    def set_room_name(self, room_name: str):
        """방 이름 텍스트 설정"""
        self.title_label.configure(text=room_name)

    def set_encryption_status(self, is_encrypted: bool):
        """암호화 여부에 따라 경고 레이블 표시/숨김"""
        if is_encrypted:
            self.warning_label.pack_forget()
        else:
            self.warning_label.pack(side="left", padx=(12, 0))

    def add_message(self, sender: str, msg: str, is_me: bool = False, timestamp: float = None):
        """채팅창에 메시지 말풍선을 추가합니다."""
        time_str = time.strftime("%H:%M", time.localtime(timestamp if timestamp else time.time()))
        chat_bg = self.chat_scroll.cget("fg_color") if isinstance(self.chat_scroll.cget("fg_color"), str) else "white"

        # 메시지 전체 행 컨테이너
        outer = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        outer.pack(fill="x", pady=4, padx=8)

        if is_me:
            # 내 메시지: 오른쪽 정렬, 닉네임 없음
            bubble = ctk.CTkFrame(outer, fg_color=BUBBLE_OUT_BG, corner_radius=12)
            bubble.pack(side="right", anchor="e")

            content = tk.Text(
                bubble,
                bg=BUBBLE_OUT_BG, fg=BUBBLE_OUT_FG,
                relief="flat", bd=0, highlightthickness=0,
                wrap="word", font=("Arial", 13),
                width=35, height=1,
                padx=0, pady=0,
                selectbackground="#4a90d9",
                selectforeground="white",
            )
            content.insert("1.0", msg)
            content.config(state="disabled")
            content.pack(anchor="e", padx=12, pady=(8, 2))
            self._auto_height(content)
            self._forward_scroll(content)

            ctk.CTkLabel(bubble, text=time_str, text_color=TIME_OUT_COLOR, font=("Arial", 10)).pack(
                anchor="e", padx=10, pady=(0, 6)
            )

        else:
            # 상대 메시지: 닉네임을 말풍선 밖 상단 좌측에 표시
            ctk.CTkLabel(outer, text=sender, text_color=NAME_COLOR, font=("Arial", 11, "bold")).pack(
                anchor="w", padx=2, pady=(0, 2)
            )

            bubble = ctk.CTkFrame(outer, fg_color=BUBBLE_IN_BG, corner_radius=12)
            bubble.pack(side="left", anchor="w")

            content = tk.Text(
                bubble,
                bg=BUBBLE_IN_BG, fg=BUBBLE_IN_FG,
                relief="flat", bd=0, highlightthickness=0,
                wrap="word", font=("Arial", 13),
                width=35, height=1,
                padx=0, pady=0,
                selectbackground="#1f538d",
                selectforeground="white",
            )
            content.insert("1.0", msg)
            content.config(state="disabled")
            content.pack(anchor="w", padx=12, pady=(8, 2))
            self._auto_height(content)
            self._forward_scroll(content)

            ctk.CTkLabel(bubble, text=time_str, text_color=TIME_IN_COLOR, font=("Arial", 10)).pack(
                anchor="e", padx=10, pady=(0, 6)
            )

    def add_file_message(self, sender: str, file_name: str, file_size: int, timestamp: float,
                         on_download: callable = None, on_cancel_share: callable = None, is_me: bool = False):
        """커스텀 파일 전송 메시지 말풍선과 다운로드/취소 버튼을 렌더링합니다."""
        time_str = time.strftime("%H:%M", time.localtime(timestamp if timestamp else time.time()))
        size_mb = file_size / (1024 * 1024)

        outer = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        outer.pack(fill="x", pady=4, padx=8)

        if not is_me:
            ctk.CTkLabel(outer, text=sender, text_color=NAME_COLOR, font=("Arial", 11, "bold")).pack(
                anchor="w", padx=2, pady=(0, 2)
            )
            side_align, anchor_align, bg_color, fg_color = "left", "w", BUBBLE_IN_BG, BUBBLE_IN_FG
        else:
            side_align, anchor_align, bg_color, fg_color = "right", "e", BUBBLE_OUT_BG, BUBBLE_OUT_FG

        bubble = ctk.CTkFrame(outer, fg_color=bg_color, corner_radius=12)
        bubble.pack(side=side_align, anchor=anchor_align)

        # 상단 아이콘 및 타이틀
        top_inner = ctk.CTkFrame(bubble, fg_color="transparent")
        top_inner.pack(fill="x", padx=12, pady=(8, 2))
        
        icon_lbl = ctk.CTkLabel(top_inner, text="📁", font=("Arial", 20), text_color=fg_color)
        icon_lbl.pack(side="left", padx=(0, 10))
        
        info_str = f"{file_name}\n{size_mb:.2f} MB"
        info_lbl = ctk.CTkLabel(top_inner, text=info_str, font=("Arial", 13), text_color=fg_color, justify="left")
        info_lbl.pack(side="left")

        # 다운로더 정보 표시 영역 (초기엔 타이틀 숨김)
        downloader_frm = ctk.CTkFrame(bubble, fg_color="transparent")
        downloader_frm.pack(fill="x", padx=12, pady=(0, 2))
        dl_text_var = tk.StringVar(value="")
        time_color = TIME_OUT_COLOR if is_me else TIME_IN_COLOR
        dl_lbl = ctk.CTkLabel(downloader_frm, textvariable=dl_text_var, font=("Arial", 10, "italic"), text_color=time_color, justify="left")
        dl_lbl.pack(anchor="w")
        
        downloaders = set()  # 다운로더 중복 방지 캐시

        # 버튼 영역
        btn_frame = ctk.CTkFrame(bubble, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=(5, 8))
        
        dl_btn = ctk.CTkButton(btn_frame, text="다운로드", height=28)
        dl_btn.pack(side="left", fill="x", expand=True)

        if not is_me:
            dl_btn.configure(fg_color="#2FA572", hover_color="#106A43")
            def handle_click():
                if on_download:
                    success = on_download()
                    if success:
                        dl_btn.configure(state="disabled", text="다운로드 중...")
                    else:
                        dl_btn.configure(text="연결 끊김", fg_color="#D9534F", hover_color="#C9302C")
            dl_btn.configure(command=handle_click)
        else:
            # 송신자용: 공유 중단 버튼 활성화
            dl_btn.configure(text="공유 중단", fg_color="#D9534F", hover_color="#C9302C")
            def handle_cancel():
                if on_cancel_share:
                    on_cancel_share()
                dl_btn.configure(state="disabled", text="중단 완료", fg_color="gray")
            dl_btn.configure(command=handle_cancel)

        time_color = TIME_OUT_COLOR if is_me else TIME_IN_COLOR
        ctk.CTkLabel(bubble, text=time_str, text_color=time_color, font=("Arial", 10)).pack(
            anchor="e", padx=10, pady=(0, 6)
        )

        self.scroll_to_bottom()
        
        def restore_btn():
            if not is_me and dl_btn.winfo_exists() and dl_btn.cget("text") != "만료됨":
                dl_btn.configure(state="normal", text="재다운로드", fg_color="#2FA572", hover_color="#106A43")

        def expire_btn():
            if dl_btn.winfo_exists():
                dl_btn.configure(state="disabled", text="만료됨", fg_color="gray")
                
        def update_dl_info(nickname: str, short_id: str):
            info_str = f"{nickname}#{short_id}"
            if info_str not in downloaders:
                downloaders.add(info_str)
                prefix = "받은 사람: "
                dl_text_var.set(prefix + ", ".join(downloaders))
                
        return {
            "restore": restore_btn,
            "expire": expire_btn,
            "update_dl": update_dl_info
        }

    def _auto_height(self, text_widget: tk.Text):
        """텍스트 내용에 맞게 높이를 자동 조정합니다."""
        text_widget.update_idletasks()
        lines = int(text_widget.index("end-1c").split(".")[0])
        text_widget.config(height=max(1, lines))

    def _forward_scroll(self, text_widget: tk.Text):
        """텍스트 위젯의 마우스 휠 이벤트를 채팅 스크롤로 전달합니다."""
        canvas = self.chat_scroll._parent_canvas
        text_widget.bind("<MouseWheel>", lambda e: canvas.event_generate("<MouseWheel>", delta=e.delta))
        text_widget.bind("<Button-4>",   lambda e: canvas.event_generate("<Button-4>"))
        text_widget.bind("<Button-5>",   lambda e: canvas.event_generate("<Button-5>"))

    def scroll_to_bottom(self):
        """UI 위젯 크기 계산이 완료된 후 아주 약간의 딜레이를 두고 스크롤을 가장 밑으로 이동시킵니다."""
        # 렌더링 이벤트 루프 처리가 완료되도록 대기 (50ms)
        self.after(50, lambda: self.chat_scroll._parent_canvas.yview_moveto(1.0))

    def _clear_messages(self):
        """이전 대화 내역 전체 삭제 (방 이동 시 사용)"""
        for widget in self.chat_scroll.winfo_children():
            widget.destroy()
