# -*- coding: utf-8 -*-
"""桌宠核心入口：透明置顶桌宠 + 思考云线通知 + DeepSeek 余额 + 高峰/空闲提醒。"""
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
    """情境自言自语：按语录内容自动分类，用不同的触发方式呈现。

    触发方式（按内容关键词自动归类；也可在语录前加 [标签] 前缀强制指定，
    显示时自动去掉前缀，如 "[time] 早安主人，新的一天也要加油哦～"）：
      [time]      时点问候：进入对应时间段后当天触发一次（早安/午饭/下午茶/夜晚/周末）
      [health]    健康提醒：键鼠闲置满 45 分钟触发一次（久坐/喝水/活动/护眼）
      [attention] 求关注：超过 90 分钟没有摸头/单击互动时触发
      [balance]   余额变动：余额增减事件后概率触发（每小时至多一次）
      [random]    随机闲聊：按设置的间隔随机触发（原有行为）
    """

    talk = pyqtSignal(str)

    KEYWORDS = {
        "time": ("早安", "中午", "下午茶", "天黑", "夜深", "深夜", "周末", "夕阳",
                 "晚安", "零点", "清晨", "晚饭"),
        "health": ("久坐", "喝水", "伸懒腰", "眼睛", "肩", "健康", "揉肩", "走两步",
                   "深呼吸", "三餐", "午饭", "吃饭", "站起来", "水杯", "活动", "保暖",
                   "护眼", "休息眼睛"),
        "balance": ("余额", "钱包", "支出", "账单"),
        "work": ("代码", "Bug", "编译", "键盘", "工作", "效率", "保存", "产出"),
        "weather": ("下雨", "阳光", "天气", "起风"),
        "attention": ("摸摸", "陪聊", "想我", "点点我", "无聊", "聊聊天", "陪我"),
        "game": ("游戏", "操作", "胜利"),
    }
    TIME_SUBTAG = (  # time 大类内部的时段细分（按内容关键词自动归类用）
        (("早安", "清晨"), "morning"),
        (("中午", "午饭"), "noon"),
        (("下午", "下午茶"), "afternoon"),
        (("天黑", "夕阳", "傍晚", "晚饭"), "evening"),
        (("夜深", "深夜", "零点", "早点睡"), "midnight"),
        (("周末",), "weekend"),
    )
    TIME_SUBTAGS = {"morning", "noon", "afternoon", "evening", "midnight", "weekend"}
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
    BALANCE_CHANCE = 0.35          # 余额变动后触发余额语录的概率
    BALANCE_THROTTLE_S = 3600      # 余额语录冷却

    def __init__(self, config, text_file):
        super().__init__()
        self.config = config
        self.text_file = text_file
        self._pools = {}
        self._timer = QTimer(self)          # random：随机闲聊
        self._timer.timeout.connect(self._fire_random)
        self._context_timer = QTimer(self)  # time/health/attention：情境检查
        self._context_timer.timeout.connect(self._check_context)
        self._last_pat = 0.0      # monotonic：最近一次摸头/单击互动
        self._last_attention = 0.0
        self._last_health = 0.0
        self._last_balance_quote = 0.0
        self._fired_rules = {}    # time 规则 -> 已触发日期
        # 可注入（测试/外部调整）
        self._now_fn = datetime.now
        self._mono_fn = time.monotonic
        self._idle_fn = _input_idle_seconds
        self.balance_chance = self.BALANCE_CHANCE
        self._schedule()

    # ---------- 语录分类 ----------
    def _classify(self, text):
        """返回 (触发类别, 正文)。

        [tag] 前缀强制指定类别；否则按关键词归类。time 大类必须细分到
        具体时段（早安/午饭/...），细分不出则归入随机池——否则时段窗口
        会从随机池抽到错时段的语录（如下午弹"夜深了"）。
        """
        text = str(text).strip()
        m = re.match(r"^\[(\w+)\]\s*(.*)$", text)
        forced = m.group(1).lower() if m else None
        body = m.group(2) if m else text
        if forced is not None:
            if forced == "time":  # 兼容旧写法：按内容细分到具体时段
                forced = self._time_subtag(body) or "random"
            if forced in self.TIME_SUBTAGS:
                return "time_" + forced, body
            return forced, body
        for t, kws in self.KEYWORDS.items():
            if any(k in body for k in kws):
                if t == "time":
                    sub = self._time_subtag(body)
                    return ("time_" + sub, body) if sub else ("random", body)
                return t, body
        return "random", body

    def _time_subtag(self, body):
        for kws, sub in self.TIME_SUBTAG:
            if any(k in body for k in kws):
                return sub
        return None

    def _load_texts(self):
        texts = load_quote_file(self.text_file, self.config.get("self_talk_texts") or [])
        self._pools = {}
        for t in texts:
            tag, body = self._classify(t)
            self._pools.setdefault(tag, []).append(body)
        # 时段无关的内容池（work/weather/game）没有专属触发方式，
        # 并入随机闲聊轮换，避免刚性打标后这些语录永远无法展示
        for tag in ("work", "weather", "game"):
            extra = self._pools.pop(tag, [])
            self._pools["random"] = self._pools.get("random", []) + extra
        return len(texts)

    def _pick(self, tag):
        pool = self._pools.get(tag)
        if not pool:
            # 时段子池为空时宁可沉默，也不回退随机池（否则时段错配，如下午弹"夜深了"）
            if tag.startswith("time_"):
                return None
            pool = self._pools.get("random") or []
        return random.choice(pool) if pool else None

    def _emit_tag(self, tag):
        """统一出口：总开关拦截 + 按类别取语录 + 发信号（去前缀后的正文）。"""
        if not bool(self.config.get("self_talk_enabled", True)):
            return False
        text = self._pick(tag)
        if not text:
            return False
        self.talk.emit(text)
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

    def on_balance_change(self):
        """余额增减事件后调用：概率触发一条余额类语录（有冷却）。"""
        mono = self._mono_fn()
        if (mono - self._last_balance_quote >= self.BALANCE_THROTTLE_S
                and random.random() < self.balance_chance):
            if self._emit_tag("balance"):
                self._last_balance_quote = mono

    def note_interaction(self):
        """摸头/单击互动发生时调用：刷新求关注计时。"""
        self._last_pat = self._mono_fn()

    # ---------- 开关与调度 ----------
    def _schedule(self):
        # 关闭开关、文本库为空、间隔 0 都要显式停表（random 与情境检查一起停）
        enabled = bool(self.config.get("self_talk_enabled", True))
        val = self.config.get("self_talk_interval", 300)
        try:
            sec = int(val if val is not None else 300)
        except (TypeError, ValueError):
            sec = 300
        if not enabled or not self._load_texts():
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
        self._setup_tray()  # 托盘（延迟自检组件）：窗口与监控就绪后创建

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
        w.petHeadRequested.connect(lambda: self.talk.note_interaction())
        w.moved.connect(self._on_moved)
        m = self.monitor
        m.balanceUpdated.connect(w.set_balance_text)
        petlog.log("wire: balanceUpdated connected (thread %s)" % threading.get_ident())
        self.monitor.balanceUpdated.emit(0.0, "selftest")
        petlog.log("wire: selftest emit returned")
        m.balanceUp.connect(lambda t: w.show_float_text(t, "#22C55E"))
        m.balanceDown.connect(lambda t: w.show_float_text(t, "#EF4444"))
        m.balanceUp.connect(lambda t: self.talk.on_balance_change())
        m.balanceDown.connect(lambda t: self.talk.on_balance_change())
        m.fetchError.connect(self._on_fetch_error)

        s = self.schedule
        s.peakStarted.connect(lambda: self._show_balloon(
            self.config.get("peak_balloon_text", "高峰时段开始啦……"), persistent=True))
        s.idleStarted.connect(lambda: self._show_balloon(
            self.config.get("idle_balloon_text", "空闲时段开始啦！"), persistent=True))
        # 时段常态显示：启动即定初始状态，切换时同步刷新（置顶层级同余额文本）
        from scheduler import is_peak
        w.status_label.set_state(is_peak())
        s.peakStarted.connect(lambda: w.status_label.set_state(True))
        s.idleStarted.connect(lambda: w.status_label.set_state(False))
        self.talk.talk.connect(self._show_balloon)

    def _restore_position(self):
        pos = self.config.get("pet_pos")
        if isinstance(pos, list) and len(pos) == 2:
            self.window.move(pos[0], pos[1])

    def _on_moved(self, point):
        # 位置落盘改由 PetWindow.mouseReleaseEvent 在拖动结束时执行一次，
        # 这里只做内存里的气泡锚点跟随（每像素写盘的旧做法已移除）
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
        tray.setToolTip("桌宠（余额与提醒）")
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
            return any(("桌宠" in x) or ("余额与提醒" in x) for x in names)
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
            w.apply_config()  # 同步余额/时段标签的可见性与位置
        else:
            w.balance_label.hide()
            w.status_label.hide()
        if getattr(self, "_tray_toggle_action", None):
            self._tray_toggle_action.setText("显示桌宠" if not show else "隐藏桌宠")

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
