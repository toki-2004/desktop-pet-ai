# -*- coding: utf-8 -*-
"""Offscreen smoke test for the AI edition.

Run: python tests/offscreen_smoke.py  (QT_QPA_PLATFORM=offscreen set here)
Covers: interact GIF playback, click/drag split, status label, affection,
SelfTalkMonitor tag emission, ChatHistory, ChatInput, AI presets, weather.
"""
import os
import sys
import json
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import QEventLoop, QTimer, QEvent, QPointF, QPoint, Qt  # noqa: E402
from PyQt5.QtGui import QImage, QMouseEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication, QPlainTextEdit  # noqa: E402

from affection import AffectionSystem  # noqa: E402
from ai_client import PRESETS  # noqa: E402
from chat_history import ChatHistory  # noqa: E402
from config import Config  # noqa: E402
from pet_window import PetWindow  # noqa: E402
from scheduler import is_peak  # noqa: E402
from settings_dialog import SettingsDialog  # noqa: E402
from weather import classify as wclass  # noqa: E402
import main as main_mod  # noqa: E402
import weather as weather_mod  # noqa: E402

app = QApplication(sys.argv)
tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp")
os.makedirs(tmp, exist_ok=True)
for stale in ("config_selftalk.json", "hist.json"):
    p = os.path.join(tmp, stale)
    if os.path.exists(p):
        os.remove(p)

normal_png = os.path.join(tmp, "normal.png")
img = QImage(120, 140, QImage.Format_ARGB32)
img.fill(0xFF5588CC)
img.save(normal_png, "PNG")

from PIL import Image, ImageDraw  # noqa: E402

gif_path = os.path.join(tmp, "interact.gif")
frames = []
for color in [(240, 90, 90), (90, 200, 90), (90, 120, 240)]:
    f = Image.new("RGBA", (120, 140), (0, 0, 0, 0))
    d = ImageDraw.Draw(f)
    d.ellipse([10, 10, 110, 130], fill=color + (255,))
    frames.append(f)
frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=30, loop=0)

cfg = Config(os.path.join(tmp, "config.json"))
cfg.set("pet_image", normal_png)
cfg.set("pet_interact_image", gif_path)
cfg.set("pet_head_enabled", True)

passed, failed = 0, []


def check(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
        print("  PASS", name)
    else:
        failed.append(name)
        print("  FAIL", name, detail)


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


pet = PetWindow(cfg, default_image=normal_png)
heads = []
pet.petHeadRequested.connect(lambda: heads.append(1))

# 1. interact GIF: start / restart / finish+restore
ok = pet._play_interact_once()
app.processEvents()
m1 = pet._interact_movie
check("click starts interact movie", ok and m1 is not None and m1.state() == m1.Running)
wait(40)
pet._play_interact_once()
app.processEvents()
m2 = pet._interact_movie
check("second click terminates previous movie", m2 is not None and m2 is not m1)
check("restart from frame 0", m2.currentFrameNumber() in (0, 1), m2.currentFrameNumber())
flag = {"done": False}


def poll():
    if pet._interact_movie is None:
        flag["done"] = True
        lp.quit()


lp = QEventLoop()
timer = QTimer()
timer.timeout.connect(poll)
timer.start(50)
QTimer.singleShot(2500, lp.quit)
lp.exec_()
timer.stop()
check("movie finished and cleared", flag["done"])
check("normal image restored", not pet.pet_label.pixmap().isNull())

# 2. StatusLabel
sl = pet.status_label
check("status label matches initial period", sl.text() in ("高峰时段", "空闲时段"))
check("status initial matches is_peak", (sl.text() == "高峰时段") == is_peak())
sl.set_state(not is_peak())
check("status text flips with state", (sl.text() == "高峰时段") != is_peak())

# 3. main module self-check
for sym in ("QIcon", "QSystemTrayIcon", "QMenu", "SelfTalkMonitor", "DesktopPet"):
    check("main module has " + sym, hasattr(main_mod, sym))


# 4. click vs drag
def mouse_event(etype, gp, buttons=Qt.NoButton):
    if isinstance(gp, QPointF):
        gp = gp.toPoint()
    lp2 = pet.mapFromGlobal(gp)
    return QMouseEvent(etype, QPointF(lp2), QPointF(gp), Qt.LeftButton, buttons, Qt.NoModifier)


def click_at(gp):
    QApplication.sendEvent(pet, mouse_event(QEvent.MouseButtonPress, gp, Qt.LeftButton))
    QApplication.sendEvent(pet, mouse_event(QEvent.MouseButtonRelease, gp))


pet._place_status()
check("status label sits right below pet", pet.status_label.y() == pet.y() + pet.height(),
      (pet.status_label.x(), pet.status_label.y()))
center = pet.geometry().center()
before = len(heads)
click_at(center)
app.processEvents()
check("click (release without move) plays movie", pet._interact_movie is not None)
check("click emits exactly one head signal", len(heads) == before + 1, len(heads))
wait(1800)
check("movie finished after click", pet._interact_movie is None)

drag_start = pet.geometry().center()
pos_before = (pet.x(), pet.y())
QApplication.sendEvent(pet, mouse_event(QEvent.MouseButtonPress, drag_start, Qt.LeftButton))
for dx in (10, 25, 45, 70):
    gp = drag_start + QPointF(dx, dx * 0.6)
    QApplication.sendEvent(pet, mouse_event(QEvent.MouseMove, gp, Qt.LeftButton))
    app.processEvents()
QApplication.sendEvent(pet, mouse_event(QEvent.MouseButtonRelease, drag_start + QPointF(70, 42)))
app.processEvents()
check("drag does NOT play movie", pet._interact_movie is None)
check("drag does NOT emit head signal", len(heads) == before + 1, len(heads))
check("drag actually moved the pet", (pet.x(), pet.y()) != pos_before)

# 5. affection system
cfg_aff = Config(os.path.join(tmp, "config_affection.json"))
for k, v in [("affection_initial", 70), ("affection_gain", 10), ("affection_value", 70.0),
             ("affection_last_update", 0.0)]:
    cfg_aff.set(k, v)
clock = {"t": 1000.0}
aff = AffectionSystem(cfg_aff, mono_fn=lambda: clock["t"])
tiers, vals = [], []
aff.tierChanged.connect(tiers.append)
aff.valueChanged.connect(vals.append)
check("affection initial value", aff.value() == 70.0 and aff.tier() == "mid")
clock["t"] += 1
aff.note_pet()
check("affection pet gains and enters high",
      aff.value() == 80.0 and aff.tier() == "high", (aff.value(), aff.tier()))
check("affection signals fired", "high" in tiers and 80.0 in vals)
clock["t"] += 300
aff._on_tick()
check("affection decays after idle", aff.value() == 79.0 and aff.tier() == "mid")
cfg_aff.set("affection_value", 39.0)
cfg_aff.set("affection_last_update", 0.0)
aff.apply_config()
check("affection low tier from config reload", aff.tier() == "low")

# 6. settings: affection + AI controls
# 测试里不发起真实模型列表请求（避免依赖网络/服务状态）
SettingsDialog._fetch_models = lambda self: None
dlg = SettingsDialog(cfg_aff)
check("settings has affection controls",
      hasattr(dlg, "aff_check") and hasattr(dlg, "aff_gain"))
check("settings has AI preset combo",
      hasattr(dlg, "preset_combo") and hasattr(dlg, "base_edit")
      and dlg.preset_combo.currentData() in PRESETS)
check("settings model combo editable",
      hasattr(dlg, "model_combo") and dlg.model_combo.isEditable())
check("settings has web2api message limit spin",
      hasattr(dlg, "web2api_msgs") and dlg.web2api_msgs.value() == int(cfg_aff.get("ai_web2api_max_messages", 20)))
check("settings has balance tab controls",
      hasattr(dlg, "poll_spin") and hasattr(dlg, "work_label_check")
      and hasattr(dlg, "balance_check") and hasattr(dlg, "accounts_list"))

dlg_m = SettingsDialog(cfg_aff)
dlg_m._on_models_loaded(["deepseek", "deepseek-thinking"], True)
check("models_loaded fills combo",
      dlg_m.model_combo.count() == 2
      and [dlg_m.model_combo.itemText(i) for i in range(2)] == ["deepseek", "deepseek-thinking"])
dlg_m._on_models_loaded([], False)
check("models load failure keeps editable input", dlg_m.model_combo.isEditable())

# 7. SelfTalkMonitor: emits tags (no quote pools anymore)
cfg2 = Config(os.path.join(tmp, "config_selftalk.json"))
t10 = main_mod.SelfTalkMonitor(cfg2)
tags = []
t10.request_talk.connect(tags.append)
from datetime import datetime as _dt  # noqa: E402

t10._now_fn = lambda: _dt(2026, 8, 30, 8, 0)
t10._check_context()
check("morning window fires tag", "time_morning" in tags, tags)
t10._now_fn = lambda: _dt(2026, 8, 30, 8, 10)
t10._check_context()
check("time window fires once per day", tags.count("time_morning") == 1)
t10._mono_fn = lambda: 10_000_000.0
t10._idle_fn = lambda: 46 * 60
t10._check_context()
check("idle health tag fired", "health" in tags, tags)
t10._check_context()
check("health tag cooldown", tags.count("health") == 1)
t10._check_context()
check("attention tag fired after long no-interaction", "attention" in tags)
t10.on_affection_tier("high")
check("affection tier emits tag", "affection_high" in tags)
t10.set_weather("sunny")
tags11 = []
t11 = main_mod.SelfTalkMonitor(cfg2)
t11.request_talk.connect(tags11.append)
t11.on_balance_change("up")
t11.on_balance_change("up")  # 冷却内不再触发
t11.on_balance_change("flat", working_hold=True)  # 余额下降保持期内不触发"空闲中"
check("work tags throttled and hold-aware", tags11 == ["work_up"], tags11)
t11._last_work_quote["flat"] = 0.0
t11.on_balance_change("flat")
check("flat work tag emitted", tags11 == ["work_up", "work_flat"], tags11)
check("weather tag fires", "weather_sunny" in tags)
t10.set_weather("sunny")
check("same weather once per day", tags.count("weather_sunny") == 1)
t10.set_weather("rainy")
check("different weather fires", "weather_rainy" in tags)
cfg2.set("self_talk_enabled", False)
check("disabled switch blocks emit", t10._emit_tag("random") is False)

# 8. ChatHistory: persistence + context filter
hist = ChatHistory(os.path.join(tmp, "hist.json"), max_n=50)
hist.append("user", "hi", "chat")
hist.append("assistant", "hello", "chat")
hist.append("assistant", "自言自语", "selftalk")
check("history keeps all kinds", len(hist.items) == 3)
check("history context only user/assistant", hist.context(10) == [
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "hello"},
    {"role": "assistant", "content": "自言自语"}])
hist2 = ChatHistory(os.path.join(tmp, "hist.json"), max_n=50)
check("history reloads from disk", len(hist2.items) == 3)

# 9. ChatInput: return sends signal
got_chat = []
pet.chatInputRequested.connect(got_chat.append)
pet.chat_input.setText("你好")
pet.chat_input._send()
check("chat input sends signal", got_chat == ["你好"], got_chat)
check("chat input cleared after send", pet.chat_input.text() == "")

# 9.5 wheel on affection label syncs font everywhere; affection follows pet move
from PyQt5.QtGui import QWheelEvent  # noqa: E402

pet.status_label.show()
pet.affection_label.show()
pet.chat_input.show()
pet.show()
whe = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120),
                  Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
fs0 = int(cfg.get("balance_font_size", 14))
app.sendEvent(pet.affection_label, whe)
app.processEvents()
fs1 = pet._font_size_pending
check("wheel bumps pending font size", fs1 == fs0 + 1, (fs0, fs1))
check("affection label font synced",
      pet.affection_label.font().pointSize() == max(9, fs1 - 2))
check("status label font synced",
      pet.status_label.font().pointSize() == max(9, fs1 - 2))
check("chat input font synced", pet.chat_input.font().pointSize() == fs1)
pet._save_font_size()
check("font size persisted", int(cfg.get("balance_font_size")) == fs1)

check("labels side by side same row",
      pet.affection_label.y() == pet.status_label.y()
      and pet.work_label.y() == pet.status_label.y(),
      (pet.affection_label.y(), pet.status_label.y(), pet.work_label.y()))
check("labels same height",
      pet.affection_label.height() == pet.status_label.height()
      and pet.work_label.height() == pet.status_label.height(),
      (pet.affection_label.height(), pet.status_label.height(), pet.work_label.height()))
check("affection left of status, work right of status",
      pet.affection_label.x() + pet.affection_label.width() + 6 == pet.status_label.x()
      and pet.status_label.x() + pet.status_label.width() + 6 == pet.work_label.x(),
      (pet.affection_label.x(), pet.status_label.x(), pet.work_label.x()))
group_center = (pet.affection_label.x() + pet.work_label.x() + pet.work_label.width()) // 2
pet_center = pet.x() + pet.width() // 2
check("label group centered on pet image", abs(group_center - pet_center) <= 1,
      (group_center, pet_center))
h_small = pet.status_label.height()
pet._font_size_pending = 22
pet._refresh_fonts()
app.processEvents()
check("label height adapts to font size",
      pet.status_label.height() > h_small
      and pet.affection_label.height() == pet.status_label.height()
      and pet.work_label.height() == pet.status_label.height(),
      (h_small, pet.status_label.height()))
pet._font_size_pending = None
pet._refresh_fonts()

# 滚轮反复放大缩小：宽高必须对称往返，不能只增不减（setFixedHeight 导致的
# sizeHint 棘轮 bug 回归测试）
w0, h0 = pet.affection_label.width(), pet.affection_label.height()
for _ in range(3):
    pet.affection_label.wheelEvent(QWheelEvent(
        QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120),
        Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
pet._save_font_size()
for _ in range(3):
    pet.affection_label.wheelEvent(QWheelEvent(
        QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
        Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
pet._save_font_size()
check("wheel zoom in/out returns to original size",
      (pet.affection_label.width(), pet.affection_label.height()) == (w0, h0),
      (w0, h0, pet.affection_label.width(), pet.affection_label.height()))

group_total = pet.affection_label.width() + 6 + pet.status_label.width() + 6 + pet.work_label.width()
check("chat input width matches label group",
      pet.chat_input.width() == group_total,
      (pet.chat_input.width(), group_total))
pet._font_size_pending = 20
pet._refresh_fonts()
app.processEvents()
group_total2 = pet.affection_label.width() + 6 + pet.status_label.width() + 6 + pet.work_label.width()
check("chat input width follows group on font change",
      pet.chat_input.width() == group_total2,
      (pet.chat_input.width(), group_total2))
pet._font_size_pending = None
pet._refresh_fonts()

_chat_pm = pet.chat_input.grab()
_chat_img = _chat_pm.toImage()
check("chat input rounded corners transparent",
      _chat_img.pixelColor(1, 1).alpha() == 0, _chat_img.pixelColor(1, 1).alpha())
check("chat input paints content",
      _chat_img.pixelColor(_chat_img.width() // 2, _chat_img.height() // 2).alpha() > 0)

old_aff_pos = (pet.affection_label.x(), pet.affection_label.y())
pet.move(pet.x() + 40, pet.y() + 20)
app.processEvents()
check("affection label follows pet move",
      pet.affection_label.x() == old_aff_pos[0] + 40
      and pet.affection_label.y() == old_aff_pos[1] + 20,
      (old_aff_pos, (pet.affection_label.x(), pet.affection_label.y())))

# 9.55 wheel-zoom on pet keeps affection label glued to pet bottom row
pet.affection_label.wheelEvent(QWheelEvent(QPointF(5, 5), QPointF(5, 5),
                                           QPoint(0, 0), QPoint(0, -120),
                                           Qt.NoButton, Qt.NoModifier,
                                           Qt.NoScrollPhase, False))
pet._save_font_size()
zoom_status_y = pet.status_label.y()
zoom_aff_y = pet.affection_label.y()
pet.wheelEvent(QWheelEvent(QPointF(5, 5), QPointF(5, 5),
                           QPoint(0, 0), QPoint(0, -120),
                           Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))
app.processEvents()
check("shrink pet: status label follows bottom", pet.status_label.y() <= zoom_status_y)
check("shrink pet: affection label follows too",
      pet.affection_label.y() == pet.status_label.y(),
      (zoom_aff_y, pet.affection_label.y(), pet.status_label.y()))

# 9.6 一键召回：不改变大小，放到当前屏幕正中间；退出保存位置与缩放
pet.move(12, 34)
app.processEvents()
size_before = (pet.width(), pet.height())
pet.recall_to_center()
geo = app.primaryScreen().availableGeometry()
check("recall centers pet without resizing",
      pet.x() == geo.x() + max(0, (geo.width() - pet.width()) // 2)
      and pet.y() == geo.y() + max(0, (geo.height() - pet.height()) // 2)
      and (pet.width(), pet.height()) == size_before,
      (pet.x(), pet.y(), geo.x(), geo.y(), geo.width(), geo.height(), size_before))
pet.save_state()
check("save_state persists position and scale",
      cfg.get("pet_pos") == [pet.x(), pet.y()]
      and abs(float(cfg.get("pet_scale", 1.0)) - pet._scale) < 0.001,
      (cfg.get("pet_pos"), cfg.get("pet_scale"), pet._scale))

# 9.7 余额文本与工作状态标签
check("balance/work labels exist",
      hasattr(pet, "balance_label") and hasattr(pet, "work_label"))
pet.work_label.show()
pet._place_work()
check("work label sits right of status label",
      pet.work_label.x() == pet.status_label.x() + pet.status_label.width() + 6
      and pet.work_label.y() == pet.status_label.y(),
      (pet.work_label.x(), pet.status_label.x(), pet.work_label.y()))
pet.work_label.set_state("down")
check("work label shows working state",
      pet.work_label.current_state() == "down" and "工作" in pet.work_label.text())
pet.balance_label.set_balance("¥12.34")
check("balance label text updates", pet.balance_label.text() == "¥12.34")

# 10. AI presets structure
check("presets have base_url and model",
      all("base_url" in p and "model" in p for p in PRESETS.values()))
check("local preset points at 127.0.0.1",
      PRESETS["deepseek_web2api"]["base_url"].startswith("http://127.0.0.1"))
check("local preset carries vendor key",
      PRESETS["deepseek_web2api"].get("key") == "sk-local")
dlg_pk = SettingsDialog(cfg)
dlg_pk.preset_combo.setCurrentIndex(list(PRESETS).index("deepseek_web2api"))
dlg_pk._apply_preset()
check("preset apply fills local key", dlg_pk.key_edit.text() == "sk-local")
check("deepseek open platform preset exists",
      "deepseek_open" in PRESETS
      and PRESETS["deepseek_open"]["base_url"].startswith("https://api.deepseek.com")
      and PRESETS["deepseek_open"]["model"] == "deepseek-chat")

# 10.5 web2api manager: probe monkeypatched, rebind button wired
import web2api as w2a  # noqa: E402

check("web2api vendor dir exists", os.path.isdir(w2a.VENDOR_DIR))
orig_get = w2a.requests.get


class _Resp:
    def __init__(self, code):
        self.status_code = code


w2a.requests.get = lambda *a, **k: _Resp(200)
check("web2api service_alive on 200", w2a.service_alive() is True)
w2a.requests.get = lambda *a, **k: _Resp(401)
check("web2api service_alive on 401 (key mismatch)", w2a.service_alive() is True)
w2a.requests.get = lambda *a, **k: (_ for _ in ()).throw(OSError())
check("web2api service_alive False on error", w2a.service_alive() is False)
w2a.requests.get = orig_get

_restart_calls = []
_orig_restart = w2a._restart_for_config
w2a._restart_for_config = lambda: _restart_calls.append(1)
with open(os.path.join(w2a.VENDOR_DIR, "config.json"), "r", encoding="utf-8") as _f:
    _cur_max = int((json.load(_f).get("conversation") or {}).get("maxMessages", 20))
w2a.apply_max_messages(_cur_max)  # 与当前 vendor 配置相同：不应触发重启
check("apply_max_messages no-op when unchanged", _restart_calls == [])
w2a._restart_for_config = _orig_restart

import balance as balance_mod  # noqa: E402
check("balance normalize clamps tiny negative",
      balance_mod.normalize_total(-0.004) == 0.0
      and balance_mod.normalize_total(12.34) == 12.34
      and balance_mod.normalize_total(None) == 0.0)

dlg_rb = SettingsDialog(cfg, rebind_callback=lambda: None)
check("settings has rebind button with callback",
      hasattr(dlg_rb, "rebind_btn") and dlg_rb.rebind_btn.isEnabled())
dlg_nb = SettingsDialog(cfg)
check("no rebind button without callback", not hasattr(dlg_nb, "rebind_btn"))

# 11. app-level wiring with fake weather
class _FakeWeather(weather_mod.WeatherMonitor):
    def start(self):
        self.weatherChanged.emit("sunny")


class _FakeBalance(main_mod.BalanceMonitor):
    def start(self):
        pass  # 不发起真实网络轮询；信号链路由 _wire 的 selftest emit 覆盖


main_mod.WeatherMonitor = _FakeWeather
main_mod.BalanceMonitor = _FakeBalance
pet2 = main_mod.DesktopPet()
app.processEvents()
check("app-level: pet window wired", pet2.window is not None
      and pet2.ai is not None and pet2.history is not None)
check("app-level: chat input visible", pet2.window.chat_input.isVisible())
check("app-level: balance selftest wired", pet2.window.balance_label.text() == "selftest")
check("app-level: prompt includes work state", "工作状态" in pet2._system_prompt())
check("prompt includes current time",
      re.search(r"当前时间：\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", pet2._system_prompt()) is not None)
check("prompt tag translated to neutral zh",
      "天气晴朗" in pet2._system_prompt("weather_sunny")
      and "weather_sunny" not in pet2._system_prompt("weather_sunny")
      and "深夜时段" in pet2._system_prompt("time_midnight"))

# 11.5 history dialog survives GC (kept reference on self)
pet2._open_history()
app.processEvents()
check("history dialog visible after processEvents", pet2._history_dlg.isVisible())
_hist_views = pet2._history_dlg.findChildren(QPlainTextEdit)
check("history dialog scrolled to latest",
      bool(_hist_views)
      and _hist_views[0].verticalScrollBar().value() == _hist_views[0].verticalScrollBar().maximum(),
      (_hist_views[0].verticalScrollBar().value(), _hist_views[0].verticalScrollBar().maximum()) if _hist_views else None)
pet2._open_settings(0)
app.processEvents()
check("settings dialog visible after _open_settings",
      pet2._settings_dlg is not None and pet2._settings_dlg.isVisible())

# 12. float text: padding fits text, position clamped on screen
_ft_text = "通知功能正常"
pet.show_float_text(_ft_text, "#22C55E")
app.processEvents()
_floats = list(pet._floats)
check("float text: label created", len(_floats) == 1)
if _floats:
    _fl = _floats[0]
    check("float text: width fits text",
          _fl.width() >= _fl.fontMetrics().horizontalAdvance(_ft_text) + 60,
          (_fl.width(), _fl.fontMetrics().horizontalAdvance(_ft_text)))
    check("float text: centered alignment",
          int(_fl.alignment()) == int(Qt.AlignCenter), int(_fl.alignment()))
    _avail = QApplication.primaryScreen().availableGeometry()
    check("float text: on screen",
          _fl.x() >= _avail.left() and _fl.y() >= _avail.top()
          and _fl.x() + _fl.width() <= _avail.right(),
          (_fl.x(), _fl.y(), _fl.width(), _avail))

# 12.5 balloon 5s cooldown
import time as _t
pet2._last_balloon_at = 0.0
pet2._show_balloon("first balloon")
app.processEvents()
_b1 = pet2._balloon
pet2._show_balloon("second balloon")
app.processEvents()
check("balloon cooldown suppresses second",
      pet2._balloon is _b1 and _b1._text == "first balloon")
pet2._last_balloon_at = _t.monotonic() - 6.0
pet2._show_balloon("third balloon")
app.processEvents()
check("balloon cooldown expires after 5s",
      pet2._balloon is not None and pet2._balloon is not _b1
      and pet2._balloon._text == "third balloon")

# 12. weather classify
check("wclass sunny", wclass(0, 5) == "sunny")
check("wclass cloudy", wclass(3, 5) == "cloudy")
check("wclass rainy", wclass(61, 5) == "rainy")
check("wclass snowy", wclass(71, 5) == "snowy")
check("wclass windy overrides clear", wclass(0, 45) == "windy")

print("")
print("RESULT: {} passed, {} failed".format(passed, len(failed)))
if failed:
    print("FAILED:", " | ".join(failed))
sys.exit(1 if failed else 0)
