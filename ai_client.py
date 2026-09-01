# -*- coding: utf-8 -*-
"""OpenAI 兼容对话客户端：后台线程调 /v1/chat/completions，信号回主线程。"""
import threading

import requests
from PyQt5.QtCore import QObject, pyqtSignal


# 厂商预设：选预设自动填 base_url/model，用户只需填 key（本机服务可免 key）
PRESETS = {
    "deepseek_web2api": {
        "name": "DeepSeekWeb2API（本机）",
        "base_url": "http://127.0.0.1:8000/v1",
        "model": "deepseek-chat",
    },
    "siliconflow": {
        "name": "硅基流动",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "deepseek-ai/DeepSeek-V3",
    },
    "kimi": {
        "name": "Kimi (Moonshot)",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
    },
    "custom": {"name": "自定义", "base_url": "", "model": ""},
}


class AIClient(QObject):
    """chat(messages, meta) 发起异步请求；reply 信号回 (text, ok, meta)。"""

    reply = pyqtSignal(str, bool, object)

    def __init__(self, config):
        super().__init__()
        self.config = config

    def chat(self, messages, meta=None):
        threading.Thread(
            target=self._worker, args=(list(messages), meta), daemon=True
        ).start()

    def _worker(self, messages, meta):
        base = (self.config.get("ai_base_url") or "").rstrip("/")
        model = self.config.get("ai_model") or ""
        key = self.config.get("ai_api_key") or ""
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        try:
            r = requests.post(
                base + "/chat/completions",
                json={"model": model, "messages": messages},
                headers=headers,
                timeout=60,
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
            self.reply.emit(text, True, meta)
        except Exception as e:
            import petlog

            petlog.log("ai request failed: %s" % e)
            self.reply.emit("", False, meta)
