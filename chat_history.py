# -*- coding: utf-8 -*-
"""对话历史：JSON 持久化（跨重启）+ 查看器对话框。"""
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QMessageBox
from PyQt5.QtGui import QTextCursor


if sys.platform == "win32":
    class _MSG(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                    ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD), ("pt", wintypes.POINT)]


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
        self.history = history
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
        # 打开即定位到最新记录：光标移到末尾并滚动到底
        view.moveCursor(QTextCursor.End)
        view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())
        lay = QVBoxLayout(self)
        lay.addWidget(view)

    def nativeEvent(self, eventType, message):
        # Windows 标题栏"?"按钮默认无动作，点击直接弹出说明
        if sys.platform == "win32":
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
                if msg.message == 0x0112 and msg.wParam == 0xF180:
                    QMessageBox.information(
                        self, "关于聊天记录",
                        "这里显示桌宠和你的聊天记录：\n\n"
                        "· 包括对话、自言自语、摸头触发的发言\n"
                        "· 保存在本地 chat_history.json，重启后仍保留\n"
                        "· 最多保留最近 %d 条\n"
                        "· 发送给 AI 时只取最近 N 条对话（设置 → AI → 携带历史对话条数）\n\n"
                        "如需清空，退出桌宠后删除 chat_history.json 即可。"
                        % self.history.max_n)
                    return True, 0
            except Exception:
                pass
        return super().nativeEvent(eventType, message)
