# -*- coding: utf-8 -*-
"""配置读写：默认配置 + 本地 JSON（config.json，含 API Key，勿提交）。"""
import json
import os
import shutil

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
    "poll_interval_sec": 3,
    "always_on_top": True,
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
    "pet_head_enabled": True,
    "pet_head_interval": 10,
    "pet_head_long_press_ms": 600,
    "pet_head_texts": [
        "嘿嘿，主人摸得我好舒服～",
        "再摸摸！还要！",
        "主人的手好温柔……",
        "呼噜呼噜～",
        "被摸头的感觉真棒！",
        "唔……有点困了，但还想被摸。",
        "摸摸我的时候，世界都安静了。",
        "今天也要多摸摸我哦！",
    ],
    "pet_head_file": "",
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
        except Exception as e:
            # 配置损坏（含 API Key 与全部个性化设置）绝不能静默丢失：
            # 坏档改名保留供排查，控制台留痕，下次保存生成全新配置
            print("[config] 配置文件读取失败，已使用默认配置: %s" % e)
            try:
                os.replace(self.path, self.path + ".broken")
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
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            if os.path.exists(self.path):
                try:
                    shutil.copy2(self.path, self.path + ".bak")  # 上一份好档留作备份
                except Exception:
                    pass
            os.replace(tmp, self.path)  # 原子替换，杜绝"截断后写一半"的坏档
        except Exception:
            pass

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()
