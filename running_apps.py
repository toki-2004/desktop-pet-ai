# -*- coding: utf-8 -*-
"""枚举 Windows 上有可见窗口的应用（前台优先），供 AI 判断主人此刻在做什么。

只采"有窗口标题"的顶层窗口：纯后台进程没有窗口，对判断用户当前活动没意义。
"""
import ctypes
import os
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi
_EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_DWM_CLOAKED = 14  # DWMWA_CLOAKED：窗口被系统隐藏（如 UWP/Edge 幽灵窗口）
# 系统桌面/任务栏等与用户活动无关的窗口类
_SKIP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow"}


def _text(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    if not n:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value.strip()


def _class_name(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _cloaked(hwnd):
    cloaked = wintypes.DWORD()
    return (dwmapi.DwmGetWindowAttribute(
        hwnd, _DWM_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0
        and bool(cloaked.value))


def _exe_name(hwnd):
    """窗口所属进程的可执行文件名（如 chrome.exe）；取不到时返回空串。"""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value or pid.value == os.getpid():
        return ""
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(ctypes.sizeof(buf))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
    finally:
        kernel32.CloseHandle(handle)
    return ""


def _entry(hwnd):
    """可见、未隐藏且有标题的窗口 -> "exe - 标题"；否则返回 None。"""
    if not user32.IsWindowVisible(hwnd) or _cloaked(hwnd):
        return None
    if _class_name(hwnd) in _SKIP_CLASSES:
        return None
    title = _text(hwnd)[:60]
    if not title:
        return None
    exe = _exe_name(hwnd)
    return "%s - %s" % (exe, title) if exe else title


def running_apps(max_n=12):
    """返回当前打开应用的描述列表（前台窗口在最前）；失败/无可枚举时返回 []。"""
    try:
        fg = user32.GetForegroundWindow()
        first = _entry(fg)
        found = [first] if first else []

        def collect(hwnd, _):
            if len(found) >= max_n:
                return False  # 窗口数足够就停（enum 按 Z 序，前面的更接近前台）
            if hwnd == fg:
                return True
            item = _entry(hwnd)
            if item and item not in found:
                found.append(item)
            return True

        user32.EnumWindows(_EnumWindowsProc(collect), 0)
        return found[:max_n]
    except Exception:
        return []


if __name__ == "__main__":
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    print("\n".join(running_apps()))
