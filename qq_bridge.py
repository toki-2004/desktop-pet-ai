# -*- coding: utf-8 -*-
"""OneBot 11 私聊桥：NapCat 收 QQ 消息 → 本地内置 AI → QQ 回复。"""
import json
import queue
import re
import threading

import requests
from PyQt5.QtCore import QObject, QTimer, QUrl, Qt, pyqtSignal
from PyQt5.QtNetwork import QAbstractSocket, QNetworkRequest
from PyQt5.QtWebSockets import QWebSocket

import petlog
from ai_client import strip_citations

CQ_RE = re.compile(r"\[CQ:[^\]]+\]")


def extract_text(message):
    """OneBot 消息段只取 text；图片/表情等先忽略。"""
    if isinstance(message, list):
        parts = []
        for segment in message:
            if isinstance(segment, dict) and segment.get("type") == "text":
                data = segment.get("data") or {}
                parts.append(str(data.get("text") or ""))
        return "".join(parts).strip()
    if isinstance(message, str):
        return CQ_RE.sub("", message).strip()
    return ""


def chunk_text(text, limit=1500):
    text = str(text or "").strip()
    return [text[i:i + limit] for i in range(0, len(text), limit)] or [""]


class QQBridge(QObject):
    _send = pyqtSignal(str, str)

    def __init__(self, config, system_fn=None, parent=None):
        super().__init__(parent)
        self.config = config
        self._system_fn = system_fn
        self._ws = QWebSocket()
        self._ws.connected.connect(self._on_connected)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.textMessageReceived.connect(self._on_text)
        self._ws.error.connect(self._on_error)
        self._send.connect(self._on_send, Qt.QueuedConnection)
        self._reconnect = QTimer(self)
        self._reconnect.setSingleShot(True)
        self._reconnect.timeout.connect(self._connect)
        self._allowed = self._load_allowed()
        self._queue = queue.Queue()
        self._worker = None
        self._running = False
        self._seq = 0
        self._convo_primed = False
        self._seen = []
        self._seen_set = set()

    def _load_allowed(self):
        raw = self.config.get("qq_bridge_allowed_ids", [])
        if not isinstance(raw, (list, tuple, set)):
            raw = [raw]
        return {str(x).strip() for x in raw if str(x).strip()}

    def start(self):
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(target=self._ai_loop, daemon=True)
        self._worker.start()
        self._connect()

    def stop(self):
        self._running = False
        self._reconnect.stop()
        self._ws.close()
        self._queue.put(None)

    def reset_context(self):
        self._convo_primed = False

    def _connect(self):
        if not self._running:
            return
        url = str(self.config.get("qq_bridge_ws_url", "") or "").strip()
        if not url:
            petlog.log("qq bridge: empty ws url")
            return
        request = QNetworkRequest(QUrl(url))
        token = str(self.config.get("qq_bridge_token", "") or "").strip()
        if token:
            request.setRawHeader(b"Authorization", ("Bearer " + token).encode("utf-8"))
        petlog.log("qq bridge: connecting %s" % url)
        self._ws.open(request)

    def _on_connected(self):
        self._reconnect.stop()
        petlog.log("qq bridge: connected")

    def _on_disconnected(self):
        petlog.log("qq bridge: disconnected code=%s reason=%s"
                   % (self._ws.closeCode(), self._ws.closeReason()))
        self._schedule_reconnect()

    def _on_error(self, _error):
        petlog.log("qq bridge: socket error: %s" % self._ws.errorString())
        self._schedule_reconnect()

    def _schedule_reconnect(self):
        if self._running and not self._reconnect.isActive():
            self._reconnect.start(5000)

    def _on_text(self, raw):
        try:
            event = json.loads(raw)
        except Exception:
            petlog.log("qq bridge: invalid json")
            return
        if event.get("retcode"):
            petlog.log("qq bridge: onebot error %s: %s"
                       % (event.get("retcode"), event.get("message") or event.get("wording") or ""))
            return
        self.handle_event(event)

    def handle_event(self, event):
        if not isinstance(event, dict):
            return
        if event.get("post_type") != "message" or event.get("message_type") != "private":
            return
        user_id = str(event.get("user_id") or "")
        if not user_id or user_id == str(event.get("self_id") or ""):
            return
        message_id = str(event.get("message_id") or "")
        if message_id and not self._mark_seen(message_id):
            return
        if not self._allowed:
            # shortcut: 首个私聊用户自动绑定；换人时在 config 里改 allowed_ids
            self._allowed.add(user_id)
            self.config.set("qq_bridge_allowed_ids", sorted(self._allowed))
            petlog.log("qq bridge: bound first private user %s" % user_id)
        if user_id not in self._allowed:
            petlog.log("qq bridge: ignored user %s" % user_id)
            return
        text = extract_text(event.get("message"))
        if not text:
            return
        petlog.log("qq bridge: queued %d chars from %s" % (len(text), user_id))
        self._queue.put((user_id, text))

    def _mark_seen(self, message_id):
        if message_id in self._seen_set:
            return False
        if len(self._seen) >= 500:
            old = self._seen.pop(0)
            self._seen_set.discard(old)
        self._seen.append(message_id)
        self._seen_set.add(message_id)
        return True

    def _build_messages(self, text):
        messages = []
        builtin = self.config.get("ai_preset") == "deepseek_web2api"
        if not builtin or not self._convo_primed:
            system = ""
            if self._system_fn is not None:
                try:
                    system = str(self._system_fn() or "").strip()
                except Exception as e:
                    petlog.log("qq bridge: prompt build failed: %s" % e)
            if system:
                messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": text})
        return messages

    def _ai_loop(self):
        while True:
            item = self._queue.get()
            if item is None:
                return
            user_id, text = item
            try:
                reply = self._ask_ai(text)
                self._convo_primed = True
            except Exception as e:
                petlog.log("qq bridge: ai failed: %s" % e)
                reply = "我这会儿没连上自己的脑子，等等再发一次吧。"
            self._send.emit(user_id, reply)

    def _ask_ai(self, text):
        base = str(self.config.get("ai_base_url", "") or "").rstrip("/")
        if not base:
            raise RuntimeError("ai_base_url is empty")
        key = str(self.config.get("ai_api_key", "") or "")
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        timeout = float(self.config.get("ai_timeout_s", 300) or 300)
        messages = self._build_messages(text)
        petlog.log("qq bridge: ai request msgs=%d" % len(messages))
        response = requests.post(
            base + "/chat/completions",
            json={"model": self.config.get("ai_model", ""), "messages": messages},
            headers=headers,
            timeout=(10, timeout),
        )
        if response.status_code >= 400:
            code = ""
            try:
                code = str(((response.json() or {}).get("error") or {}).get("code") or "")
            except Exception:
                pass
            if code:
                raise RuntimeError("HTTP %s %s" % (response.status_code, code))
            response.raise_for_status()
        reply = strip_citations(response.json()["choices"][0]["message"]["content"])
        if not reply:
            raise RuntimeError("empty response")
        petlog.log("qq bridge: ai reply %d chars" % len(reply))
        return reply

    def _on_send(self, user_id, text):
        if not self._running or self._ws.state() != QAbstractSocket.ConnectedState:
            petlog.log("qq bridge: reply dropped (not connected)")
            return
        target = int(user_id) if user_id.isdigit() else user_id
        for part in chunk_text(text):
            self._seq += 1
            payload = {
                "action": "send_private_msg",
                "params": {"user_id": target, "message": part, "auto_escape": True},
                "echo": "pet-%d" % self._seq,
            }
            self._ws.sendTextMessage(json.dumps(payload, ensure_ascii=False))
            petlog.log("qq bridge: sent %d chars to %s" % (len(part), user_id))