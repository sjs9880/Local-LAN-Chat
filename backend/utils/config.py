import os
import json

CONFIG_FILE = "config.json"

class AppConfig:
    """사용자가 로비에서 입력한 로컬 환경설정을 저장/불러오는 유틸리티"""
    def __init__(self):
        self.nickname = ""
        self.port = 50000
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.nickname = data.get("nickname", self.nickname)
                    self.port = data.get("port", self.port)
            except Exception as e:
                print(f"[Config] 설정 파일 읽기 오류: {e}")

    def save(self):
        data = {
            "nickname": self.nickname,
            "port": self.port
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[Config] 설정 파일 저장 오류: {e}")

# 전역 싱글톤 설정 객체
global_config = AppConfig()
