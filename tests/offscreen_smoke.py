# -*- coding: utf-8 -*-
"""Offscreen smoke test for the AI edition.

Run: python tests/offscreen_smoke.py  (QT_QPA_PLATFORM=offscreen set here)
Covers: interact GIF playback, click/drag split, status label, affection,
SelfTalkMonitor tag emission, ChatHistory, ChatInput, AI presets, weather.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import QEventLoop, QTimer, QEvent, QPointF, QPoint, Qt  # noqa: E402
from PyQt5.QtGui import QImage, QMouseEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

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
dlg = SettingsDialog(cfg_aff)
check("settings has affection controls",
      hasattr(dlg, "aff_check") and hasattr(dlg, "aff_gain"))
check("settings has AI preset combo",
      hasattr(dlg, "preset_combo") and hasattr(dlg, "base_edit")
      and dlg.preset_combo.currentData() in PRESETS)

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

old_aff_pos = (pet.affection_label.x(), pet.affection_label.y())
pet.move(pet.x() + 40, pet.y() + 20)
app.processEvents()
check("affection label follows pet move",
      pet.affection_label.x() == old_aff_pos[0] + 40
      and pet.affection_label.y() == old_aff_pos[1] + 20,
      (old_aff_pos, (pet.affection_label.x(), pet.affection_label.y())))

# 10. AI presets structure
check("presets have base_url and model",
      all("base_url" in p and "model" in p for p in PRESETS.values()))
check("local preset points at 127.0.0.1",
      PRESETS["deepseek_web2api"]["base_url"].startswith("http://127.0.0.1"))

# 11. app-level wiring with fake weather
class _FakeWeather(weather_mod.WeatherMonitor):
    def start(self):
        self.weatherChanged.emit("sunny")


main_mod.WeatherMonitor = _FakeWeather
pet2 = main_mod.DesktopPet()
app.processEvents()
check("app-level: pet window wired", pet2.window is not None
      and pet2.ai is not None and pet2.history is not None)
check("app-level: chat input visible", pet2.window.chat_input.isVisible())

# 11.5 history dialog survives GC (kept reference on self)
pet2._open_history()
app.processEvents()
check("history dialog visible after processEvents", pet2._history_dlg.isVisible())

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
