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
from ai_client import AIClient, PRESETS
from chat_history import ChatHistory, HistoryDialog
from balance import BalanceMonitor
from running_apps import audio_apps, media_track, running_apps
import autostart
import web2api

FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    PROJECT_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", PROJECT_DIR)
else:
    PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = PROJECT_DIR

CONFIG_PATH = os.path.join(PROJECT_DIR, "config.json")
DEFAULT_IMAGE = os.path.join(BUNDLE_DIR, "assets", "ds拟人.png")
DEFAULT_INTERACT = os.path.join(BUNDLE_DIR, "assets", "ds拟人_q.gif")


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


# 情境标签 -> 中性中文描述（不直接给英文参数，避免 AI 对 weather_sunny 之类
# 联想出"太阳出来"等时间敏感内容；具体天气已由"当前天气"行给出）。
TAG_ZH = {
    "time_morning": "晨间时段",
    "time_noon": "午间时段",
    "time_afternoon": "午后时段",
    "time_evening": "晚间时段",
    "time_midnight": "深夜时段",
    "time_weekend": "周末时段",
    "health": "久坐健康提醒",
    "attention": "主人长时间未互动",
    "affection_high": "好感度达到高位",
    "affection_mid": "好感度保持中等",
    "affection_low": "好感度处于低位",
    "work_up": "自己刚收到充值（余额上升）",
    "work_down": "自己开始工作了（余额下降）",
    "work_flat": "自己空闲了（余额平稳）",
    "weather_sunny": "天气晴朗",
    "weather_cloudy": "天气多云",
    "weather_rainy": "天气有雨",
    "weather_snowy": "天气有雪",
    "weather_foggy": "天气有雾",
    "weather_windy": "天气有风",
    "weather_stormy": "天气有风暴",
    "weather": "天气变化",
    "random": "随机闲聊",
}


class SelfTalkMonitor(QObject):
    """情境自言自语：时段/健康/求关注/好感/天气/余额/随机等触发器命中后
    发出 request_talk 信号，由 AI 生成文本。

    self_talk_interval 现在定义为"每两次自言自语之间的最小间隔（冷却）"，
    对全部触发器生效且优先于触发器：冷却未到点的触发器不发声——
    情境类条件由 60s 检查继续等待；一次性事件（好感/天气/余额）暂存到
    心跳到点后优先补放；随机只在没有别的可说时补位。间隔 0 = 不限间隔
    且关闭随机闲聊（仅情境触发，与原版一致）。"""

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
    WORK_THROTTLE_S = 1800         # 工作状态 AI 触发冷却（每方向）

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._timer = QTimer(self)          # 心跳：冷却到点放行情境/暂存事件/随机
        self._timer.timeout.connect(self._fire_random)
        self._context_timer = QTimer(self)  # time/health/attention：情境检查
        self._context_timer.timeout.connect(self._check_context)
        self._last_talk = 0.0     # 上次真正发声的自言自语时间（全局冷却基准）
        self._pending = []        # 冷却期内被拦住的一次性触发标签，到点优先补放
        self._last_pat = 0.0      # monotonic：最近一次摸头/单击互动
        self._last_attention = 0.0
        self._last_health = 0.0
        self._last_work_quote = {"up": 0.0, "down": 0.0, "flat": 0.0}
        self._fired_rules = {}    # time 规则 -> 已触发日期
        self._fired_weather = {}   # 天气池 -> 已触发日期
        # 可注入（测试/外部调整）
        self._now_fn = datetime.now
        self._mono_fn = time.monotonic
        self._idle_fn = _input_idle_seconds
        self._schedule()

    def _emit_tag(self, tag, hold=False):
        """统一出口：总开关拦截 + 全局冷却（文本由 AI 生成）。

        冷却未到点时：hold=True（好感/天气/余额等一次性事件）暂存进
        _pending 等待心跳补放；情境类（时段/健康/求关注）不传 hold，
        调用方不标记"已触发"，下一轮条件仍满足时继续尝试。
        """
        if not bool(self.config.get("self_talk_enabled", True)):
            return False
        if not self._gate_open():
            if hold and tag not in self._pending:
                self._pending.append(tag)
            return False
        self._last_talk = self._mono_fn()
        self.request_talk.emit(tag)
        return True

    def _interval(self):
        """两次自言自语之间的最小间隔秒数；0 = 不限间隔（并关闭随机心跳）。"""
        val = self.config.get("self_talk_interval", 300)
        try:
            sec = int(val if val is not None else 300)
        except (TypeError, ValueError):
            sec = 300
        return max(0, sec)

    def _gate_open(self):
        return self._mono_fn() - self._last_talk >= self._interval()

    # ---------- 触发方式 ----------
    def _fire_random(self):
        """心跳：冷却到点后先让情境/暂存的一次性触发优先发声，都没有才随机。"""
        self._check_context()
        if not self._gate_open():   # 情境触发达到了这次发言机会
            self._schedule()
            return
        if self._pending:
            self._emit_tag(self._pending.pop(0))
        else:
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
            self._emit_tag(tag, hold=True)

    def on_balance_change(self, direction=None, working_hold=False):
        """余额变动事件后调用（direction: "up"/"down"/"flat"）。

        按方向触发工作状态 AI 文本（工作中/空闲中/充值了，各自冷却）；
        working_hold=True 表示仍处于"余额下降后的保持期"，此时 flat 方向
        不再触发"空闲中"（与工作标签显示保持一致）。
        """
        if direction not in ("up", "down", "flat"):
            return
        if direction == "flat" and working_hold:
            return
        mono = self._mono_fn()
        if mono - self._last_work_quote[direction] < self.WORK_THROTTLE_S:
            return
        tag = {"up": "work_up", "down": "work_down", "flat": "work_flat"}[direction]
        if self._emit_tag(tag, hold=True):
            self._last_work_quote[direction] = mono

    def set_weather(self, kind):
        """天气变化时调用：当天同一天气至多触发一次（换天气/跨天可再触发）。"""
        tag = ("weather_" + kind) if kind in self.WEATHER_KINDS else "weather"
        today = self._now_fn().date().isoformat()
        if not bool(self.config.get("self_talk_enabled", True)):
            return
        if self._fired_weather.get(tag) == today:
            return
        self._fired_weather[tag] = today  # 先占当天名额：立即说，或冷却到点后补说
        self._emit_tag(tag, hold=True)

    def note_interaction(self):
        """摸头/主动聊天等用户互动发生时调用：刷新求关注计时，并把互动计入
        自言自语冷却——互动后的一段时间内桌宠不再主动搭话。"""
        now = self._mono_fn()
        self._last_pat = now
        self._last_talk = now

    # ---------- 开关与调度 ----------
    def _schedule(self):
        # 关闭开关或间隔 0 都要显式停心跳（间隔 0 = 不限冷却且无随机闲聊，
        # 情境触发仍由下方 60s 检查驱动；文本始终由 AI 生成）
        enabled = bool(self.config.get("self_talk_enabled", True))
        sec = self._interval()
        if not enabled:
            self._timer.stop()
            self._context_timer.stop()
            self._pending[:] = []  # 丢弃冷却期内暂存的一次性触发，避免复启后补说旧事
            return
        if sec > 0:
            self._timer.start(sec * 1000)
        else:
            self._timer.stop()
            self._pending[:] = []
        if not self._context_timer.isActive():
            self._context_timer.start(60000)


class DesktopPet:
    STARTUP_AI_DELAY_S = 10.0  # 重启后推迟首条 AI 请求，让"内置 AI 已就绪"先弹出

    def __init__(self):
        self.config = Config(CONFIG_PATH)
        self._start_mono = time.monotonic()
        if not self.config.get("pet_image"):
            self.config.set(
                "pet_image", DEFAULT_IMAGE if os.path.exists(DEFAULT_IMAGE) else ""
            )
        if autostart.is_enabled():
            self.config.set("auto_start", True)
        # 旧配置迁移：内置服务端口从 8000 挪到 3000
        if (self.config.get("ai_preset") == "deepseek_web2api"
                and str(self.config.get("ai_base_url", "")).endswith(":8000/v1")):
            self.config.set("ai_base_url", "http://127.0.0.1:3000/v1")
        # 旧配置迁移：内置服务要求 Bearer sk-local，空 key 会一直 401
        if (self.config.get("ai_preset") == "deepseek_web2api"
                and not self.config.get("ai_api_key")):
            self.config.set("ai_api_key", PRESETS["deepseek_web2api"]["key"])
        self.window = PetWindow(self.config, default_image=DEFAULT_IMAGE)
        self.schedule = ScheduleMonitor()
        self.talk = SelfTalkMonitor(self.config)
        self.ai = AIClient(self.config)
        self.history = ChatHistory(
            os.path.join(PROJECT_DIR, "chat_history.json"),
            self.config.get("chat_history_max", 200))
        self.affection = AffectionSystem(self.config)
        self.weather = WeatherMonitor(self.config)
        self.balance = BalanceMonitor(self.config)
        self._balloon = None
        self._special_active = False
        self._last_error_ts = 0.0
        self._settings_dlg = None
        self.web2api = web2api.Manager()
        self.web2api.status.connect(self._on_web2api_status)
        # 内置免费 AI（DeepSeek 网页对话）自带对话记录：人设只需在每次
        # 新对话的第一条请求注入（启动/重连后的首请求），不逐条重复。
        self._convo_primed = False
        self._wire()
        self._restore_position()
        if not self.config.get("pet_interact_image") and os.path.exists(DEFAULT_INTERACT):
            self.config.set("pet_interact_image", DEFAULT_INTERACT)
        self.window.show()
        if not os.environ.get("PET_SMOKE"):
            self.weather.start()  # 冒烟模式不访问网络（天气拉取放后台线程，会拖慢退出）
            self.balance.start()  # 余额轮询（多平台账号，未绑定则显示"未绑定账号"）
            if os.path.isdir(web2api.VENDOR_DIR):
                self.web2api.ensure_async()  # 探测/拉起内置 AI；未绑定会弹登录
        self._setup_tray()  # 托盘（延迟自检组件）：窗口与监控就绪后创建

    def _on_web2api_status(self, ok, msg):
        if msg:
            # 服务拉起/重连/登录后 = DeepSeek 新对话：下一条请求重注入人设
            self._convo_primed = False
        if msg == "login":
            self._show_balloon("即将清空旧登录态并打开全新的 DeepSeek 登录浏览器，可直接登录或切换账号；登录完成后关闭那个控制台窗口～")
            return
        if msg:
            self._show_balloon(msg)

    # ---------- AI 生成 ----------
    def _system_prompt(self, tag="", persona=True):
        """组装 system prompt；persona=False 时只给动态情境，不再重复人设。"""
        tier_map = {"high": "好感度很高", "mid": "好感度一般", "low": "好感度较低"}
        tier = self.affection.tier()
        work_map = {"up": "充值了", "down": "工作中",
                    "flat": "空闲中", "unknown": "未知"}
        work = work_map.get(self.window.work_label.current_state(), "未知")
        from scheduler import is_peak
        period = "高峰时段" if is_peak() else "空闲时段"
        parts = []
        if persona:
            text = str(self.config.get("ai_persona", "")).strip()
            if text:
                parts.append(text)
        parts.extend([
            "当前情境：%s；%s。" % (period, tier_map.get(tier, tier)),
            "工作状态：%s。注意：该状态描述我自己（AI/本机后台）："
            "工作中/空闲中 = 我在不在跑任务，充值了 = 我的账户到账；"
            "它不是主人的工作状态，主人此刻在做什么请以“当前打开的应用”为准。" % work,
            "当前时间：%s。" % time.strftime("%Y-%m-%d %H:%M:%S"),
        ])
        apps = running_apps()
        if apps:
            parts.append(
                "当前打开的应用（排最前的为前台窗口，可据此判断主人在做什么）：%s。"
                % "；".join(apps))
        aud = audio_apps()
        if aud:
            parts.append("正在发声的应用（含后台播放的音乐/视频）：%s。" % "、".join(aud))
        tr = media_track()
        if tr:
            parts.append("正在播放音乐：%s - %s（%s）。"
                         % (tr.get("title"), tr.get("artist"), tr.get("app")))
        if getattr(self, "_last_weather", ""):
            parts.append("当前天气：%s。" % self._last_weather)
        if tag:
            parts.append("本次触发情境：%s。" % TAG_ZH.get(tag, tag))
        parts.append("回复要非常简短（一两句话），不要复述情境描述。")
        return "\n".join(parts)

    def _ask_ai(self, messages, meta):
        # 重启后 10 秒内不向后端发第一条请求：让"内置 AI 已就绪"等启动通知先
        # 弹出并显示完，避免它覆盖桌宠刚启动时主动说的第一句话。
        remain = (self._start_mono + self.STARTUP_AI_DELAY_S) - time.monotonic()
        if remain > 0:
            QTimer.singleShot(int(remain * 1000) + 20,
                              lambda: self._ask_ai(messages, meta))
            return
        # 内置免费 AI 的网页对话自带上下文：人设 + 历史回放只放在每次新对话的
        # 第一条请求（启动/重连后的首请求）；后续请求只发新消息 + 动态情境，
        # 避免同一大段 prompt 反复出现在对话记录里导致 AI 回复刻板。
        builtin = self.config.get("ai_preset") == "deepseek_web2api"
        fresh = not builtin or not self._convo_primed
        if fresh:
            self._convo_primed = True
        n = int(self.config.get("ai_context_n", 10) or 10)
        msgs = (self.history.context(n) if fresh else []) + messages  # 主线程纯内存拼接（快）
        # system prompt 组装（枚举窗口/采样音频/起 PowerShell 查歌曲）整体在
        # AI worker 线程执行，避免摸头/对话时卡住 GUI（GIF 播放延迟的根因）
        self.ai.chat(
            msgs, meta,
            system_fn=lambda: self._system_prompt(meta.get("tag", ""), persona=fresh))

    def _on_selftalk_tag(self, tag):
        reason = TAG_ZH.get(tag, tag)
        self._ask_ai(
            [{"role": "user",
              "content": "（桌宠主动搭话，触发原因：%s。请围绕这个原因说一句应景的话，简短口语化。）" % reason}],
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
            # 请求失败后服务可能重连并新开对话：下一条请求重注入人设
            self._convo_primed = False
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
        w.chatInputRequested.connect(lambda: self.talk.note_interaction())
        w.historyRequested.connect(self._open_history)
        w.balanceVisibleRequested.connect(self._on_balance_visible)
        w.moved.connect(self._on_moved)

        a = self.affection
        a.tierChanged.connect(self.talk.on_affection_tier)
        a.valueChanged.connect(w.affection_label.set_affection)
        w.affection_label.set_affection(a.value())

        m = self.balance
        m.balanceUpdated.connect(w.set_balance_text)
        m.balanceUp.connect(lambda t: w.show_float_text(t, "#22C55E"))
        m.balanceDown.connect(lambda t: w.show_float_text(t, "#EF4444"))
        m.balanceUp.connect(lambda t: w.work_label.set_state("up"))
        m.balanceDown.connect(lambda t: w.work_label.set_state("down"))
        m.balanceFlat.connect(lambda t: w.work_label.set_state("flat"))
        m.balanceUp.connect(lambda t: self.talk.on_balance_change("up"))
        m.balanceDown.connect(lambda t: self.talk.on_balance_change("down"))
        m.balanceFlat.connect(lambda t: self.talk.on_balance_change(
            "flat", working_hold=w.work_label.in_working_hold()))
        m.fetchError.connect(lambda msg: petlog.log("balance error: %s" % msg))
        m.balanceUpdated.emit(0.0, "selftest")  # 冒烟：验证信号链路

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

    def _on_balance_visible(self, visible):
        self.window.set_balance_visible(visible)

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
        # 通知弹幕冷却：5 秒内不重复弹出普通通知，防多情境/自言自语同时触发刷屏；
        # 需确认的特殊通知不受冷却影响。
        if not persistent and \
                time.monotonic() - getattr(self, "_last_balloon_at", 0.0) < 5.0:
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
        self._last_balloon_at = time.monotonic()
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
        dlg = SettingsDialog(self.config, initial_tab=tab,
                             rebind_callback=self._rebind_web2api)
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.destroyed.connect(self._on_settings_destroyed)
        dlg.accepted.connect(self._on_settings_applied)
        self._settings_dlg = dlg
        dlg.show()

    def _rebind_web2api(self):
        self.web2api.rebind_async()

    def _on_settings_destroyed(self):
        self._settings_dlg = None

    def _on_settings_applied(self):
        self._settings_dlg = None
        self.window.apply_config()
        self.talk._schedule()
        self.balance.set_interval(int(self.config.get("poll_interval_sec", 3)))
        self.balance.poll()
        web2api.apply_max_messages(self.config.get("ai_web2api_max_messages", 20))
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
        menu.addAction("一键召回（移到屏幕正中）", self._recall_pet)
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

    def _recall_pet(self):
        """一键召回：保持大小，把桌宠放到当前屏幕正中间（防掉出屏幕无法操作）。"""
        self.window.recall_to_center()

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
            w.balance_label.hide()
            w.work_label.hide()
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
    app.aboutToQuit.connect(pet.window.save_state)  # 退出前记住位置与大小

    if os.environ.get("PET_SMOKE"):
        QTimer.singleShot(1500, pet._test_notify)
        QTimer.singleShot(4500, app.quit)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
