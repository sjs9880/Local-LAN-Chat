import os
from backend.core.engine import P2PEngine
from frontend.app import LanChatApp
from frontend.controllers.ui_controller import UIController
from backend.utils.config import global_config

def main():
    # 1. 환경설정 로드 확인 (global_config 객체가 자동 수행함)
    if not global_config.nickname:
        global_config.nickname = "Anonymous"
        
    # 2. 메인 윈도우 생성
    app = LanChatApp()
    
    # 3. 로비 상태용 P2PEngine 생성 및 네트워크 시작
    # (로비 상태에서는 room_name="__LOBBY__" 로 두어 실제 방에 속하지 않게 하며 정보를 주고받음)
    engine = P2PEngine(nickname=global_config.nickname, password="", room_name="__LOBBY__")
    engine.start()
    
    # 4. 프론트엔드 - 백엔드 링커 연결
    controller = UIController(app, engine)
    
    # 앱 종료 시 완전한 리소스 정리
    def on_close():
        if controller.engine:
            controller.engine.stop()
        app.destroy()
        
    app.protocol("WM_DELETE_WINDOW", on_close)
    
    # 5. 앱 구동 (초기 뷰 Lobby 노출)
    app.start()

if __name__ == "__main__":
    main()
