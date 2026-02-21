import customtkinter as ctk
from frontend.views.user_list import UserListView
from frontend.views.chat_panel import ChatPanelView
from frontend.views.lobby import LobbyView

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

class LanChatApp(ctk.CTk):
    """메인 윈도우 레이아웃 설정 (프론트엔드 진입 뷰)"""
    def __init__(self):
        super().__init__()

        self.title("로컬 P2P 메신저 (Local LAN Chat)")
        self.geometry("900x600")
        self.minsize(700, 450)

        self.configure(fg_color="white")
        self.container = ctk.CTkFrame(self, fg_color="white")
        self.container.pack(fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.views = {}

        self.views["Lobby"] = LobbyView(self.container, lambda r,p: None, lambda r,p: None, lambda n,p: None)
        self.views["Lobby"].grid(row=0, column=0, sticky="nsew")

        self.chat_room_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        self.chat_room_frame.grid_rowconfigure(0, weight=1)
        self.chat_room_frame.grid_columnconfigure(0, weight=1)
        # 비율 조정: 좌측(유저리스트) 1 vs 우측(채팅창) 5
        self.chat_room_frame.grid_columnconfigure(1, weight=5)

        self.user_list_view = UserListView(self.chat_room_frame)
        self.user_list_view.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        self.chat_panel_view = ChatPanelView(self.chat_room_frame)
        self.chat_panel_view.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)

        self.views["ChatRoom"] = self.chat_room_frame
        self.views["ChatRoom"].grid(row=0, column=0, sticky="nsew")

        self.show_view("Lobby")

    def show_view(self, view_name):
        view = self.views.get(view_name)
        if view:
            view.tkraise()

    def start(self):
        self.mainloop()
