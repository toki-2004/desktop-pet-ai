# -*- coding: utf-8 -*-
"""对话历史：JSON 持久化（跨重启）+ 查看器对话框。"""
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPlainTextEdit, QMessageBox
from PyQt5.QtGui import QTextCursor

import petlog


if sys.platform == "win32":
    class _MSG(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                    ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD), ("pt", wintypes.POINT)]


class ChatHistory(QObject):
    """保存全部消息（含自言自语），context() 只取参与对话的条目。

    append 后发出 changed 信号，聊天记录查看窗口据此实时刷新。"""

    changed = pyqtSignal()

    def __init__(self, path, max_n=200):
        super().__init__()
        self.path = path
        self.max_n = max(10, int(max_n or 200))
        self.items = []
        self.rev = 0  # 每次 append +1：网页端据此判断"有新消息"（条数封顶后长度不再变）
        self.load()

    def load(self):
        """读记录。读不成（写一半/被占用/坏档）时保留现场再开空表，
        绝不静默当成"没有记录"——否则下一次 save 就把老记录永久覆盖了。"""
        data = None
        for attempt in range(3):
            try:
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                break
            except FileNotFoundError:
                self.items = []
                return
            except Exception:
                if attempt < 2:
                    time.sleep(0.3)
        if data is None:
            try:
                if os.path.exists(self.path):
                    os.replace(self.path, "%s.broken-%s" % (
                        self.path, time.strftime("%Y%m%d-%H%M%S")))
                    petlog.log("chat history unreadable, kept as .broken-*")
            except OSError:
                pass
            self.items = []
            return
        self.items = data.get("messages", []) if isinstance(data, dict) else []

    def save(self):
        """原子写：先写 .tmp 再 os.replace，读者不会读到"截断了一半"的文件。
        （旧写法是 open(w) 直接截断，别的实例正好在这时读就会拿到空/半截数据，
        它的下一次保存便把整份记录清空——今天两次"记录莫名消失"就是这个。）"""
        if not self.items:
            try:
                if os.path.exists(self.path) and os.path.getsize(self.path) > 10:
                    petlog.log("skip saving empty history over a non-empty file")
                    return
            except OSError:
                pass
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"messages": self.items[-self.max_n:]},
                          f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except Exception as e:
            petlog.log("chat history save failed: %s" % e)
            try:
                os.remove(tmp)
            except OSError:
                pass

    def append(self, role, content, kind="chat", image=""):
        self.rev += 1
        item = {
            "role": role, "content": content,
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind,
        }
        if image:
            # 网页要用 <img> 渲染发出去的图：只存文件名（图片本身在 web_images/）
            item["image"] = image
        self.items.append(item)
        self.items = self.items[-self.max_n:]
        self.save()
        self.changed.emit()

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
        self.view = QPlainTextEdit(self)
        self.view.setReadOnly(True)
        lay = QVBoxLayout(self)
        lay.addWidget(self.view)
        # 每次追加消息实时重绘并自动拉到底部（与刚打开时定位一致）
        self.history.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        lines = []
        for m in self.history.items:
            who = {"user": "我", "assistant": "桌宠"}.get(m.get("role"), m.get("role"))
            kind = {"selftalk": "自言自语", "head": "摸头", "chat": ""}.get(m.get("kind"), "")
            prefix = "[%s] %s%s：" % (m.get("ts", ""), who, ("（%s）" % kind) if kind else "")
            lines.append(prefix + str(m.get("content", "")))
        self.view.setPlainText("\n\n".join(lines))
        # 打开/每次更新都定位到最新记录：光标移到末尾并滚动到底
        self.view.moveCursor(QTextCursor.End)
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())

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
