# -*- coding: utf-8 -*-
"""内置 DeepSeekWeb2API 生命周期管理。

vendor/DeepSeekWeb2API 是 D:\\pythonitems\\DeepSeekWeb2API 的本地拷贝
（便携 Node + 源码，GitHub 不入库）。职责：
- 探测 127.0.0.1:3000 是否已有 web2api 服务（自己的或用户手启的都直接用）；
- 未绑定（vendor 无登录态）时以可见控制台跑 --login，首次启动弹浏览器登录；
- 已绑定则后台静默启动服务，桌宠退出时停止自己拉起的进程。
"""
import atexit
import os
import subprocess
import sys
import threading

import requests
from PyQt5.QtCore import QObject, pyqtSignal

if getattr(sys, "frozen", False):
    _BASE = os.path.dirname(sys.executable)
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
VENDOR_DIR = os.path.join(_BASE, "vendor", "DeepSeekWeb2API")
PORT = 3000
BASE_URL = "http://127.0.0.1:%d" % PORT

_proc = None  # 自己拉起的服务进程，退出时回收


def _node_exe():
    exe = os.path.join(VENDOR_DIR, "node", "node.exe")
    return exe if os.path.exists(exe) else "node"


def is_bound():
    """登录态是否存在（data/user-data 下有内容）。"""
    d = os.path.join(VENDOR_DIR, "data", "user-data")
    try:
        return os.path.isdir(d) and bool(os.listdir(d))
    except OSError:
        return False


def service_alive():
    """端口上是否已有 web2api 服务（200=匹配，401=在跑但 key 不同，都算可用）。"""
    try:
        r = requests.get(BASE_URL + "/v1/models", timeout=2)
        return r.status_code in (200, 401)
    except Exception:
        return False


def _run_node(args, new_console):
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NEW_CONSOLE if new_console else subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(
        [_node_exe(), os.path.join(VENDOR_DIR, "src", "index.js")] + args,
        cwd=VENDOR_DIR, creationflags=flags,
        stdout=subprocess.DEVNULL if not new_console else None,
        stderr=subprocess.DEVNULL if not new_console else None,
    )


def start_service(timeout_s=30):
    """后台静默启动服务并等待就绪；已有服务在跑则直接返回 True。"""
    global _proc
    if service_alive():
        return True
    _proc = _run_node([], new_console=False)
    for _ in range(timeout_s * 2):
        if service_alive():
            return True
        if _proc.poll() is not None:
            return False
        threading.Event().wait(0.5)
    return service_alive()


def stop_service():
    """停止自己拉起的服务（taskkill 带上 Playwright 浏览器子进程树）。"""
    global _proc
    p, _proc = _proc, None
    if p is not None and p.poll() is None:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                           creationflags=subprocess.CREATE_NO_WINDOW,
                           capture_output=True)
        else:
            p.terminate()


def run_login_and_start():
    """可见控制台跑 --login（弹浏览器），用户登录完关掉控制台后自动拉起服务。"""
    stop_service()
    login = _run_node(["--login"], new_console=True)
    login.wait()
    return start_service()


def kill_port_listener():
    """重新绑定前清掉 3000 端口上的旧服务（无论是不是自己拉起的）。"""
    stop_service()
    if not service_alive():
        return
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "tcp"],
                             creationflags=subprocess.CREATE_NO_WINDOW,
                             capture_output=True, text=True).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1].endswith(":%d" % PORT) and parts[3] == "LISTENING":
                subprocess.run(["taskkill", "/PID", parts[4], "/T", "/F"],
                               creationflags=subprocess.CREATE_NO_WINDOW,
                               capture_output=True)
    except Exception:
        pass
    for _ in range(10):
        if not service_alive():
            return
        threading.Event().wait(0.3)


atexit.register(stop_service)


class Manager(QObject):
    """给桌宠用的异步封装：ensure_async / rebind_async，结果经 status 信号回主线程。"""

    status = pyqtSignal(bool, str)  # (ok, message)

    def ensure_async(self):
        threading.Thread(target=self._ensure, daemon=True).start()

    def _ensure(self):
        if service_alive():
            self.status.emit(True, "")
            return
        if not is_bound():
            self.status.emit(False, "login")
            ok = run_login_and_start()
            self.status.emit(ok, "内置 AI 已就绪" if ok else "内置 AI 启动失败，请看设置页重新绑定")
            return
        ok = start_service()
        self.status.emit(ok, "内置 AI 已就绪" if ok else "内置 AI 启动失败，请看设置页重新绑定")

    def rebind_async(self):
        threading.Thread(target=self._rebind, daemon=True).start()

    def _rebind(self):
        kill_port_listener()
        ok = run_login_and_start()
        self.status.emit(ok, "重新绑定完成，内置 AI 已就绪" if ok
                         else "重新绑定失败，请重试或手动启动 vendor 服务")
