# -*- coding: utf-8 -*-
"""对话历史：JSON 持久化（跨重启）+ 查看器对话框。"""
import json
import os
import time

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit


class ChatHistory:
    """保存全部消息（含自言自语），context() 只取参与对话的条目。"""

    def __init__(self, path, max_n=200):
        self.path = path
        self.max_n = max(10, int(max_n or 200))
        self.items = []
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self.items = data.get("messages", []) if isinstance(data, dict) else []
        except Exception:
            self.items = []

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"messages": self.items[-self.max_n:]},
                          f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def append(self, role, content, kind="chat"):
        self.items.append({
            "role": role, "content": content,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind,
        })
        self.items = self.items[-self.max_n:]
        self.save()

    def context(self, n):
        """最近 n 条 user/assistant 消息（OpenAI messages 格式，不含 ts）。"""
        msgs = [m for m in self.items if m.get("role") in ("user", "assistant")]
        return [{"role": m["role"], "content": m["content"]} for m in msgs[-n:]]


class HistoryDialog(QDialog):
    def __init__(self, history, parent=None):
        super().__init__(parent)
        self.setWindowTitle("聊天记录")
        self.resize(420, 480)
        view = QPlainTextEdit(self)
        view.setReadOnly(True)
        lines = []
        for m in history.items:
            who = {"user": "我", "assistant": "桌宠"}.get(m.get("role"), m.get("role"))
            kind = {"selftalk": "自言自语", "head": "摸头", "chat": ""}.get(m.get("kind"), "")
            prefix = "[%s] %s%s：" % (m.get("ts", ""), who, ("（%s）" % kind) if kind else "")
            lines.append(prefix + str(m.get("content", "")))
        view.setPlainText("\n\n".join(lines))
        lay = QVBoxLayout(self)
        lay.addWidget(view)
