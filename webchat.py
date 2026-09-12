# -*- coding: utf-8 -*-
"""聊天记录局域网网页：手机上也能看历史、直接和桌宠说话。

服务跑在后台线程（标准库 http.server，零依赖），收到的消息用 Qt 信号回主线程，
走的是和桌宠输入框完全相同的那条链路（chatInputRequested），所以效果一致。
局域网可见，因此默认要求一个 token（config.json 的 webchat_token）。
"""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from PyQt5.QtCore import QObject, pyqtSignal

# 单文件页面：2 秒轮询历史，纯 textContent 渲染（AI 文本不会被当 HTML 执行）
PAGE = """<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>桌宠聊天记录</title>
<style>
 html,body{margin:0;height:100%%;background:#10141c;color:#e8ecf3;
   font:16px/1.5 "Microsoft YaHei",system-ui,sans-serif}
 #head{padding:10px 14px;background:#161b25;position:sticky;top:0;
   border-bottom:1px solid #263041;font-weight:600}
 #head small{color:#8b98ad;font-weight:400}
 #list{padding:12px 14px 90px}
 .m{max-width:46em;margin:0 0 10px;padding:8px 12px;border-radius:12px;
   white-space:pre-wrap;word-break:break-word}
 .me{background:#2b6cb0;margin-left:auto}
 .pet{background:#232b38}
 .t{font-size:12px;color:#93a1b5;margin-bottom:2px}
 #bar{position:fixed;left:0;right:0;bottom:0;display:flex;gap:8px;padding:10px;
   background:#161b25;border-top:1px solid #263041}
 #txt{flex:1;padding:10px 12px;border-radius:10px;border:1px solid #33405a;
   background:#0d1117;color:#e8ecf3;font-size:16px}
 #send{padding:10px 16px;border:0;border-radius:10px;background:#3d8bff;
   color:#fff;font-size:16px}
 #send:disabled{background:#3a465c}
 #hint{position:fixed;left:0;right:0;bottom:66px;text-align:center;color:#8b98ad;
   font-size:13px}
</style></head><body>
<div id="head">桌宠聊天记录 <small id="cnt"></small></div>
<div id="list"></div>
<div id="hint"></div>
<div id="bar"><input id="txt" placeholder="跟桌宠说点什么…" autocomplete="off">
<button id="send">发送</button></div>
<script>
var K = new URLSearchParams(location.search).get('k') || '';
var api = function(p){ return p + (K ? '?k=' + encodeURIComponent(K) : ''); };
var seen = -1, waiting = 0;
function esc(s){ return s; }
function render(msgs){
  var list = document.getElementById('list');
  list.textContent = '';
  msgs.forEach(function(m){
    var who = m.role === 'user' ? 'me' : 'pet';
    var d = document.createElement('div');
    d.className = 'm ' + who;
    var t = document.createElement('div');
    t.className = 't';
    t.textContent = (m.ts || '') + ' ' + (m.role === 'user' ? '我' : '桌宠');
    d.appendChild(t);
    var b = document.createElement('div');
    b.textContent = m.content || '';
    d.appendChild(b);
    list.appendChild(d);
  });
  document.getElementById('cnt').textContent = '共 ' + msgs.length + ' 条';
  window.scrollTo(0, document.body.scrollHeight);
}
function tick(){
  fetch(api('/api/history')).then(function(r){ return r.json(); }).then(function(d){
    if (!d.messages) { document.getElementById('hint').textContent = d.error || 'token 不对'; return; }
    if (d.messages.length !== seen) { seen = d.messages.length; render(d.messages); }
    if (waiting && d.messages.length && d.messages[d.messages.length-1].role !== 'user') {
      waiting = 0;
    }
    document.getElementById('hint').textContent = waiting ? '已发送，桌宠思考中…' : '';
    document.getElementById('send').disabled = !!waiting;
  }).catch(function(){ document.getElementById('hint').textContent = '连不上桌宠'; });
}
function send(){
  var el = document.getElementById('txt'); var text = el.value.trim();
  if (!text) return;
  el.value = ''; waiting = 1;
  fetch(api('/api/chat'), {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({text: text})}).then(function(r){ return r.json(); })
    .then(function(d){ if (d.error) { waiting = 0; document.getElementById('hint').textContent = d.error; } });
}
document.getElementById('send').onclick = send;
document.getElementById('txt').addEventListener('keydown', function(e){
  if (e.key === 'Enter') send(); });
setInterval(tick, 2000); tick();
</script></body></html>
"""


def lan_ip():
    """本机在局域网里的地址（只查路由表，不真的发包）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class WebChat(QObject):
    """history 用 ChatHistory；chatRequested 由主线程接到桌宠输入框那条链路。"""

    chatRequested = pyqtSignal(str)

    def __init__(self, history, port=8848, token="", bind="0.0.0.0"):
        super().__init__()
        self.history = history
        self.port = int(port)
        self.token = str(token or "")
        self.bind = str(bind or "0.0.0.0")
        self.error = ""
        self._httpd = None
        self._thread = None

    # ---------- 生命周期 ----------
    def start(self):
        try:
            self._httpd = ThreadingHTTPServer((self.bind, self.port), self._make_handler())
        except OSError as e:
            self.error = str(e)
            return False
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]  # 传 0 时取系统分配的真实端口
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        httpd, self._httpd = self._httpd, None
        if httpd is not None:
            try:
                httpd.shutdown()
                httpd.server_close()
            except Exception:
                pass

    def url(self, host=None):
        host = host or lan_ip()
        return "http://%s:%d/%s" % (host, self.port, ("?k=" + self.token) if self.token else "")

    # ---------- 内部 ----------
    def messages(self):
        try:
            return list(self.history.items)
        except Exception:
            return []

    def _make_handler(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):  # 轮询很吵，不打到 stderr
                pass

            def _send(self, code, body, ctype="application/json; charset=utf-8"):
                data = body if isinstance(body, bytes) else str(body).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _authed(self, query):
                if not owner.token:
                    return True
                return query.get("k", [""])[0] == owner.token

            def do_GET(self):
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                if not self._authed(query):
                    self._send(401, json.dumps({"error": "token 不对"}))
                    return
                if parsed.path in ("/", "/index.html"):
                    self._send(200, PAGE, "text/html; charset=utf-8")
                    return
                if parsed.path == "/api/history":
                    self._send(200, json.dumps({"messages": owner.messages()},
                                               ensure_ascii=False))
                    return
                self._send(404, json.dumps({"error": "not found"}))

            def do_POST(self):
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                if not self._authed(query):
                    self._send(401, json.dumps({"error": "token 不对"}))
                    return
                if parsed.path != "/api/chat":
                    self._send(404, json.dumps({"error": "not found"}))
                    return
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    payload = json.loads(self.rfile.read(length) or b"{}")
                except Exception:
                    self._send(400, json.dumps({"error": "请求格式不对"}))
                    return
                text = str((payload or {}).get("text") or "").strip()
                if not text:
                    self._send(400, json.dumps({"error": "内容为空"}))
                    return
                if len(text) > 2000:
                    self._send(400, json.dumps({"error": "太长了"}))
                    return
                owner.chatRequested.emit(text)  # 跨线程 → 主线程发消息
                self._send(200, json.dumps({"ok": True}))

        return Handler
