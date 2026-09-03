# -*- coding: utf-8 -*-
"""OpenAI 兼容对话客户端：后台线程调 /v1/chat/completions，信号回主线程。"""
import re
import threading

import requests
from PyQt5.QtCore import QObject, pyqtSignal

import petlog


# 厂商预设：选预设自动填 base_url/model，用户只需填 key（本机服务可免 key）
PRESETS = {
    "deepseek_web2api": {
        "name": "DeepSeekWeb2API（内置免费）",
        "base_url": "http://127.0.0.1:3000/v1",
        "model": "deepseek",
        "key": "sk-local",  # 与 vendor/DeepSeekWeb2API/config.json 的 apiKey 一致
    },
    "deepseek_open": {
        "name": "DeepSeek 开放平台",
        "base_url": "https://api.deepseek.com/v1",
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


def strip_citations(text):
    """去掉 AI 联网搜索回复里的 [citation:N] 标签（不显示、不存历史）。"""
    text = re.sub(r"\[citation:\s*\d+\]", "", str(text), flags=re.I)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


class AIClient(QObject):
    """chat() 发起异步请求；system prompt 在 worker 线程组装（含阻塞的系统感知调用，
    不卡 GUI）；reply 信号回 (text, ok, meta)。"""

    reply = pyqtSignal(str, bool, object)

    def __init__(self, config):
        super().__init__()
        self.config = config

    def chat(self, messages, meta=None, system_fn=None):
        """messages 不含 system 消息时传 system_fn()，在 worker 线程生成 system 前置。"""
        threading.Thread(
            target=self._worker, args=(list(messages), meta, system_fn), daemon=True
        ).start()

    def _worker(self, messages, meta, system_fn=None):
        try:
            system = system_fn() if system_fn else ""
        except Exception as e:
            petlog.log("system prompt build failed: %s" % e)
            system = ""
        if system:
            messages = [{"role": "system", "content": system}] + messages
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
            text = strip_citations(r.json()["choices"][0]["message"]["content"])
            self.reply.emit(text, True, meta)
        except Exception as e:
            petlog.log("ai request failed: %s" % e)
            self.reply.emit("", False, meta)
