# -*- coding: utf-8 -*-
"""配置读写：默认配置 + 本地 JSON（config.json，含 API Key，勿提交）。"""
import json
import os

DEFAULT_CONFIG = {
    "balloon_fill": "#FFFFFF",
    "balloon_outline": "#1E3A8A",
    "balloon_text": "主人，有新消息啦！",
    "peak_balloon_text": "高峰时段开始啦……",
    "idle_balloon_text": "空闲时段开始啦！",
    "pet_image": "",
    "pet_pos": [],
    "pet_scale": 1.0,
    "pet_interact_image": "",
    "show_balance": True,
    "balance_font_size": 14,
    "balance_offset": [],
    "poll_interval_sec": 5,
    "self_talk_enabled": True,
    "self_talk_texts": [
        "今天也是元气满满的一天！",
        "主人工作辛苦了～",
        "要不要摸摸头？",
        "我在认真看家呢。",
        "呼……好想出去晒晒太阳。",
        "余额安全，请放心～",
    ],
    "self_talk_interval": 300,
    "self_talk_file": "",
    "auto_start": False,
    "accounts": {},
}


class Config:
    def __init__(self, path):
        self.path = path
        self.data = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            for key in DEFAULT_CONFIG:
                if key in loaded:
                    self.data[key] = loaded[key]
            self._migrate_accounts()
        except Exception:
            pass

    def _migrate_accounts(self):
        """旧格式 {名称: Key} 迁移为 {名称: {platform, api_key}}。"""
        accounts = self.data.get("accounts")
        if not isinstance(accounts, dict):
            return
        changed = False
        for name, acc in list(accounts.items()):
            if isinstance(acc, str):
                accounts[name] = {"platform": "deepseek", "api_key": acc}
                changed = True
        if changed:
            self.save()

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()
