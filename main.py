# -*- coding: utf-8 -*-
"""桌宠核心入口：透明置顶桌宠 + 思考云线通知 + DeepSeek 余额 + 高峰/空闲提醒。"""
import json
import os
import random
import shutil
import sys

from PyQt5.QtCore import Qt, QTimer, QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication

from config import Config
from pet_window import PetWindow
from balloon import ThinkingBalloon
from balance import BalanceMonitor
from scheduler import ScheduleMonitor
from settings_dialog import SettingsDialog
import autostart

FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    PROJECT_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", PROJECT_DIR)
else:
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = PROJECT_DIR

CONFIG_PATH = os.path.join(PROJECT_DIR, "config.json")
DEFAULT_IMAGE = os.path.join(BUNDLE_DIR, "assets", "deepseek拟人.png")
DEFAULT_INTERACT = os.path.join(BUNDLE_DIR, "assets", "ds摸头.gif")
DEFAULT_SELF_TALK_QUOTES = os.path.join(BUNDLE_DIR, "assets", "self_talk_quotes.json")
DEFAULT_PET_HEAD_QUOTES = os.path.join(BUNDLE_DIR, "assets", "pet_head_quotes.json")


def load_txt_lines(path):
    """读取旧版每行一条的文本库。"""
    try:
        with open(path, encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception:
        return []


def write_json_quotes(path, texts):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump([t for t in texts if str(t).strip()], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_quote_file(path, fallback):
    """读取 JSON 语录库（数组）；兼容旧 txt 格式；均失败时回退默认文本。"""
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                texts = [str(t).strip() for t in data if str(t).strip()]
                if texts:
                    return texts
        except Exception:
            pass
        lines = load_txt_lines(path)
        if lines:
            return lines
    return [str(t).strip() for t in (fallback or []) if str(t).strip()]


class SelfTalkMonitor(QObject):
    """挂机自言自语：按随机间隔从文本库取一条触发通知。"""

    talk = pyqtSignal(str)

    def __init__(self, config, text_file):
        super().__init__()
        self.config = config
        self.text_file = text_file
        self._texts = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._fire)
        self._schedule()

    def _load_texts(self):
        self._texts = load_quote_file(self.text_file, self.config.get("self_talk_texts") or [])
        return self._texts

    def _schedule(self):
        if not self.config.get("self_talk_enabled", True):
            return
        if not self._load_texts():
            return
        val = self.config.get("self_talk_interval", 300)
        sec = max(1, int(val if val is not None else 300))
        self._timer.start(sec * 1000)

    def _fire(self):
        if self._texts:
            self.talk.emit(random.choice(self._texts))
        self._schedule()


class DesktopPet:
    def __init__(self):
        self.config = Config(CONFIG_PATH)
        if not self.config.get("pet_image"):
            self.config.set(
                "pet_image", DEFAULT_IMAGE if os.path.exists(DEFAULT_IMAGE) else ""
            )
        self.talk_file = self.config.get("self_talk_file") or os.path.join(PROJECT_DIR, "self_talk_quotes.json")
        self.head_file = self.config.get("pet_head_file") or os.path.join(PROJECT_DIR, "pet_head_quotes.json")
        self._ensure_quote_files()
        if autostart.is_enabled():
            self.config.set("auto_start", True)
        self.window = PetWindow(self.config, default_image=DEFAULT_IMAGE)
        self.monitor = BalanceMonitor(self.config)
        self.schedule = ScheduleMonitor()
        self.talk = SelfTalkMonitor(self.config, self.talk_file)
        self._balloon = None
        self._special_active = False
        self._last_error_ts = 0.0
        self._settings_dlg = None
        self._wire()
        self._restore_position()
        if not self.config.get("pet_interact_image") and os.path.exists(DEFAULT_INTERACT):
            self.config.set("pet_interact_image", DEFAULT_INTERACT)
        self.window.show()
        self.monitor.start()

    def _ensure_quote_files(self):
        """确保两个语录库存在且为 JSON：旧 txt 自动迁移，缺失时复制预置默认库。"""
        # 旧版 .txt 迁移为 .json（原文件保留）
        if self.talk_file.lower().endswith(".txt") and os.path.exists(self.talk_file):
            lines = load_txt_lines(self.talk_file)
            if lines:
                json_path = os.path.join(PROJECT_DIR, "self_talk_quotes.json")
                write_json_quotes(json_path, lines)
                self.talk_file = json_path
                self.config.set("self_talk_file", json_path)
        self.talk_file = self._ensure_quote_file(
            self.talk_file, DEFAULT_SELF_TALK_QUOTES, self.config.get("self_talk_texts") or []
        )
        self.head_file = self._ensure_quote_file(
            self.head_file, DEFAULT_PET_HEAD_QUOTES, self.config.get("pet_head_texts") or []
        )
        if self.talk_file != self.config.get("self_talk_file"):
            self.config.set("self_talk_file", self.talk_file)
        if self.head_file != self.config.get("pet_head_file"):
            self.config.set("pet_head_file", self.head_file)

    def _ensure_quote_file(self, path, default_src, fallback_texts):
        if path and os.path.exists(path):
            return path
        if os.path.exists(default_src):
            try:
                shutil.copyfile(default_src, path)
                return path
            except Exception:
                pass
        write_json_quotes(path, fallback_texts)
        return path

    def _wire(self):
        w = self.window
        w.toggleBalanceRequested.connect(self._on_toggle_balance)
        w.bindAccountRequested.connect(lambda: self._open_settings(2))
        w.settingsRequested.connect(lambda: self._open_settings(0))
        w.appearanceRequested.connect(lambda: self._open_settings(1))
        w.testNotifyRequested.connect(self._test_notify)
        w.quitRequested.connect(QApplication.instance().quit)
        w.autoStartRequested.connect(self._on_auto_start)
        w.petHeadRequested.connect(self._show_pet_head)
        w.moved.connect(self._on_moved)

        m = self.monitor
        m.balanceUpdated.connect(w.set_balance_text)
        m.balanceUp.connect(lambda t: w.show_float_text(t, "#22C55E"))
        m.balanceDown.connect(lambda t: w.show_float_text(t, "#EF4444"))
        m.fetchError.connect(self._on_fetch_error)

        s = self.schedule
        s.peakStarted.connect(lambda: self._show_balloon(
            self.config.get("peak_balloon_text", "高峰时段开始啦……"), persistent=True))
        s.idleStarted.connect(lambda: self._show_balloon(
            self.config.get("idle_balloon_text", "空闲时段开始啦！"), persistent=True))
        self.talk.talk.connect(self._show_balloon)

    def _restore_position(self):
        pos = self.config.get("pet_pos")
        if isinstance(pos, list) and len(pos) == 2:
            self.window.move(pos[0], pos[1])

    def _on_moved(self, point):
        self.config.set("pet_pos", [point.x(), point.y()])
        if self._balloon is not None and self._balloon.isVisible():
            self._balloon.set_anchor(self.window.geometry())

    def _on_toggle_balance(self, visible):
        self.config.set("show_balance", bool(visible))
        self.window.set_balance_visible(visible)

    def _on_auto_start(self, enabled):
        try:
            if enabled:
                autostart.enable()
            else:
                autostart.disable()
            self.config.set("auto_start", bool(enabled))
        except Exception:
            self.window.show_float_text("自启设置失败", "#EF4444")

    def _show_pet_head(self):
        """长按桌宠：随机取一条摸头语录显示。"""
        texts = load_quote_file(self.head_file, self.config.get("pet_head_texts") or [])
        if texts:
            self._show_balloon(random.choice(texts))

    def _show_balloon(self, text, persistent=False):
        # 特殊通知（高峰/空闲，需点按钮确认）显示期间，抑制自言自语/摸头等普通通知
        if self._special_active and not persistent:
            return
        if self._balloon is not None:
            self._balloon.hide()
            self._balloon.deleteLater()
        self._balloon = ThinkingBalloon(
            text=text,
            fill=self.config.get("balloon_fill", "#FFFFFF"),
            outline=self.config.get("balloon_outline", "#1E3A8A"),
            persistent=persistent,
            always_on_top=bool(self.config.get("always_on_top", True)),
        )
        self._balloon.confirmed.connect(self._on_balloon_confirmed)
        if persistent:
            self._special_active = True
        self._balloon.show_at(self.window.geometry())

    def _on_balloon_confirmed(self):
        """特殊通知确认：只有点"知道了"按钮才会走到这里。"""
        self._special_active = False
        if self._balloon is not None:
            self._balloon.hide()

    def _test_notify(self):
        self._show_balloon(self.config.get("balloon_text", "主人，有新消息啦！"))
        self.window.show_float_text("通知功能正常", "#22C55E")

    def _open_settings(self, tab):
        if self._settings_dlg is not None:
            try:
                # 对话框可能处于隐藏但对象仍在的状态（如副屏 DPI 重建窗口时被连带隐藏），
                # 必须先 show() 再置前，否则 raise_() 对隐藏窗口无效、设置将永远打不开
                if not self._settings_dlg.isVisible():
                    self._settings_dlg.show()
                self._settings_dlg.raise_()
                self._settings_dlg.activateWindow()
                self._settings_dlg.tabs.setCurrentIndex(tab)
                return
            except RuntimeError:
                # 对话框已被关闭并删除（点取消/右上角 X），重新创建
                self._settings_dlg = None
        dlg = SettingsDialog(self.config, initial_tab=tab)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.destroyed.connect(self._on_settings_destroyed)
        dlg.accepted.connect(self._on_settings_applied)
        self._settings_dlg = dlg
        dlg.show()

    def _on_settings_destroyed(self):
        self._settings_dlg = None

    def _on_settings_applied(self):
        self._settings_dlg = None
        self.window.apply_config()
        self.monitor.set_interval(int(self.config.get("poll_interval_sec", 3)))
        self.monitor.poll()
        self.talk._schedule()
        if self._balloon is not None:
            self._balloon.set_top_flag(bool(self.config.get("always_on_top", True)))

    def _on_fetch_error(self, message):
        import time
        self.window.set_balance_text(0.0, "获取失败")
        now = time.time()
        if now - self._last_error_ts > 300:
            self._last_error_ts = now
            self.window.show_float_text("余额获取失败", "#EF4444")


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("DesktopPet")
    # 桌宠/气泡均为 Qt.Tool 工具窗口，不计入主窗口；关闭设置对话框时
    # 不应触发"最后窗口关闭即退出"，退出统一走右键菜单。
    app.setQuitOnLastWindowClosed(False)
    pet = DesktopPet()

    if os.environ.get("PET_SMOKE"):
        QTimer.singleShot(1500, pet._test_notify)
        QTimer.singleShot(4500, app.quit)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
