# -*- coding: utf-8 -*-
"""Offscreen smoke test: single-click plays the interact GIF once.

Run: python tests/offscreen_smoke.py
Verifies (QT_QPA_PLATFORM=offscreen):
  1. _play_interact_once() starts a QMovie on click;
  2. a second call terminates the previous movie and restarts from frame 0;
  3. after the last frame the pet returns to the normal image;
  4. StatusLabel reflects peak/idle state.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import QCoreApplication, QEventLoop, QTimer, QEvent, QPointF, Qt  # noqa: E402
from PyQt5.QtGui import QImage  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from config import Config  # noqa: E402
from pet_window import PetWindow, StatusLabel  # noqa: E402
from scheduler import is_peak  # noqa: E402

app = QApplication(sys.argv)

tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp")
os.makedirs(tmp, exist_ok=True)

# 生成测试素材：常态静态 PNG + 3 帧 30ms 的互动 GIF
normal_png = os.path.join(tmp, "normal.png")
Image_ = QImage(120, 140, QImage.Format_ARGB32)
Image_.fill(0xFF5588CC)
Image_.save(normal_png, "PNG")

gif_path = os.path.join(tmp, "interact.gif")
from PIL import Image, ImageDraw  # noqa: E402

frames = []
for color in [(240, 90, 90), (90, 200, 90), (90, 120, 240)]:
    f = Image.new("RGBA", (120, 140), (0, 0, 0, 0))
    d = ImageDraw.Draw(f)
    d.ellipse([10, 10, 110, 130], fill=color + (255,))
    frames.append(f)
frames[0].save(gif_path, save_all=True, append_images=frames[1:], duration=30, loop=0)
TOTAL = 3

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

pet = PetWindow(cfg, default_image=normal_png)
quotes = []
pet.petHeadRequested.connect(lambda: quotes.append(1))

# 1. 单击播放：movie 启动
ok = pet._play_interact_once()
app.processEvents()
m1 = pet._interact_movie
check("click starts interact movie", ok and m1 is not None and m1.state() == m1.Running)

# 2. 连点：旧播放被终止，新的从头开始
loop = QEventLoop()
QTimer.singleShot(40, loop.quit)  # 让旧 movie 走几帧
loop.exec_()
pet._play_interact_once()
app.processEvents()
m2 = pet._interact_movie
check("second click terminates previous movie", m2 is not None and m2 is not m1)
check("restart from frame 0", m2.currentFrameNumber() in (0, 1), m2.currentFrameNumber())

# 3. 播完自动恢复常态（3 帧 x 30ms，留 2.5s 余量轮询）
restored = {"flag": False, "waited": 0}
def poll():
    restored["waited"] += 50
    if pet._interact_movie is None:
        restored["flag"] = True
        loop2.quit()
    elif restored["waited"] > 2500:
        loop2.quit()
loop2 = QEventLoop()
timer = QTimer()
timer.timeout.connect(poll)
timer.start(50)
loop2.exec_()
timer.stop()
check("movie finished and cleared", restored["flag"])
check("normal image restored", not pet.pet_label.pixmap().isNull())

# 4. StatusLabel
sl = pet.status_label
check("status label matches initial period", sl.text() in ("高峰时段", "空闲时段"))
check("status initial matches is_peak", (sl.text() == "高峰时段") == is_peak())
sl.set_state(not is_peak())
check("status text flips with state", (sl.text() == "高峰时段") != is_peak())

# 6. main 模块级导入自检：托盘功能用到 QIcon 等符号（import 不触发 main()）
import main as main_mod  # noqa: E402
for sym in ("QIcon", "QSystemTrayIcon", "QMenu"):
    check("main module has " + sym, hasattr(main_mod, sym))

# 7. 位置与拖动/单击行为（真实鼠标事件模拟）
from PyQt5.QtGui import QMouseEvent  # noqa: E402


def mouse_event(etype, gp, buttons=Qt.NoButton):
    if isinstance(gp, QPointF):
        gp = gp.toPoint()
    lp = pet.mapFromGlobal(gp)
    return QMouseEvent(etype, QPointF(lp), QPointF(gp), Qt.LeftButton, buttons, Qt.NoModifier)


def click_at(gp):
    QApplication.sendEvent(pet, mouse_event(QEvent.MouseButtonPress, gp, Qt.LeftButton))
    QApplication.sendEvent(pet, mouse_event(QEvent.MouseButtonRelease, gp))


pet._place_status()
check("status label sits right below pet", pet.status_label.y() == pet.y() + pet.height(),
      (pet.status_label.x(), pet.status_label.y(), pet.x(), pet.y(), pet.height()))
center = pet.geometry().center()

before = len(quotes)
click_at(center)
app.processEvents()
check("click (release without move) plays movie", pet._interact_movie is not None)
check("click emits exactly one head quote", len(quotes) == before + 1, len(quotes))
loop4 = QEventLoop()
QTimer.singleShot(1800, loop4.quit)  # 3 帧 x 30ms 播完
loop4.exec_()
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
check("drag does NOT emit quote", len(quotes) == before + 1, len(quotes))
check("drag actually moved the pet", (pet.x(), pet.y()) != pos_before)
pet._play_interact_once()  # 清理：结束残留动画
app.processEvents()

# 7.5 互动动画尺寸上限：大于常态桌宠的 GIF 必须缩到常态显示尺寸以内
big_gif = os.path.join(tmp, "big.gif")
big_frames = []
for color in [(200, 80, 80), (80, 200, 80)]:
    f = Image.new("RGBA", (400, 500), (0, 0, 0, 0))
    d = ImageDraw.Draw(f)
    d.ellipse([30, 30, 370, 470], fill=color + (255,))
    big_frames.append(f)
big_frames[0].save(big_gif, save_all=True, append_images=big_frames[1:], duration=40, loop=0)
big_saved = cfg.get("pet_interact_image")
cfg.set("pet_interact_image", big_gif)
pet._play_interact_once()
app.processEvents()
cap = pet._normal_display_size or pet._current_size
lw, lh = pet.pet_label.width(), pet.pet_label.height()
check("interact capped to normal display size", lw <= cap.width() + 1 and lh <= cap.height() + 1,
      (lw, lh, cap.width(), cap.height()))
cfg.set("pet_interact_image", big_saved or "")
pet._play_interact_once()
app.processEvents()

# 8. 余额看门狗：查询挂死时按时放弃并重试成功
import time as _time  # noqa: E402
import platforms  # noqa: E402
from balance import BalanceMonitor  # noqa: E402

errors8 = []
balances8 = []
cfg2 = Config(os.path.join(tmp, "config_balance.json"))
cfg2.set("accounts", {"测试账号": {"platform": "deepseek", "api_key": "sk-dummy"}})
m2 = BalanceMonitor(cfg2, poll_timeout_ms=300)
m2.fetchError.connect(errors8.append)
m2.balanceUpdated.connect(lambda t, s: balances8.append(s))


def hang_fetch(key):
    _time.sleep(5)  # 模拟 DNS 卡死：requests timeout 管不到的无限挂起
    return (9.99, "CNY")


platforms.PROVIDERS["deepseek"].fetch = hang_fetch
m2.start()
loop5 = QEventLoop()
QTimer.singleShot(700, loop5.quit)
loop5.exec_()
check("watchdog fires on hung fetch", any("查询超时" in e for e in errors8), errors8)
platforms.PROVIDERS["deepseek"].fetch = lambda key: (12.34, "CNY")  # 恢复后离线模拟成功
got = False
for _ in range(30):
    if balances8:
        got = True
        break
    l6 = QEventLoop()
    QTimer.singleShot(150, l6.quit)
    l6.exec_()
check("retry after watchdog succeeds", got and balances8[-1].startswith("¥"), balances8)
check("polling released after success", m2._polling is False and m2._timeouts == 0)

# 10. 自言自语情境触发：分类 / 时点 / 健康 / 求关注 / 余额变动
import json as _json  # noqa: E402
from datetime import datetime as _dt  # noqa: E402

talk10 = os.path.join(tmp, "talk10.json")
_json.dump([
    "[time] 早安主人，新的一天也要加油哦～",
    "记得喝水哦，主人。",
    "主人，摸摸我嘛～",
    "余额稳稳的，安全感满满～",
    "普通随机话语。",
], open(talk10, "w", encoding="utf-8"), ensure_ascii=False)
t10 = main_mod.SelfTalkMonitor(cfg2, talk10)
said = []
t10.talk.connect(said.append)

check("classify time_morning", any("早安" in x for x in t10._pools.get("time_morning", [])))
check("classify health", any("喝水" in x for x in t10._pools.get("health", [])))
check("classify attention", any("摸摸" in x for x in t10._pools.get("attention", [])))
check("classify balance", any("余额" in x for x in t10._pools.get("balance", [])))
check("classify random", "普通随机话语。" in t10._pools.get("random", []))

t10._now_fn = lambda: _dt(2026, 8, 30, 9, 0)  # 周日上午 9 点
t10._check_context()
check("time window fired (morning)", any(x.startswith("早安") for x in said), said)
count_after_time = len(said)
t10._check_context()
check("time rule fires once per day", len(said) == count_after_time)

t10._mono_fn = lambda: 10_000_000.0  # 快进单调时钟（越过大冷却阈值）
t10._idle_fn = lambda: 46 * 60       # 闲置 46 分钟
t10._check_context()
check("idle health quote fired", any("喝水" in x for x in said))
t10._check_context()
check("health quote cooldown", len([x for x in said if "喝水" in x]) == 1)

t10._check_context()
check("attention quote fired after long no-interaction", any("摸摸" in x for x in said))
t10.balance_chance = 1.0
t10.on_balance_change()
check("balance quote fired on change", any("余额" in x for x in said))
t10.on_balance_change()
check("balance quote throttled", len([x for x in said if "余额" in x and "安全感" in x]) == 1)

# 9. 完整应用级回归：DesktopPet 装配后余额标签必须脱离占位
# （2026-08-30 事故：托盘编辑把 _wire 拦腰截断，余额/时段/语录信号整体失联，
#   组件级测试抓不到装配错误——必须构造完整 DesktopPet 验证一次）
import main as main_mod2  # noqa: E402
pet2 = main_mod2.DesktopPet()
app.processEvents()
label2 = pet2.window.balance_label.text()
check("app-level: balance label left placeholder", label2 != "余额…", label2)
check("app-level: label shows selftest or real balance",
      label2 == "selftest" or label2.startswith("¥"), label2)

# 5. 配色渲染：高峰红系/空闲绿系，纯色边框 + 半透明底纹
def render_colors(state):
    sl.set_state(state)
    app.processEvents()
    img = sl.grab().toImage()
    w, h = img.width(), img.height()
    return img.pixelColor(1, h // 2), img.pixelColor(w // 2, 4)  # 边框采样 / 底纹采样

border_p, fill_p = render_colors(True)
check("peak border is red family", border_p.red() > 150 and border_p.red() > border_p.green() + 40,
      (border_p.red(), border_p.green(), border_p.blue()))
check("peak fill is semi-transparent", 0 < fill_p.alpha() < 255, fill_p.alpha())
border_i, fill_i = render_colors(False)
check("idle border is green family", border_i.green() > border_i.red() + 20,
      (border_i.red(), border_i.green(), border_i.blue()))
check("idle fill is semi-transparent", 0 < fill_i.alpha() < 255, fill_i.alpha())

print("")
print("RESULT: {} passed, {} failed".format(passed, len(failed)))
if failed:
    print("FAILED:", " | ".join(failed))
sys.exit(1 if failed else 0)
