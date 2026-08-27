# -*- coding: utf-8 -*-
"""桌宠核心入口：透明置顶桌宠 + 思考云线通知 + DeepSeek 余额 + 高峰/空闲提醒。"""
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
DEFAULT_TALK_FILE = os.path.join(BUNDLE_DIR, "self_talk.txt")


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
        self._texts = []
        try:
            with open(self.text_file, encoding="utf-8") as f:
                self._texts = [line.strip() for line in f if line.strip()]
        except Exception:
            pass
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
        self.talk_file = self.config.get("self_talk_file") or os.path.join(PROJECT_DIR, "self_talk.txt")
        if not self.config.get("self_talk_file"):
            self.config.set("self_talk_file", self.talk_file)
        self._ensure_talk_file()
        if autostart.is_enabled():
            self.config.set("auto_start", True)
        self.window = PetWindow(self.config, default_image=DEFAULT_IMAGE)
        self.monitor = BalanceMonitor(self.config)
        self.schedule = ScheduleMonitor()
        self.talk = SelfTalkMonitor(self.config, self.talk_file)
        self._balloon = None
        self._last_error_ts = 0.0
        self._settings_dlg = None
        self._wire()
        self._restore_position()
        if not self.config.get("pet_interact_image") and os.path.exists(DEFAULT_INTERACT):
            self.config.set("pet_interact_image", DEFAULT_INTERACT)
        self.window.show()
        self.monitor.start()

    def _ensure_talk_file(self):
        if os.path.exists(self.talk_file):
            return
        if os.path.exists(DEFAULT_TALK_FILE):
            try:
                shutil.copyfile(DEFAULT_TALK_FILE, self.talk_file)
                return
            except Exception:
                pass
        texts = self.config.get("self_talk_texts") or []
        try:
            with open(self.talk_file, "w", encoding="utf-8") as f:
                f.write("\n".join(texts))
        except Exception:
            pass

    def _wire(self):
        w = self.window
        w.toggleBalanceRequested.connect(self._on_toggle_balance)
        w.bindAccountRequested.connect(lambda: self._open_settings(2))
        w.settingsRequested.connect(lambda: self._open_settings(0))
        w.appearanceRequested.connect(lambda: self._open_settings(1))
        w.testNotifyRequested.connect(self._test_notify)
        w.quitRequested.connect(QApplication.instance().quit)
        w.autoStartRequested.connect(self._on_auto_start)
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

    def _show_balloon(self, text, persistent=False):
        if self._balloon is not None:
            self._balloon.hide()
            self._balloon.deleteLater()
        self._balloon = ThinkingBalloon(
            text=text,
            fill=self.config.get("balloon_fill", "#FFFFFF"),
            outline=self.config.get("balloon_outline", "#1E3A8A"),
            persistent=persistent,
        )
        self._balloon.confirmed.connect(self._balloon.hide)
        self._balloon.show_at(self.window.geometry())

    def _test_notify(self):
        self._show_balloon(self.config.get("balloon_text", "主人，有新消息啦！"))
        self.window.show_float_text("通知功能正常", "#22C55E")

    def _open_settings(self, tab):
        if self._settings_dlg is not None:
            self._settings_dlg.raise_()
            self._settings_dlg.activateWindow()
            self._settings_dlg.tabs.setCurrentIndex(tab)
            return
        dlg = SettingsDialog(self.config, initial_tab=tab)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.accepted.connect(self._on_settings_applied)
        self._settings_dlg = dlg
        dlg.show()

    def _on_settings_applied(self):
        self._settings_dlg = None
        self.window.apply_config()
        self.monitor.set_interval(int(self.config.get("poll_interval_sec", 5)))
        self.monitor.poll()
        self.talk._schedule()

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
