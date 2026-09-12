# -*- coding: utf-8 -*-
"""聊天记录局域网网页：手机上也能看历史、直接和桌宠说话。

服务跑在后台线程（标准库 http.server，零依赖），收到的消息用 Qt 信号回主线程，
走的是和桌宠输入框完全相同的那条链路（chatInputRequested），所以效果一致。
局域网可见，因此默认要求一个 token（config.json 的 webchat_token）。
"""
import json
import base64
import os
import shutil
import socket
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from PyQt5.QtCore import QObject, pyqtSignal

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
IMAGE_MIME_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg",
                  "image/webp": ".webp", "image/gif": ".gif"}
IMAGE_EXT_MIME = {v: k for k, v in IMAGE_MIME_EXT.items()}
IMAGE_EXT_MIME[".jpeg"] = "image/jpeg"
MAX_IMAGE_BYTES = 20 * 1024 * 1024   # 手机照片压过之后远小于这个数
MAX_KEEP_IMAGES = 200                # 网页要能回看图片：留最近 200 张，其余按时间清
# 发出去的图都存这里（main 会改成程序目录下的 web_images，方便随 exe 一起留存）
MEDIA_DIR = os.path.join(tempfile.gettempdir(), "pet_webchat_img")


def save_data_url(data_url):
    """data:image/...;base64,... → 存到 MEDIA_DIR 的图片路径（给桌宠那条发图链路用）。"""
    head, _, payload = str(data_url).partition(",")
    if not payload or not head.startswith("data:image/"):
        return ""
    mime = head[5:].split(";")[0].lower()
    ext = IMAGE_MIME_EXT.get(mime)
    if not ext:
        return ""
    try:
        raw = base64.b64decode(payload, validate=False)
    except Exception:
        return ""
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        return ""
    os.makedirs(MEDIA_DIR, exist_ok=True)
    _prune_old_images()
    path = os.path.join(MEDIA_DIR, "web_%d%s" % (int(time.time() * 1000), ext))
    with open(path, "wb") as f:
        f.write(raw)
    return path


def store_image(src_path):
    """把要发出去的图复制进 MEDIA_DIR，返回文件名（网页据此 <img> 渲染）。
    已经在 MEDIA_DIR 里的（网页上传的）直接返回文件名，不重复复制。
    ponytail: 只保留最近 MAX_KEEP_IMAGES 张，不做引用计数。"""
    try:
        src = os.path.abspath(str(src_path))
        if not os.path.isfile(src):
            return ""
        ext = os.path.splitext(src)[1].lower()
        if ext not in IMAGE_EXT_MIME:
            return ""
        if os.path.dirname(src) == os.path.abspath(MEDIA_DIR):
            return os.path.basename(src)
        os.makedirs(MEDIA_DIR, exist_ok=True)
        name = "%d_%s" % (int(time.time() * 1000), _safe_name(os.path.basename(src)))
        shutil.copyfile(src, os.path.join(MEDIA_DIR, name))
        _prune_old_images()
        return name
    except OSError:
        return ""


def media_path(name):
    """MEDIA_DIR 里某个文件的安全路径（挡住路径穿越）；不存在返回空串。"""
    name = os.path.basename(str(name or ""))
    if not name or name != str(name or ""):
        return ""
    path = os.path.join(MEDIA_DIR, name)
    return path if os.path.isfile(path) else ""


def _safe_name(name):
    keep = "-_.() abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    cleaned = "".join(c for c in str(name) if c in keep).strip() or "image"
    return cleaned[-60:]


def _prune_old_images():
    """只留最近 MAX_KEEP_IMAGES 张（多了按修改时间删老的）。"""
    try:
        files = [os.path.join(MEDIA_DIR, n) for n in os.listdir(MEDIA_DIR)]
        files = [p for p in files if os.path.isfile(p)]
        for p in sorted(files, key=os.path.getmtime)[:-MAX_KEEP_IMAGES]:
            os.remove(p)
    except OSError:
        pass


# 单文件页面：2 秒轮询历史，纯 textContent 渲染（AI 文本不会被当 HTML 执行）
PAGE = """<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>桌宠聊天记录</title>
<style>
 html,body{margin:0;height:100%;background:#10141c;color:#e8ecf3;
   font:16px/1.5 "Microsoft YaHei",system-ui,sans-serif}
 /* 固定顶栏：好感 / 摸头常驻，不跟聊天记录一起滚走。
    这里必须用 fixed 而不是 sticky —— sticky 的容纳块是 body，而 body 高度 100%，
    长列表里滚过一屏它就会跟着滚出去（表现为"要往上翻好久才看到"）。*/
 #head{position:fixed;left:0;right:0;top:0;z-index:10;background:#161b25;
   border-bottom:1px solid #263041;padding:8px 14px;display:flex;
   align-items:center;gap:8px;flex-wrap:nowrap;overflow:hidden}
 #head .tt{font-weight:600;white-space:nowrap}
 #head .c{color:#8b98ad;font-size:13px;white-space:nowrap}
 #head .a{margin-left:auto;color:#ffd166;font-weight:600;white-space:nowrap}
 #pat{flex:0 0 auto;padding:8px 14px;border:0;border-radius:10px;background:#e8590c;
   color:#fff;font-size:15px;font-weight:600}
 #pat:disabled{background:#5a4634}
 #list{padding:56px 14px 90px}   /* 顶部留出固定栏的高度 */
 @media (max-width:400px){#head .t,#head .tt{display:none}}
 .m{max-width:46em;margin:0 0 10px;padding:8px 12px;border-radius:12px;
   white-space:pre-wrap;word-break:break-word}
 .me{background:#2b6cb0;margin-left:auto}
 .pet{background:#232b38}
 .t{font-size:12px;color:#93a1b5;margin-bottom:2px}
 .pic{display:block;max-width:100%;max-height:320px;margin-top:6px;border-radius:8px;
   background:#0d1117}
 #bar{position:fixed;left:0;right:0;bottom:0;display:flex;gap:8px;padding:10px;
   background:#161b25;border-top:1px solid #263041}
 #txt{flex:1;padding:10px 12px;border-radius:10px;border:1px solid #33405a;
   background:#0d1117;color:#e8ecf3;font-size:16px}
 #send{padding:10px 16px;border:0;border-radius:10px;background:#3d8bff;
   color:#fff;font-size:16px}
 #send:disabled{background:#3a465c}
 #pick{padding:10px 12px;border:0;border-radius:10px;background:#3a465c;
   color:#fff;font-size:16px}
 #hint{position:fixed;left:0;right:0;bottom:66px;text-align:center;color:#8b98ad;
   font-size:13px;pointer-events:none}
 #new{position:fixed;left:50%;transform:translateX(-50%);bottom:74px;display:none;
   padding:6px 14px;border-radius:99px;background:#3d8bff;color:#fff;font-size:14px}
</style></head><body>
<div id="head">
  <span class="tt">桌宠聊天</span><small class="c" id="cnt"></small>
  <span class="a" id="aff">好感 …</span>
  <button id="pat">摸头</button>
</div>
<div id="list"></div>
<div id="hint"></div>
<div id="new">有新消息 ↓</div>
<div id="bar"><input id="txt" placeholder="跟桌宠说点什么…" autocomplete="off">
<button id="pick">图片</button>
<button id="send">发送</button></div>
<input id="file" type="file" accept="image/*" style="display:none">
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
    if (m.image) {
      // 图片消息：直接渲染出来（服务端 /api/media/<文件名> 只认这个目录里的文件）
      var a = document.createElement('a');
      a.href = api('/api/media/' + encodeURIComponent(m.image));
      a.target = '_blank';
      var im = document.createElement('img');
      im.className = 'pic';
      im.src = a.href;
      im.alt = '图片';
      im.loading = 'lazy';
      a.appendChild(im);
      d.appendChild(a);
    }
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
  localEcho(text);
  document.getElementById('hint').textContent = '已发送，桌宠思考中…';
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
function shrink(file){
  // 手机照片动辄好几 MB：先按最长边 1600 压成 JPEG 再传，快且不影响识图
  return new Promise(function(resolve){
    var fr = new FileReader();
    fr.onload = function(){
      var img = new Image();
      img.onload = function(){
        var max = 1600, w = img.width, h = img.height;
        if (w <= max && h <= max && file.size <= 1500000) { resolve(fr.result); return; }
        var scale = Math.min(1, max / Math.max(w, h));
        var c = document.createElement('canvas');
        c.width = Math.round(w * scale); c.height = Math.round(h * scale);
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        resolve(c.toDataURL('image/jpeg', 0.85));
      };
      img.onerror = function(){ resolve(fr.result); };
      img.src = fr.result;
    };
    fr.onerror = function(){ resolve(''); };
    fr.readAsDataURL(file);
  });
}
function localEcho(text){
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
  window.scrollTo(0, document.body.scrollHeight);
}
function sendImage(file){
  if (!file) return;
  waiting = 1;
  document.getElementById('send').disabled = true;
  document.getElementById('hint').textContent = '正在上传图片…';
  localEcho('（发送了一张图片：' + file.name + '）');
  shrink(file).then(function(dataUrl){
    if (!dataUrl) throw new Error('读不出这张图');
    return fetch(api('/api/image'), {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({image: dataUrl})});
  }).then(function(r){ return r.json(); }).then(function(d){
    if (d.error) { waiting = 0; document.getElementById('send').disabled = false;
                   document.getElementById('hint').textContent = d.error; return; }
    document.getElementById('hint').textContent = '已发送，桌宠看图思考中…';
  }).catch(function(e){
    waiting = 0; document.getElementById('send').disabled = false;
    document.getElementById('hint').textContent = '图片发送失败：' + (e.message || e);
  });
}
document.getElementById('pick').onclick = function(){ document.getElementById('file').click(); };
document.getElementById('file').addEventListener('change', function(e){
  var f = e.target.files && e.target.files[0];
  e.target.value = '';           // 同一张图能连发
  sendImage(f);
});
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
    imageRequested = pyqtSignal(str)   # 网页传图：走桌宠拖图/粘贴截图同一条链路

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
                if parsed.path.startswith("/api/media/"):
                    name = parsed.path[len("/api/media/"):]
                    path = media_path(name)
                    if not path:
                        self._send(404, json.dumps({"error": "no such image"}))
                        return
                    try:
                        with open(path, "rb") as f:
                            data = f.read()
                    except OSError:
                        self._send(404, json.dumps({"error": "no such image"}))
                        return
                    ctype = IMAGE_EXT_MIME.get(os.path.splitext(path)[1].lower(),
                                               "application/octet-stream")
                    self._send(200, data, ctype)
                    return
                self._send(404, json.dumps({"error": "not found"}))

            def do_POST(self):
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                if not self._authed(query):
                    self._send(401, json.dumps({"error": "token 不对"}))
                    return
                # 先把 body 读完：HTTP/1.1 keep-alive 下不读干净会污染同一条连接上的下一个请求
                payload = {}
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    if length:
                        payload = json.loads(self.rfile.read(length) or b"{}") or {}
                except Exception:
                    self._send(400, json.dumps({"error": "请求格式不对"}))
                    return
                if parsed.path == "/api/pat":
                    owner.patRequested.emit()   # 跨线程 → 主线程摸头
                    out = owner.state()
                    out["ok"] = True
                    self._send(200, json.dumps(out, ensure_ascii=False))
                    return
                if parsed.path == "/api/image":
                    path = save_data_url(payload.get("image") or "")
                    if not path:
                        self._send(400, json.dumps(
                            {"error": "图片格式不支持或太大（20MB 上限）"},
                            ensure_ascii=False))
                        return
                    owner.imageRequested.emit(path)   # 跨线程 → 主线程发图
                    self._send(200, json.dumps({"ok": True}, ensure_ascii=False))
                    return
                if parsed.path != "/api/chat":
                    self._send(404, json.dumps({"error": "not found"}))
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
