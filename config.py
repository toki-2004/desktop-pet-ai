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
    "peak_status_text": "高峰时段",
    "idle_status_text": "空闲时段",
    "affection_enabled": True,
    "affection_initial": 70,
    "affection_max": 100,
    "affection_gain": 5,
    "affection_decay_sec": 300,
    "affection_high_threshold_pct": 80,
    "affection_low_threshold_pct": 40,
    "affection_quote_cooldown_sec": 600,
    "affection_label_enabled": True,
    "affection_value": 0.0,
    "affection_last_update": 0.0,
    "pet_image": "",
    "pet_pos": [],
    "pet_scale": 1.0,
    "pet_interact_image": "",
    "balance_font_size": 14,
    "always_on_top": True,
    "self_talk_enabled": True,
    "self_talk_interval": 300,
    "pet_head_enabled": True,
    "auto_start": False,
    # AI 对话（OpenAI 兼容）
    "ai_preset": "deepseek_web2api",
    "ai_base_url": "http://127.0.0.1:3000/v1",
    "ai_api_key": "sk-local",  # 内置服务的本地 key（与 vendor config.json 一致）
    "ai_model": "deepseek-chat",
    "ai_persona": (
        "你是一只住在用户桌面上的 AI 桌宠，说话可爱、简短、口语化，每次回复尽量不超过两句话。"
        "你会根据当前情境（时间、天气、好感度等）主动说话，也会回应主人的摸头和聊天。"
    ),
    "ai_context_n": 10,
    "ai_fallback_enabled": True,
    "ai_fallback_text": "唔……我现在有点短路了",
    "ai_web2api_max_messages": 20,  # 内置 DeepSeek 网页对话的消息上限（0=不限制）
    "chat_history_max": 200,
    "chat_input_offset": [],
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
        except Exception as e:
            # 配置损坏（含 API Key 与全部个性化设置）绝不能静默丢失：
            # 坏档改名保留供排查，控制台留痕，下次保存生成全新配置
            print("[config] 配置文件读取失败，已使用默认配置: %s" % e)
            try:
                os.replace(self.path, self.path + ".broken")
            except Exception:
                pass

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
