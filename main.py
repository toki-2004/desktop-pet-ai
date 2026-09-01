# -*- coding: utf-8 -*-
"""桌宠核心入口（AI 版）：透明置顶桌宠 + AI 生成文本 + 情境触发 + 聊天输入。"""
import json
import os
import random
import re
import shutil
import threading
import time
import sys

from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, QObject, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu

from config import Config
import petlog
petlog.install_excepthooks()
from pet_window import PetWindow
from balloon import ThinkingBalloon
from scheduler import ScheduleMonitor
from settings_dialog import SettingsDialog
from weather import WeatherMonitor
from affection import AffectionSystem
from ai_client import AIClient
from chat_history import ChatHistory, HistoryDialog
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


def _input_idle_seconds():
    """距上次键鼠输入的秒数（Windows GetLastInputInfo，无新依赖）。"""
    try:
        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(lii)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return max(0.0, (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0)
    except Exception:
        pass
    return 0.0


class SelfTalkMonitor(QObject):
    """情境自言自语：触发逻辑同原版（时段/健康/求关注/好感/天气/随机），
    命中标签后不再查语录库，而是发出 request_talk 信号，由 AI 生成文本。"""

    request_talk = pyqtSignal(str)

    TIME_WINDOWS = [  # (起始时, 结束时, 池后缀)——全天连续覆盖，每段每天至多触发一次
        (5, 11, "time_morning"),
        (11, 14, "time_noon"),
        (14, 18, "time_afternoon"),
        (18, 23, "time_evening"),
        (23, 24, "time_midnight"),
        (0, 5, "time_midnight"),
    ]
    WEEKEND_WINDOW = (9, 21)       # 周末白天
    IDLE_MINUTES = 45              # 闲置多久触发健康提醒
    ATTENTION_MINUTES = 90         # 多久没有互动触发求关注
    WEATHER_KINDS = ("sunny", "cloudy", "rainy", "snowy", "foggy", "windy", "stormy")

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._timer = QTimer(self)          # random：随机闲聊
        self._timer.timeout.connect(self._fire_random)
        self._context_timer = QTimer(self)  # time/health/attention：情境检查
        self._context_timer.timeout.connect(self._check_context)
        self._last_pat = 0.0      # monotonic：最近一次摸头/单击互动
        self._last_attention = 0.0
        self._last_health = 0.0
        self._fired_rules = {}    # time 规则 -> 已触发日期
        self._fired_weather = {}   # 天气池 -> 已触发日期
        # 可注入（测试/外部调整）
        self._now_fn = datetime.now
        self._mono_fn = time.monotonic
        self._idle_fn = _input_idle_seconds
        self._schedule()

    def _emit_tag(self, tag):
        """统一出口：总开关拦截 + 发出情境标签（文本由 AI 生成）。"""
        if not bool(self.config.get("self_talk_enabled", True)):
            return False
        self.request_talk.emit(tag)
        return True

    # ---------- 触发方式 ----------
    def _fire_random(self):
        self._emit_tag("random")
        self._schedule()

    def _check_context(self):
        now = self._now_fn()
        self._check_time_windows(now)
        self._check_health()
        self._check_attention()

    def _check_time_windows(self, now):
        today = now.date().isoformat()
        weekend = now.weekday() >= 5
        rules = []
        for h1, h2, sub in self.TIME_WINDOWS:
            if h1 <= now.hour < h2:
                rules.append(sub)
        if weekend and self.WEEKEND_WINDOW[0] <= now.hour < self.WEEKEND_WINDOW[1]:
            rules.append("time_weekend")
        for rule in rules:
            if self._fired_rules.get(rule) == today:
                continue
            if self._emit_tag(rule):
                self._fired_rules[rule] = today

    def _check_health(self):
        mono = self._mono_fn()
        idle = self._idle_fn()
        if idle >= self.IDLE_MINUTES * 60 and mono - self._last_health >= self.IDLE_MINUTES * 60:
            if self._emit_tag("health"):
                self._last_health = mono

    def _check_attention(self):
        mono = self._mono_fn()
        if (mono - self._last_pat >= self.ATTENTION_MINUTES * 60
                and mono - self._last_attention >= self.ATTENTION_MINUTES * 60):
            if self._emit_tag("attention"):
                self._last_attention = mono

    def on_affection_tier(self, tier):
        """好感档位切换时调用：high -> [affection_high]，mid/low 同理。"""
        tag = {"high": "affection_high", "mid": "affection_mid", "low": "affection_low"}.get(tier)
        if tag:
            self._emit_tag(tag)

    def set_weather(self, kind):
        """天气变化时调用：当天同一天气至多触发一次（换天气/跨天可再触发）。"""
        tag = ("weather_" + kind) if kind in self.WEATHER_KINDS else "weather"
        today = self._now_fn().date().isoformat()
        if self._fired_weather.get(tag) == today:
            return
        if self._emit_tag(tag):
            self._fired_weather[tag] = today

    def note_interaction(self):
        """摸头/单击互动发生时调用：刷新求关注计时。"""
        self._last_pat = self._mono_fn()

    # ---------- 开关与调度 ----------
    def _schedule(self):
        # 关闭开关、文本库为空、间隔 0 都要显式停表（random 与情境检查一起停；文本不再来自语录库）
        enabled = bool(self.config.get("self_talk_enabled", True))
        val = self.config.get("self_talk_interval", 300)
        try:
            sec = int(val if val is not None else 300)
        except (TypeError, ValueError):
            sec = 300
        if not enabled:
            self._timer.stop()
            self._context_timer.stop()
            return
        if sec > 0:
            self._timer.start(sec * 1000)
        else:
            self._timer.stop()  # 随机闲聊可单独设 0 关闭，情境触发不受影响
        if not self._context_timer.isActive():
            self._context_timer.start(60000)


class DesktopPet:
    def __init__(self):
        self.config = Config(CONFIG_PATH)
        if not self.config.get("pet_image"):
            self.config.set(
                "pet_image", DEFAULT_IMAGE if os.path.exists(DEFAULT_IMAGE) else ""
            )
        if autostart.is_enabled():
            self.config.set("auto_start", True)
        self.window = PetWindow(self.config, default_image=DEFAULT_IMAGE)
        self.schedule = ScheduleMonitor()
        self.talk = SelfTalkMonitor(self.config)
        self.ai = AIClient(self.config)
        self.history = ChatHistory(
            os.path.join(PROJECT_DIR, "chat_history.json"),
            self.config.get("chat_history_max", 200))
        self.affection = AffectionSystem(self.config)
        self.weather = WeatherMonitor(self.config)
        self._balloon = None
        self._special_active = False
        self._last_error_ts = 0.0
        self._settings_dlg = None
        self._wire()
        self._restore_position()
        if not self.config.get("pet_interact_image") and os.path.exists(DEFAULT_INTERACT):
            self.config.set("pet_interact_image", DEFAULT_INTERACT)
        self.window.show()
        if not os.environ.get("PET_SMOKE"):
            self.weather.start()  # 冒烟模式不访问网络（天气拉取放后台线程，会拖慢退出）
        self._setup_tray()  # 托盘（延迟自检组件）：窗口与监控就绪后创建

    # ---------- AI 生成 ----------
    def _system_prompt(self, tag=""):
        tier_map = {"high": "好感度很高", "mid": "好感度一般", "low": "好感度较低"}
        tier = self.affection.tier()
        from scheduler import is_peak
        period = "高峰时段" if is_peak() else "空闲时段"
        parts = [
            str(self.config.get("ai_persona", "")).strip(),
            "当前情境：%s；%s。" % (period, tier_map.get(tier, tier)),
        ]
        if getattr(self, "_last_weather", ""):
            parts.append("当前天气：%s。" % self._last_weather)
        if tag:
            parts.append("本次触发情境标签：%s。" % tag)
        parts.append("回复要非常简短（一两句话），不要复述情境描述。")
        return "\n".join(parts)

    def _ask_ai(self, messages, meta):
        n = int(self.config.get("ai_context_n", 10) or 10)
        msgs = ([{"role": "system", "content": self._system_prompt(meta.get("tag", ""))}]
                + self.history.context(n) + messages)
        self.ai.chat(msgs, meta)

    def _on_selftalk_tag(self, tag):
        self._ask_ai(
            [{"role": "user",
              "content": "（情境触发，请以桌宠身份自发说一句话，简短口语化。）"}],
            {"kind": "selftalk", "tag": tag})

    def _show_pet_head(self):
        """单击桌宠：AI 根据好感档位与上下文生成摸头反应。"""
        self._ask_ai(
            [{"role": "user",
              "content": "（主人刚刚单击摸了摸你的头，请自然地反应一句话，简短口语化。）"}],
            {"kind": "head"})

    def _on_user_chat(self, text):
        self.history.append("user", text)
        self._ask_ai([{"role": "user", "content": text}], {"kind": "chat"})

    def _on_ai_reply(self, text, ok, meta):
        meta = meta or {}
        kind = meta.get("kind", "chat")
        if not ok:
            if not bool(self.config.get("ai_fallback_enabled", True)):
                return
            text = str(self.config.get("ai_fallback_text", "唔……我现在有点短路了"))
        self.history.append("assistant", text, kind=kind)
        self._show_balloon(text)

    def _open_history(self):
        dlg = HistoryDialog(self.history)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        self._history_dlg = dlg  # 局部变量会被 GC：不持引用窗口闪退
        dlg.show()

    def _wire(self):
        w = self.window
        w.settingsRequested.connect(lambda: self._open_settings(0))
        w.appearanceRequested.connect(lambda: self._open_settings(1))
        w.testNotifyRequested.connect(self._test_notify)
        w.quitRequested.connect(QApplication.instance().quit)
        w.autoStartRequested.connect(self._on_auto_start)
        w.petHeadRequested.connect(self._show_pet_head)
        w.petHeadRequested.connect(lambda: self.talk.note_interaction())
        w.petHeadRequested.connect(lambda: self.affection.note_pet())
        w.chatInputRequested.connect(self._on_user_chat)
        w.historyRequested.connect(self._open_history)
        w.moved.connect(self._on_moved)

        a = self.affection
        a.tierChanged.connect(self.talk.on_affection_tier)
        a.valueChanged.connect(w.affection_label.set_affection)
        w.affection_label.set_affection(a.value())

        s = self.schedule
        s.peakStarted.connect(lambda: self._show_balloon(
            self.config.get("peak_balloon_text", "高峰时段开始啦……"), persistent=True))
        s.idleStarted.connect(lambda: self._show_balloon(
            self.config.get("idle_balloon_text", "空闲时段开始啦！"), persistent=True))
        from scheduler import is_peak
        w.status_label.set_state(is_peak())
        s.peakStarted.connect(lambda: w.status_label.set_state(True))
        s.idleStarted.connect(lambda: w.status_label.set_state(False))
        self.talk.request_talk.connect(self._on_selftalk_tag)
        self.weather.weatherChanged.connect(self.talk.set_weather)
        self.weather.weatherChanged.connect(lambda k: setattr(self, "_last_weather", k))
        self.weather.weatherError.connect(self._on_weather_error)
        self.ai.reply.connect(self._on_ai_reply)

    def _on_weather_error(self, msg):
        """天气拉取失败：只留日志，不弹通知打扰用户。"""
        petlog.log("weather error: %s" % msg)

    def _restore_position(self):
        pos = self.config.get("pet_pos")
        if isinstance(pos, list) and len(pos) == 2:
            # 恢复前钳制到当前可见屏幕：副屏/虚拟屏断开后旧坐标会在屏外，
            # 桌宠"消失只剩通知"（2026-09-01 实测坑）
            geo = QApplication.primaryScreen().availableGeometry()
            x, y = int(pos[0]), int(pos[1])
            if not geo.contains(x, y):
                petlog.log("pet_pos %s off-screen, clamp to primary" % pos)
                x = max(geo.left(), min(x, geo.right() - self.window.width()))
                y = max(geo.top(), min(y, geo.top() + 100))
            self.window.move(x, y)

    def _on_moved(self, point):
        # 位置落盘改由 PetWindow.mouseReleaseEvent 在拖动结束时执行一次，
        # 这里只做内存里的气泡锚点跟随（每像素写盘的旧做法已移除）
        if self._balloon is not None and self._balloon.isVisible():
            self._balloon.set_anchor(self.window.geometry())

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
            font_size=int(self.config.get("balance_font_size", 14) or 14),
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
        self.talk._schedule()
        self.affection.apply_config()
        if self._balloon is not None:
            self._balloon.set_top_flag(bool(self.config.get("always_on_top", True)))

    def _setup_tray(self):
        petlog.log("tray setup entered")
        self._tray_attempts = 0
        self._create_tray(1)

    def _create_tray(self, attempt):
        """创建托盘图标：左键单击显示/隐藏桌宠，右键菜单（设置 / 显示隐藏 / 退出）。

        独立组件：创建于全部窗口显示之后；创建后 2.5 秒自检图标是否真实注册，
        未注册则 hide/show 重试（最多 3 次）。图标优先用打包资源目录的
        icon.png，回退项目根目录同名文件。
        """
        icon_path = os.path.join(BUNDLE_DIR, "icon.png")
        if not os.path.isfile(icon_path):
            icon_path = os.path.join(PROJECT_DIR, "icon.png")
        icon = QIcon(icon_path) if os.path.isfile(icon_path) else QIcon.fromTheme("applications-games")
        tray = QSystemTrayIcon(icon)
        menu = QMenu()
        self._tray_toggle_action = menu.addAction("隐藏桌宠", self._toggle_pet_visible)
        menu.addAction("通知设置…", lambda: self._open_settings(0))
        menu.addAction("外观设置…", lambda: self._open_settings(1))
        menu.addSeparator()
        menu.addAction("退出", QApplication.instance().quit)
        tray.setContextMenu(menu)
        tray.setToolTip("桌宠（AI）")
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self._tray = tray
        self._tray_menu = menu
        petlog.log("tray create #%d: shown (visible=%s available=%s)" % (
            attempt, tray.isVisible(), QSystemTrayIcon.isSystemTrayAvailable()))
        QTimer.singleShot(2500, lambda: self._verify_tray(tray, attempt))

    def _verify_tray(self, tray, attempt):
        """UIA 自检：枚举任务栏与隐藏区按钮，确认桌宠图标已真实注册；
        未注册则重建托盘（最多 3 次），枚举失败时不误判。"""
        found = self._uia_tray_has_icon()
        petlog.log("tray verify #%d: found=%s" % (attempt, found))
        if found:
            self._startup_notice()
            return
        if attempt >= 3:
            petlog.log("tray verify: 放弃自动重试（图标仍未出现，请检查任务栏隐藏区）")
            return
        tray.hide()
        tray.show()
        QTimer.singleShot(2000, lambda: self._verify_tray(tray, attempt + 1))

    def _uia_tray_has_icon(self):
        try:
            from pywinauto import Desktop
            d = Desktop(backend="uia")
            names = []
            taskbar = d.window(class_name="Shell_TrayWnd")
            for b in taskbar.descendants(control_type="Button"):
                names.append(b.window_text())
            for w in d.windows():
                try:
                    if "Island" in (w.element_info.class_name or ""):
                        for b in w.descendants(control_type="Button"):
                            names.append(b.window_text())
                except Exception:
                    pass
            return any(("桌宠" in x) or ("AI" in x) for x in names)
        except Exception as e:
            petlog.log("tray verify enumeration error: %s" % e)
            return True  # 枚举失败时不误判，保持现状

    def _startup_notice(self):
        self._tray.showMessage("桌宠已启动",
                               "托盘图标已就绪；若任务栏上没有看到，请点任务栏角落的 ^ 展开隐藏图标。",
                               QSystemTrayIcon.Information, 5000)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:  # 左键单击
            self._toggle_pet_visible()

    def _toggle_pet_visible(self):
        w = self.window
        show = not w.isVisible()
        w.setVisible(show)
        if show:
            w.apply_config()  # 同步输入框/时段标签的可见性与位置
        else:
            w.chat_input.hide()
            w.status_label.hide()
            w.affection_label.hide()
        if getattr(self, "_tray_toggle_action", None):
            self._tray_toggle_action.setText("显示桌宠" if not show else "隐藏桌宠")


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
