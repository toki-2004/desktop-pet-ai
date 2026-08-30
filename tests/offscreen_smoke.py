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

from PyQt5.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402
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
