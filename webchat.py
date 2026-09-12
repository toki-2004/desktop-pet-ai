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
 html,body{margin:0;height:100%;background:#10141c;color:#e8ecf3;
   font:16px/1.5 "Microsoft YaHei",system-ui,sans-serif}
 #head{position:sticky;top:0;background:#161b25;border-bottom:1px solid #263041;
   padding:8px 14px;display:flex;align-items:center;gap:10px}
 #head .t{font-weight:600}
 #head .a{margin-left:auto;color:#ffd166;font-weight:600}
 #pat{padding:8px 14px;border:0;border-radius:10px;background:#e8590c;color:#fff;
   font-size:15px;font-weight:600}
 #pat:disabled{background:#5a4634}
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
   font-size:13px;pointer-events:none}
 #new{position:fixed;left:50%;transform:translateX(-50%);bottom:74px;display:none;
   padding:6px 14px;border-radius:99px;background:#3d8bff;color:#fff;font-size:14px}
</style></head><body>
<div id="head">
  <span class="t">桌宠聊天</span><small id="cnt" style="color:#8b98ad"></small>
  <span class="a" id="aff">好感 …</span>
  <button id="pat">摸头</button>
</div>
<div id="list"></div>
<div id="hint"></div>
<div id="new">有新消息 ↓</div>
<div id="bar"><input id="txt" placeholder="跟桌宠说点什么…" autocomplete="off">
<button id="send">发送</button></div>
<script>
var K = new URLSearchParams(location.search).get('k') || '';
var api = function(p){ return p + (K ? '?k=' + encodeURIComponent(K) : ''); };
var rev = -1, waiting = 0, tierZh = {high:'高', mid:'一般', low:'低'};
function nearBottom(){
  return document.body.scrollHeight - window.scrollY - window.innerHeight < 60;
}
function render(msgs, keepPos){
  var list = document.getElementById('list');
  var atBottom = !keepPos || nearBottom();
  list.textContent = '';
  var frag = document.createDocumentFragment();
  msgs.forEach(function(m){
    var d = document.createElement('div');
    d.className = 'm ' + (m.role === 'user' ? 'me' : 'pet');
    var t = document.createElement('div');
    t.className = 't';
    t.textContent = (m.ts || '') + ' ' + (m.role === 'user' ? '我' : '桌宠');
    d.appendChild(t);
    var b = document.createElement('div');
    b.textContent = m.content || '';
    d.appendChild(b);
    frag.appendChild(d);
  });
  list.appendChild(frag);
  document.getElementById('cnt').textContent = msgs.length + ' 条';
  var last = msgs.length ? msgs[msgs.length - 1] : null;
  var replied = !!last && last.role !== 'user';
  if (replied) { waiting = 0; document.getElementById('send').disabled = false; }
  document.getElementById('hint').textContent = waiting ? '已发送，桌宠思考中…' : '';
  if (atBottom) { window.scrollTo(0, document.body.scrollHeight);
                  document.getElementById('new').style.display = 'none'; }
  else if (keepPos) { document.getElementById('new').style.display = 'block'; }
}
function tick(first){
  fetch(api('/api/history')).then(function(r){ return r.json(); }).then(function(d){
    if (!d.messages) { document.getElementById('hint').textContent = d.error || 'token 不对'; return; }
    document.getElementById('aff').textContent =
        '好感 ' + (d.affection === null || d.affection === undefined ? '…' : Math.round(d.affection))
        + (tierZh[d.tier] ? ' · ' + tierZh[d.tier] : '');
    if (d.rev !== rev) {
      var grew = rev >= 0 && d.rev !== rev;
      rev = d.rev;
      render(d.messages, grew);   // 老记录不再跳到底，出新消息才给提示
    }
    document.getElementById('send').disabled = !!waiting;
  }).catch(function(){ document.getElementById('hint').textContent = '连不上桌宠'; });
}
function send(){
  var el = document.getElementById('txt'); var text = el.value.trim();
  if (!text) return;
  el.value = ''; waiting = 1;
  // 先本地显示，别等下一轮轮询（发送后立刻能看到自己发的话）
  var list = document.getElementById('list');
  var box = document.createElement('div');
  box.className = 'm me';
  var t = document.createElement('div');
  t.className = 't';
  t.textContent = '刚刚 我';
  box.appendChild(t);
  var body = document.createElement('div');
  body.textContent = text;
  box.appendChild(body);
  list.appendChild(box);
  document.getElementById('hint').textContent = '已发送，桌宠思考中…';
  window.scrollTo(0, document.body.scrollHeight);
  fetch(api('/api/chat'), {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({text: text})}).then(function(r){ return r.json(); })
    .then(function(d){ if (d.error) { waiting = 0; document.getElementById('hint').textContent = d.error; } });
}
function pat(){
  var b = document.getElementById('pat');
  b.disabled = true;
  fetch(api('/api/pat'), {method:'POST'}).then(function(r){ return r.json(); })
    .then(function(d){ if (d.error) document.getElementById('hint').textContent = d.error; })
    .catch(function(){ document.getElementById('hint').textContent = '摸不到桌宠'; })
    .then(function(){ setTimeout(function(){ tick(false); }, 400); })  // 摸完刷新好感
    .then(function(){ setTimeout(function(){ b.disabled = false; }, 600); });
}
document.getElementById('send').onclick = send;
document.getElementById('pat').onclick = pat;
document.getElementById('new').onclick = function(){
  window.scrollTo(0, document.body.scrollHeight);
  this.style.display = 'none';
};
window.addEventListener('scroll', function(){
  if (nearBottom()) document.getElementById('new').style.display = 'none';
});
document.getElementById('txt').addEventListener('keydown', function(e){
  if (e.key === 'Enter') send(); });
setInterval(function(){ tick(false); }, 2000); tick(true);
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
    patRequested = pyqtSignal()   # 网页点"摸头"：走桌宠单击摸头同一条链路

    def __init__(self, history, port=8848, token="", bind="0.0.0.0", state_fn=None):
        super().__init__()
        self.history = history
        self.port = int(port)
        self.token = str(token or "")
        self.bind = str(bind or "0.0.0.0")
        self.state_fn = state_fn      # 主线程提供：好感值/档位
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

    def state(self):
        try:
            data = dict(self.state_fn() or {}) if self.state_fn else {}
        except Exception:
            data = {}
        return {
            "rev": int(getattr(self.history, "rev", 0)),
            "affection": data.get("affection"),
            "tier": data.get("tier"),
        }

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
                    payload = owner.state()
                    payload["messages"] = owner.messages()
                    self._send(200, json.dumps(payload, ensure_ascii=False))
                    return
                if parsed.path == "/api/state":
                    self._send(200, json.dumps(owner.state(), ensure_ascii=False))
                    return
                self._send(404, json.dumps({"error": "not found"}))

            def do_POST(self):
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                if not self._authed(query):
                    self._send(401, json.dumps({"error": "token 不对"}))
                    return
                if parsed.path != "/api/chat":
                    if parsed.path == "/api/pat":
                        owner.patRequested.emit()   # 跨线程 → 主线程摸头
                        payload = owner.state()
                        payload["ok"] = True
                        self._send(200, json.dumps(payload, ensure_ascii=False))
                        return
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
