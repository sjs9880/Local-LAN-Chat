import os
import threading
import time
from tkinter import filedialog

from backend.core.engine import P2PEngine
from backend.utils.config import global_config


class UIController:
    """Bridge between UI views and backend engine callbacks."""

    def __init__(self, app_view, initial_engine):
        self.app_view = app_view
        self.engine = initial_engine

        self.app_view.chat_panel_view.send_btn.configure(command=self.on_send_chat)
        self.app_view.chat_panel_view.msg_entry.bind("<Return>", lambda _e: self.on_send_chat())
        self.app_view.chat_panel_view.on_attach_file_callback = self.on_attach_file
        self.app_view.chat_panel_view.on_attach_folder_callback = self.on_attach_folder
        self.app_view.user_list_view.leave_btn.configure(command=self.on_leave_room)

        lobby = self.app_view.views["Lobby"]
        lobby.on_create_room = self.on_create_room
        lobby.on_join_room = self.on_join_room
        lobby.on_save_config = self.on_save_config
        lobby.refresh_btn.configure(command=self.refresh_lobby_ui)
        lobby.set_config_values(global_config.nickname)

        self.bind_engine_callbacks()

    def bind_engine_callbacks(self):
        self.engine.on_peer_updated = self.handle_peer_update
        self.engine.on_message_received = self.handle_incoming_message
        self.engine.on_file_requested = self.handle_file_request
        self.engine.on_file_transfer_completed = self.handle_file_completed
        self.engine.on_chat_history_received = self.handle_chat_history

    def _switch_engine(self, new_room_name, password=""):
        self.engine.stop()

        nick = global_config.nickname if global_config.nickname else "Anonymous"
        new_engine = P2PEngine(nickname=nick, password=password, room_name=new_room_name)

        self.engine = new_engine
        self.bind_engine_callbacks()
        self.engine.start()

    def on_save_config(self, nickname):
        global_config.nickname = nickname
        global_config.save()

        self.engine.nickname = nickname
        self.engine.discovery.nickname = nickname

    def on_create_room(self, room_name, password):
        base_name = room_name
        active_peers = self.engine.discovery.get_active_peers()
        existing_rooms = {info.get("room_name") for info in active_peers.values() if info.get("room_name")}
        
        counter = 1
        while room_name in existing_rooms:
            room_name = f"{base_name} {counter}"
            counter += 1

        self._switch_engine(new_room_name=room_name, password=password)
        self.app_view.show_view("ChatRoom")
        self.app_view.chat_panel_view.set_room_name(room_name)
        self.app_view.chat_panel_view.set_encryption_status(self.engine.security.is_encrypted)
        self.app_view.chat_panel_view._clear_messages()
        self.app_view.chat_panel_view.add_message("System", f"Created room '{room_name}'.", is_me=True)

    def on_join_room(self, room_name, password):
        self._switch_engine(new_room_name=room_name, password=password)
        self.app_view.show_view("ChatRoom")
        self.app_view.chat_panel_view.set_room_name(room_name)
        self.app_view.chat_panel_view.set_encryption_status(self.engine.security.is_encrypted)
        self.app_view.chat_panel_view._clear_messages()
        self.app_view.chat_panel_view.add_message("System", f"Joined room '{room_name}'.", is_me=True)

    def on_leave_room(self):
        self._switch_engine(new_room_name="__LOBBY__", password="")
        self.app_view.show_view("Lobby")

    def refresh_lobby_ui(self):
        if self.engine.room_name == "__LOBBY__":
            self.handle_peer_update(self.engine.discovery.get_active_peers())

    def on_send_chat(self):
        msg = self.app_view.chat_panel_view.msg_entry.get().strip()
        if not msg:
            return

        self.app_view.chat_panel_view.msg_entry.delete(0, "end")
        self.app_view.chat_panel_view.add_message(self.engine.nickname, msg, is_me=True)
        self.app_view.chat_panel_view.scroll_to_bottom()

        def send_task():
            try:
                success = self.engine.broadcast_chat_message(msg)
                if not success:
                    self.app_view.after(
                        0,
                        lambda: self.app_view.chat_panel_view.add_message(
                            "System",
                            "Send failed: no available peers in the current room.",
                            is_me=True,
                        ),
                    )
            except Exception as e:
                print(f"[UIController] send_task error: {type(e).__name__}: {e}")

        threading.Thread(target=send_task, daemon=True).start()

    def handle_peer_update(self, peers: dict):
        if self.engine.room_name == "__LOBBY__":
            rooms = {}
            for info in peers.values():
                room_name = info.get("room_name", "")
                if not room_name or room_name == "__LOBBY__":
                    continue
                if room_name not in rooms:
                    rooms[room_name] = {"is_private": info.get("is_private", False), "count": 1}
                else:
                    rooms[room_name]["count"] += 1

            lobby_view = self.app_view.views["Lobby"]
            self.app_view.after(0, lambda: lobby_view.render_room_list(rooms))
        else:
            my_room = self.engine.room_name
            room_peers = {sid: info for sid, info in peers.items() if info.get("room_name") == my_room}
            my_session = self.engine.discovery.session_id
            my_nickname = self.engine.nickname
            my_short_id = self.engine.discovery.ip_short_id(self.engine.discovery.local_ip)
            self.app_view.after(0, lambda: self.app_view.user_list_view.update_users(room_peers, my_session, my_nickname, my_short_id))

    def handle_incoming_message(self, packet: dict):
        sender = packet.get("sender_nickname", "Unknown")
        sender_short_id = packet.get("sender_short_id", "")
        if sender_short_id:
            sender = f"{sender} #{sender_short_id}"
            
        content = packet.get("content", "")
        timestamp = packet.get("timestamp")

        def update_ui():
            msg_type = packet.get("type")
            if msg_type == "FILE_REQ":
                file_name = packet.get("file_name", "file")
                file_size = packet.get("file_size", 0)
                req_id = packet.get("req_id", "")

                on_download_clicked = self._create_download_handler(
                    req_id, packet.get("sender_session", ""), file_name
                )

                btn_funcs = self.app_view.chat_panel_view.add_file_message(
                    sender=sender,
                    file_name=file_name,
                    file_size=file_size,
                    timestamp=timestamp,
                    on_download=on_download_clicked,
                    is_me=False,
                )
                if not hasattr(self, "_file_btn_restorers"):
                    self._file_btn_restorers = {}
                self._file_btn_restorers[req_id] = btn_funcs

            elif msg_type == "FILE_CANCEL":
                req_id = packet.get("req_id", "")
                if hasattr(self, "_file_btn_restorers") and req_id in self._file_btn_restorers:
                    self._file_btn_restorers[req_id]["expire"]()
                    del self._file_btn_restorers[req_id]

            elif msg_type == "FILE_DOWNLOADED":
                req_id = packet.get("req_id", "")
                downloader_nick = packet.get("downloader_nickname", "Unknown")
                downloader_short = packet.get("downloader_short_id", "")
                if hasattr(self, "_file_btn_restorers") and req_id in self._file_btn_restorers:
                    self._file_btn_restorers[req_id]["update_dl"](downloader_nick, downloader_short)

            else:
                self.app_view.chat_panel_view.add_message(sender, content, is_me=False, timestamp=timestamp)

            self.app_view.chat_panel_view.scroll_to_bottom()

        self.app_view.after(0, update_ui)

    def on_attach_file(self):
        file_paths = filedialog.askopenfilenames(title="Select files to share")
        if not file_paths:
            return

        def req_task():
            success, meta, req_id = self.engine.broadcast_file_request(list(file_paths), speed_limit_bytes=0)
            if success and meta:
                def render_me():
                    btn_funcs = self.app_view.chat_panel_view.add_file_message(
                        sender=self.engine.nickname,
                        file_name=meta.get("name", "file"),
                        file_size=meta.get("size", 0),
                        timestamp=time.time(),
                        on_download=None,
                        on_cancel_share=lambda: self.engine.cancel_file_sharing(req_id),
                        is_me=True,
                    )
                    if not hasattr(self, "_file_btn_restorers"):
                        self._file_btn_restorers = {}
                    self._file_btn_restorers[req_id] = btn_funcs

                self.app_view.after(0, render_me)
            else:
                self.app_view.after(
                    0,
                    lambda: self.app_view.chat_panel_view.add_message(
                        "System",
                        "File share request failed.",
                        is_me=True,
                    ),
                )

        threading.Thread(target=req_task, daemon=True).start()

    def on_attach_folder(self):
        folder_path = filedialog.askdirectory(title="공유할 폴더 선택")
        if not folder_path:
            return

        def req_task():
            success, meta, req_id = self.engine.broadcast_file_request([folder_path], speed_limit_bytes=0)
            if success and meta:
                def render_me():
                    btn_funcs = self.app_view.chat_panel_view.add_file_message(
                        sender=self.engine.nickname,
                        file_name=meta.get("name", "Archive.zip"),
                        file_size=meta.get("size", 0),
                        timestamp=time.time(),
                        on_download=None,
                        on_cancel_share=lambda: self.engine.cancel_file_sharing(req_id),
                        is_me=True,
                    )
                    if not hasattr(self, "_file_btn_restorers"):
                        self._file_btn_restorers = {}
                    self._file_btn_restorers[req_id] = btn_funcs

                self.app_view.after(0, render_me)
            else:
                self.app_view.after(
                    0,
                    lambda: self.app_view.chat_panel_view.add_message(
                        "System",
                        "Folder share request failed.",
                        is_me=True,
                    ),
                )

        threading.Thread(target=req_task, daemon=True).start()

    def _create_download_handler(self, req_id: str, sender_session: str, file_name: str):
        """다운로드 버튼 콜백을 생성해 반환합니다."""
        def on_download_clicked():
            peers = self.engine.discovery.get_active_peers()
            if sender_session not in peers:
                return False

            dl_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            temp_dir = os.path.join(dl_dir, ".temp_lan_chat")
            os.makedirs(temp_dir, exist_ok=True)
            temp_save_path = os.path.join(temp_dir, f"temp_{req_id}.part")

            success = self.engine.accept_file_transfer(req_id, temp_save_path)
            if success:
                self.app_view.chat_panel_view.add_message(
                    "System",
                    f"[{file_name}] Temporary download started...",
                    is_me=True,
                )
            return success

        return on_download_clicked

    def handle_file_request(self, req_id: str, packet: dict):
        pass

    def handle_chat_history(self, messages: list):
        sorted_msgs = sorted(messages, key=lambda x: x.get("timestamp", 0))

        def update_ui():
            active_peer_ids = set(self.engine.discovery.get_active_peers().keys())
            my_session = self.engine.discovery.session_id
            my_nickname = (self.engine.nickname or "").strip()
            my_short_id = self.engine.discovery.ip_short_id(self.engine.discovery.local_ip)

            for msg in sorted_msgs:
                sender = msg.get("sender_nickname", "Unknown")
                sender_short_id_val = (msg.get("sender_short_id", "") or "").strip()
                if sender_short_id_val:
                    sender = f"{sender} #{sender_short_id_val}"
                    
                content = msg.get("content", "")
                timestamp = msg.get("timestamp")
                sender_session = msg.get("sender_session", "")
                sender_nickname = (msg.get("sender_nickname", "") or "").strip()
                sender_short_id = (msg.get("sender_short_id", "") or "").strip()
                is_me = sender_session == my_session
                if not is_me and sender_short_id:
                    is_me = (
                        bool(my_nickname)
                        and sender_nickname == my_nickname
                        and sender_short_id == my_short_id
                    )
                elif not is_me:
                    # Backward compatibility for old history entries without sender_short_id.
                    is_me = (
                        bool(my_nickname)
                        and sender_nickname == my_nickname
                        and sender_session not in active_peer_ids
                    )
                msg_type = msg.get("type", "MESSAGE")

                if msg_type == "FILE_REQ":
                    file_name = msg.get("file_name", "file")
                    file_size = msg.get("file_size", 0)
                    req_id = msg.get("req_id", "")

                    on_cancel_share = (
                        (lambda r=req_id: self.engine.cancel_file_sharing(r)) if is_me else None
                    )

                    btn_funcs = self.app_view.chat_panel_view.add_file_message(
                        sender=sender,
                        file_name=file_name,
                        file_size=file_size,
                        timestamp=timestamp,
                        on_download=self._create_download_handler(req_id, msg.get("sender_session", ""), file_name),
                        on_cancel_share=on_cancel_share,
                        is_me=is_me,
                    )

                    if not hasattr(self, "_file_btn_restorers"):
                        self._file_btn_restorers = {}
                    self._file_btn_restorers[req_id] = btn_funcs

                elif msg_type == "FILE_CANCEL":
                    req_id = msg.get("req_id", "")
                    if hasattr(self, "_file_btn_restorers") and req_id in self._file_btn_restorers:
                        self._file_btn_restorers[req_id]["expire"]()
                        del self._file_btn_restorers[req_id]

                elif msg_type == "FILE_DOWNLOADED":
                    req_id = msg.get("req_id", "")
                    dn_nick = msg.get("downloader_nickname", "Unknown")
                    dn_short = msg.get("downloader_short_id", "")
                    if hasattr(self, "_file_btn_restorers") and req_id in self._file_btn_restorers:
                        self._file_btn_restorers[req_id]["update_dl"](dn_nick, dn_short)

                else:
                    self.app_view.chat_panel_view.add_message(sender, content, is_me=is_me, timestamp=timestamp)

            self.app_view.chat_panel_view.scroll_to_bottom()

        self.app_view.after(0, update_ui)

    def handle_file_completed(self, req_id: str, final_path: str):
        def save_as_task():
            import shutil

            base_name = os.path.basename(final_path)
            original_name = None
            if req_id in self.engine.active_file_requests:
                original_name = self.engine.active_file_requests[req_id].get("file_name")
            if not original_name:
                original_name = base_name.replace(".part", "")

            initial_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            suggested_ext = ""
            if "." in original_name:
                suggested_ext = f".{original_name.split('.')[-1]}"

            filetypes = [("All Files", "*.*")]
            if suggested_ext:
                filetypes.insert(0, (f"{suggested_ext} files", f"*{suggested_ext}"))

            save_path = filedialog.asksaveasfilename(
                title=f"Save as '{original_name}'",
                initialdir=initial_dir,
                initialfile=original_name,
                filetypes=filetypes,
            )

            temp_dir = os.path.dirname(os.path.abspath(final_path))

            if save_path:
                try:
                    if os.path.exists(save_path):
                        if os.path.isdir(save_path):
                            shutil.rmtree(save_path)
                        else:
                            os.remove(save_path)
                    shutil.move(final_path, save_path)
                    self.app_view.chat_panel_view.add_message("System", f"Download complete:\n{save_path}", is_me=True)
                except Exception as e:
                    self.app_view.chat_panel_view.add_message("System", f"Save failed: {e}", is_me=True)
            else:
                try:
                    if os.path.isdir(final_path):
                        shutil.rmtree(final_path)
                    else:
                        os.remove(final_path)
                    self.app_view.chat_panel_view.add_message("System", "Download canceled.", is_me=True)
                except Exception:
                    pass

            try:
                os.rmdir(temp_dir)  # 비어 있을 때만 제거 (다른 다운로드 진행 중이면 자동으로 실패)
            except OSError:
                pass

            if hasattr(self, "_file_btn_restorers") and req_id in self._file_btn_restorers:
                try:
                    self._file_btn_restorers[req_id]["restore"]()
                except Exception as e:
                    print(f"[UIController] button restore error: {e}")
                finally:
                    del self._file_btn_restorers[req_id]

            self.app_view.chat_panel_view.scroll_to_bottom()

        self.app_view.after(0, save_as_task)
