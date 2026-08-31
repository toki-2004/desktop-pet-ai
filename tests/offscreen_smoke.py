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

from balloon import ThinkingBalloon  # noqa: E402
from config import Config  # noqa: E402
from pet_window import PetWindow, StatusLabel  # noqa: E402
from scheduler import is_peak  # noqa: E402
from settings_dialog import SettingsDialog  # noqa: E402

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

# 7.6 播放/恢复的 resize 后，时段标签必须跟着归位（回归：曾卡在旧位置）
wide_gif = os.path.join(tmp, "wide.gif")
wide_frames = []
for color in [(90, 140, 220), (220, 140, 90)]:
    f = Image.new("RGBA", (400, 160), (0, 0, 0, 0))
    dd = ImageDraw.Draw(f)
    dd.rounded_rectangle([10, 10, 390, 150], 30, fill=color + (255,))
    wide_frames.append(f)
wide_frames[0].save(wide_gif, save_all=True, append_images=wide_frames[1:], duration=30, loop=0)
wide_saved = cfg.get("pet_interact_image")
cfg.set("pet_interact_image", wide_gif)
normal_h = pet.height()
status_rest_y = pet.status_label.y()
pet._play_interact_once()
app.processEvents()
check("status label frozen during playback", pet.status_label.y() == status_rest_y,
      (pet.status_label.y(), status_rest_y))
for _ in range(40):
    app.processEvents()
    if pet._interact_movie is None and pet.height() == normal_h:
        break
    l7 = QEventLoop()
    QTimer.singleShot(50, l7.quit)
    l7.exec_()
check("pet restored to normal height", pet.height() == normal_h, (pet.height(), normal_h))
check("status label back under pet after restore",
      pet.status_label.y() == pet.y() + pet.height(),
      (pet.status_label.y(), pet.y() + pet.height()))
check("status label centered under pet",
      abs((pet.status_label.x() + pet.status_label.width() / 2) - (pet.x() + pet.width() / 2)) <= 1)
check("work label sits right of status label",
      pet.work_label.x() > pet.status_label.x()
      and pet.work_label.y() == pet.status_label.y(),
      (pet.work_label.x(), pet.status_label.x(), pet.work_label.y()))
check("affection label sits left of status group",
      pet.affection_label.x() < pet.status_label.x()
      and pet.affection_label.y() == pet.status_label.y(),
      (pet.affection_label.x(), pet.status_label.x(), pet.affection_label.y()))
cfg.set("pet_interact_image", wide_saved or "")
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

# 13. 好感度系统：摸头增加 / 随时间衰减 / 档位切换触发
from affection import AffectionSystem  # noqa: E402

cfg_aff = Config(os.path.join(tmp, "config_affection.json"))
cfg_aff.set("affection_initial", 70)
cfg_aff.set("affection_max", 100)
cfg_aff.set("affection_gain", 10)
cfg_aff.set("affection_decay_sec", 300)
cfg_aff.set("affection_high_threshold_pct", 80)
cfg_aff.set("affection_low_threshold_pct", 40)
cfg_aff.set("affection_value", 70.0)
cfg_aff.set("affection_last_update", 0.0)

clock = {"t": 1000.0}
aff_tiers = []
aff_vals = []
aff = AffectionSystem(cfg_aff, mono_fn=lambda: clock["t"])
aff.tierChanged.connect(aff_tiers.append)
aff.valueChanged.connect(aff_vals.append)
check("affection initial value", aff.value() == 70.0 and aff.tier() == "mid")

clock["t"] += 1
aff.note_pet()  # 摸头一次 +10 -> 80，进入 high 档
check("affection pet gains and enters high",
      aff.value() == 80.0 and aff.tier() == "high", (aff.value(), aff.tier()))
check("affection tier signal on pet", "high" in aff_tiers, aff_tiers)
check("affection value signal on pet", 80.0 in aff_vals, aff_vals)

clock["t"] += 300  # 5 分钟未互动：下降 1 点，离开 high 档回到 mid
aff._on_tick()
check("affection decays after idle", aff.value() == 79.0 and aff.tier() == "mid",
      (aff.value(), aff.tier()))
check("affection tier signal on decay", "mid" in aff_tiers, aff_tiers)

clock["t"] += 1200  # 再 20 分钟：共下降 4 点 -> 75
aff._on_tick()
check("affection decay batches by interval", aff.value() == 75.0, aff.value())

clock["t"] += 9000  # 2.5 小时：下降 30 点 -> 45（仍在 mid）
aff._on_tick()
check("affection decay floors at zero", aff.value() >= 0.0 and aff.tier() == "mid",
      (aff.value(), aff.tier()))

# 低好感：持续不摸头直到跌破低阈值 -> low
cfg_aff.set("affection_value", 39.0)
cfg_aff.set("affection_last_update", 0.0)
aff.apply_config()
check("affection low tier from config reload", aff.tier() == "low",
      (aff.value(), aff.tier()))

# 摸头语录分档：高好感优先 [high] 池，低好感优先 [low] 池，未知档回退 neutral
import json as _json  # noqa: E402
from main import pick_head_quote  # noqa: E402

head_aff = os.path.join(tmp, "head_aff.json")
_json.dump([
    "[high] 被摸头最幸福了！",
    "[low] 等了好久的摸摸！",
    "普通的摸头回应。",
], open(head_aff, "w", encoding="utf-8"), ensure_ascii=False)
check("head quote picks high pool",
      pick_head_quote(head_aff, [], tier="high") == "被摸头最幸福了！")
check("head quote picks low pool",
      pick_head_quote(head_aff, [], tier="low") == "等了好久的摸摸！")
check("head quote falls back to neutral",
      pick_head_quote(head_aff, [], tier="mid") == "普通的摸头回应。")
check("head quote legacy plain list",
      pick_head_quote("", ["旧语录兜底"], tier="low") == "旧语录兜底")

# 工作状态标签三态：降低=工作中，不变=空闲中，升高=充值了
from pet_window import WorkingStatusLabel  # noqa: E402

work_pet = PetWindow(cfg_aff, default_image=normal_png)
wlab = work_pet.work_label
wlab.set_state("down")
check("work label shows working on balance down", wlab.text() == "工作中", wlab.text())
# 保持期内 flat 不切回空闲（新语义）；过期后由专门的保持期测试覆盖
wlab._last_down = _time.monotonic() - 9999
wlab.set_state("flat")
check("work label shows idle on balance flat (after hold)", wlab.text() == "空闲中", wlab.text())
wlab.set_state("up")
check("work label shows recharge on balance up", wlab.text() == "充值了", wlab.text())
wlab.set_state("unknown")
check("work label unknown before first fetch", wlab.text() == "余额未知", wlab.text())

# 14. 工作状态保持期：余额下降后 3 分钟内 flat 不切回"空闲中"
import time as _time2  # noqa: E402

work_hold = PetWindow(cfg_aff, default_image=normal_png).work_label
work_hold.set_hold_sec(180)
work_hold.set_state("down")
check("work hold: down -> 工作中", work_hold.text() == "工作中", work_hold.text())
# 模拟 60 秒后 flat：保持期内应维持"工作中"
work_hold._last_down = _time2.monotonic() - 60
work_hold.set_state("flat")
check("work hold: flat within hold keeps 工作中", work_hold.text() == "工作中", work_hold.text())
check("work hold: in_working_hold true", work_hold.in_working_hold() is True)
# 模拟 200 秒后 flat：超过保持期，允许切回"空闲中"
work_hold._last_down = _time2.monotonic() - 200
work_hold.set_state("flat")
check("work hold: flat after hold switches to 空闲中", work_hold.text() == "空闲中", work_hold.text())
check("work hold: in_working_hold false", work_hold.in_working_hold() is False)
# 语录侧：保持期内 flat 不触发"空闲中"语录（独立实例验证）
import json as _json2  # noqa: E402

talk_hold = os.path.join(tmp, "talk_hold.json")
_json2.dump([
    "[work_flat] 余额纹丝不动，主人正在享受悠闲时光～",
    "[work_down] 余额一路向下，主人的干劲一路向上～",
], open(talk_hold, "w", encoding="utf-8"), ensure_ascii=False)
t_hold = main_mod.SelfTalkMonitor(cfg2, talk_hold)
said_hold = []
t_hold.talk.connect(said_hold.append)
t_hold._mono_fn = lambda: 30_000_000.0
t_hold.on_balance_change("down")
check("work hold: down quote fires", any("余额一路向下" in x for x in said_hold), said_hold)
t_hold.on_balance_change("flat", working_hold=True)
check("work hold: flat quote suppressed during hold",
      not any("余额纹丝不动" in x for x in said_hold), said_hold)
t_hold._last_work_quote["flat"] = 0.0  # 清冷却
t_hold.on_balance_change("flat", working_hold=False)
check("work hold: flat quote fires after hold",
      any("余额纹丝不动" in x for x in said_hold), said_hold)

# 设置页好感/状态控件
dlg_aff = SettingsDialog(cfg_aff)
check("settings has affection controls",
      hasattr(dlg_aff, "aff_check") and dlg_aff.aff_gain.value() == 10
      and dlg_aff.work_label_check.isChecked())
check("settings has work hold control", hasattr(dlg_aff, "work_hold_spin")
      and dlg_aff.work_hold_spin.value() == 180, dlg_aff.work_hold_spin.value())

# 10. 自言自语情境触发：显式时段标签 / 分类 / 健康 / 求关注 / 余额变动
import json as _json  # noqa: E402
from datetime import datetime as _dt  # noqa: E402

talk10 = os.path.join(tmp, "talk10.json")
_json.dump([
    "[morning] 早安主人，新的一天也要加油哦～",
    "[afternoon] 下午茶时间～主人喝口水吧。",
    "[midnight] 夜深了……主人早点睡嘛。",
    "记得喝水哦，主人。",
    "主人，摸摸我嘛～",
    "余额稳稳的，安全感满满～",
    "[work_down] 余额一路向下，主人的干劲一路向上～",
    "[work_flat] 余额纹丝不动，主人正在享受悠闲时光～",
    "[work_up] 余额上涨啦！是主人充值了！钱包辛苦了～",
    "普通随机话语。",
    "[time] 周末愉快，今天有什么安排吗？",   # 旧写法兼容：按内容细分到 weekend
    "[sunny] 阳光真好，适合出去走走。",
    "[rainy] 下雨了，出门记得带伞哦。",
    "[windy] 起风了，主人多穿一件吧。",
    "[weather] 今天的天气，全看主人的心情！",
], open(talk10, "w", encoding="utf-8"), ensure_ascii=False)
t10 = main_mod.SelfTalkMonitor(cfg2, talk10)
said = []
t10.talk.connect(said.append)

# 分类：显式时段标签 / [time] 兼容 / 其他类别
check("classify [morning]", any("早安" in x for x in t10._pools.get("time_morning", [])))
check("classify [afternoon]", any("下午茶" in x for x in t10._pools.get("time_afternoon", [])))
check("classify [midnight]", any("夜深了" in x for x in t10._pools.get("time_midnight", [])))
check("classify legacy [time] -> weekend", any("周末愉快" in x for x in t10._pools.get("time_weekend", [])))
check("classify health", any("喝水" in x for x in t10._pools.get("health", [])))
check("classify attention", any("摸摸" in x for x in t10._pools.get("attention", [])))
check("classify balance", any("余额" in x for x in t10._pools.get("balance", [])))
check("classify work_down", any("余额一路向下" in x for x in t10._pools.get("work_down", [])))
check("classify work_flat", any("余额纹丝不动" in x for x in t10._pools.get("work_flat", [])))
check("classify work_up", any("主人充值了" in x for x in t10._pools.get("work_up", [])))
check("classify random", "普通随机话语。" in t10._pools.get("random", []))
check("classify [sunny]", any("阳光真好" in x for x in t10._pools.get("weather_sunny", [])))
check("classify [rainy]", any("出门记得带伞" in x for x in t10._pools.get("weather_rainy", [])))
check("classify [windy]", any("多穿一件" in x for x in t10._pools.get("weather_windy", [])))
check("weather pools stay separate from random",
      "阳光真好" not in t10._pools.get("random", []) and "weather" in t10._pools)
check("affection pools exist and stay silent when empty",
      all(x in t10._pools for x in ("affection_high", "affection_mid", "affection_low"))
      and t10._pick("affection_high") is None)

# 时段窗口：清晨 8 点触发 morning；下午 14 点触发 afternoon；深夜 23:30 触发 midnight
t10._now_fn = lambda: _dt(2026, 8, 30, 8, 0)
t10._check_context()
check("morning window fires", any("早安" in x for x in said), said)
t10._now_fn = lambda: _dt(2026, 8, 30, 14, 0)
t10._check_context()
check("afternoon window fires", any("下午茶" in x for x in said), said)
t10._now_fn = lambda: _dt(2026, 8, 30, 23, 30)
t10._check_context()
check("midnight window fires", any("夜深了" in x for x in said), said)
count_then = len(said)
t10._now_fn = lambda: _dt(2026, 8, 30, 23, 40)
t10._check_context()
check("each window fires once per day", len(said) == count_then)

# 正午 12 点：time_noon 池为空 → 宁可沉默（时段错配回归）
said_before_noon = len(said)
t10._now_fn = lambda: _dt(2026, 8, 30, 12, 0)
t10._check_context()
check("REGRESSION: empty noon pool stays silent", len(said) == said_before_noon, said)

# 健康 / 求关注 / 余额变动
t10._mono_fn = lambda: 10_000_000.0
t10._idle_fn = lambda: 46 * 60
t10._check_context()
check("idle health quote fired", any("喝水" in x for x in said))
t10._check_context()
check("health quote cooldown", len([x for x in said if "喝水" in x]) == 1)
t10._check_context()
check("attention quote fired after long no-interaction", any("摸摸" in x for x in said))
t10.balance_chance = 1.0
t10.on_balance_change()
check("balance quote fired on change", any("余额稳稳" in x for x in said))
t10.on_balance_change()
check("balance quote throttled", len([x for x in said if "余额稳稳" in x]) == 1)

# 工作状态语录：余额降低/不变/升高分别触发，各自冷却
said_before_work = len(said)
t10.balance_chance = 0.0  # 隔离余额语录概率，专注工作状态触发
t10._mono_fn = lambda: 20_000_000.0
t10.on_balance_change("down")
check("work_down fires when balance decreases", any("余额一路向下" in x for x in said), said)
count_work_down = len([x for x in said if "余额一路向下" in x])
t10.on_balance_change("down")
check("work_down throttled", len([x for x in said if "余额一路向下" in x]) == count_work_down)
t10.on_balance_change("flat")
check("work_flat fires when balance unchanged", any("余额纹丝不动" in x for x in said), said)
t10.on_balance_change("up")
check("work_up fires when balance rises", any("主人充值了" in x for x in said), said)
check("balance quotes untouched by work quotes",
      len([x for x in said if "余额稳稳" in x]) == 1)

# 好感档位语录：on_affection_tier 映射到对应标签
said_before_tier = len(said)
t10.on_affection_tier("high")
check("affection tier emits tag", len(said) == said_before_tier)  # 空池静默
t10._pools["affection_high"] = ["被主人宠着的感觉真好！"]
t10.on_affection_tier("high")
check("affection_high quote fires", any("被主人宠着" in x for x in said), said)

# 天气触发：同一天气每天至多一次，换天气触发不同文本，空池回退通用天气池
t10.set_weather("sunny")
check("weather sunny fires", any("阳光真好" in x for x in said), said)
count_sunny = len(said)
t10.set_weather("sunny")
check("same weather once per day", len(said) == count_sunny)
t10.set_weather("rainy")
check("different weather fires different text", any("出门记得带伞" in x for x in said), said)
t10.set_weather("snowy")  # weather_snowy 池为空 -> 回退通用 [weather] 池
check("empty weather pool falls back to generic", any("全看主人的心情" in x for x in said), said)

# 9. 完整应用级回归：DesktopPet 装配后余额标签必须脱离占位
# （2026-08-30 事故：托盘编辑把 _wire 拦腰截断，余额/时段/语录信号整体失联，
#   组件级测试抓不到装配错误——必须构造完整 DesktopPet 验证一次）
import main as main_mod2  # noqa: E402
import weather as weather_mod  # noqa: E402


class _FakeWeather(weather_mod.WeatherMonitor):
    """离屏测试：start 时同步发一次天气信号，不访问网络。"""
    def start(self):
        self.weatherChanged.emit("sunny")


main_mod2.WeatherMonitor = _FakeWeather
pet2 = main_mod2.DesktopPet()
app.processEvents()
label2 = pet2.window.balance_label.text()
check("app-level: balance label left placeholder", label2 != "余额…", label2)
check("app-level: label shows selftest or real balance",
      label2 == "selftest" or label2.startswith("¥"), label2)
check("app-level: weather wired to self-talk",
      pet2.talk._fired_weather.get("weather_sunny") == pet2.talk._now_fn().date().isoformat(),
      pet2.talk._fired_weather)

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

# 11. 字号统一：通知/余额/浮动文字共用 balance_font_size
cfg_f = Config(os.path.join(tmp, "font_config.json"))
cfg_f.set("balance_font_size", 22)
b_big = ThinkingBalloon("主人，有新消息啦！", font_size=22)
b_small = ThinkingBalloon("主人，有新消息啦！", font_size=8)
check("balloon font size follows config with CJK visual compensation",
      b_big._font_size == max(6, round(22 * 0.7))
      and b_small._font_size == max(6, round(8 * 0.7))
      and b_big.width() > b_small.width(),
      (b_big._font_size, b_small._font_size, b_big.width(), b_small.width()))

pet_f = PetWindow(cfg_f, default_image=normal_png)
pet_f.balance_label._apply_style()
check("balance label font point size unified", pet_f.balance_label.font().pointSize() == 22,
      pet_f.balance_label.font().pointSize())
pet_f.show_float_text("字号统一", "#22C55E")
float_styles = [lab.styleSheet() for lab in list(pet_f._floats)]
check("float text uses pt and same size",
      any("font-size:22pt" in s and "px" not in s for s in float_styles), float_styles)

dlg_f = SettingsDialog(cfg_f)
check("settings dialog exposes unified font size", dlg_f.font_spin.value() == 22,
      dlg_f.font_spin.value())
dlg_f.font_spin.setValue(16)
dlg_f._save()
check("settings save writes unified font size", cfg_f.get("balance_font_size") == 16,
      cfg_f.get("balance_font_size"))

# 滚轮调字号：状态标签必须同步刷新（曾漏掉该入口，只有设置路径生效）
from PyQt5.QtCore import QPoint  # noqa: E402
from PyQt5.QtGui import QWheelEvent  # noqa: E402

wheel_up = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120),
                       Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
QApplication.sendEvent(pet_f.balance_label, wheel_up)
app.processEvents()
fs_wheel = int(cfg_f.get("balance_font_size"))
check("wheel scales balance font", fs_wheel > 16, fs_wheel)
check("wheel syncs status label font",
      pet_f.status_label.font().pointSize() == max(9, fs_wheel - 2),
      (fs_wheel, pet_f.status_label.font().pointSize()))

# 12. 天气：WMO 分类映射 + 看门狗（模拟 DNS 挂死）
from weather import classify as _wclass  # noqa: E402

check("wclass sunny", _wclass(0, 5) == "sunny")
check("wclass cloudy", _wclass(3, 5) == "cloudy")
check("wclass rainy", _wclass(61, 5) == "rainy")
check("wclass snowy", _wclass(71, 5) == "snowy")
check("wclass foggy", _wclass(45, 5) == "foggy")
check("wclass stormy", _wclass(95, 5) == "stormy")
check("wclass windy overrides clear", _wclass(0, 45) == "windy")

errs_w, kinds_w = [], []
fetch_calls = {"n": 0}


def counting_fetch():
    if fetch_calls["n"] == 0:
        fetch_calls["n"] += 1
        _time.sleep(5)  # 仅首次挂死，模拟 DNS 卡死
    fetch_calls["n"] += 1
    return ("sunny", "ok-test")


wm = weather_mod.WeatherMonitor(
    cfg2, fetch_fn=counting_fetch, watchdog_ms=300)
wm.weatherError.connect(errs_w.append)
wm.weatherChanged.connect(kinds_w.append)
wm.refresh()
loop_w = QEventLoop()
QTimer.singleShot(700, loop_w.quit)
loop_w.exec_()
check("weather watchdog fires on hung fetch", any("超时" in e for e in errs_w), errs_w)
got_w = False
for _ in range(60):
    if "sunny" in kinds_w:
        got_w = True
        break
    loop_w2 = QEventLoop()
    QTimer.singleShot(150, loop_w2.quit)
    loop_w2.exec_()
check("weather retry succeeds after watchdog", got_w and "sunny" in kinds_w, kinds_w)

print("")
print("RESULT: {} passed, {} failed".format(passed, len(failed)))
if failed:
    print("FAILED:", " | ".join(failed))
sys.exit(1 if failed else 0)
