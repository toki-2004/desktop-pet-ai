# -*- coding: utf-8 -*-
"""好感度系统：摸头/单击互动增加好感，长时间不互动随时间衰减。

设计：
- 好感值持久化在 config（affection_value / affection_last_update），
  桌宠退出期间同样按时间衰减，重启后接续（不因退出回满）。
- 档位：high / mid / low，阈值按最大值百分比配置
  （affection_high_threshold_pct / affection_low_threshold_pct）。
- 档位切换时发 tierChanged 信号，由 main.py 转成自言自语
  [affection_high] / [affection_low] / [affection_normal] 触发
  （带冷却，避免连续摸头刷屏）。
- note_pet()：摸头/单击互动时增加好感并刷新"求关注"计时。
"""
import time

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

import petlog

TICK_MS = 30_000  # 衰减检查周期（每 30 秒算一次账，避免每秒刷盘）


def _f(config, key, default):
    """从配置安全读取数值：非法值回退默认。"""
    try:
        v = float(config.get(key, default))
        return v if v == v else default  # NaN 兜底
    except (TypeError, ValueError):
        return default


class AffectionSystem(QObject):
    valueChanged = pyqtSignal(float)   # 好感值变化（含持久化后回调）
    tierChanged = pyqtSignal(str)      # "high" / "mid" / "low"

    def __init__(self, config, mono_fn=time.monotonic):
        super().__init__()
        self.config = config
        self._mono_fn = mono_fn
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_tick)
        self._last_tier = None
        self._last_emit = {"high": 0.0, "mid": 0.0, "low": 0.0}
        self._load()
        self._tick.start(TICK_MS)

    # ---------- 参数 ----------
    def enabled(self):
        return bool(self.config.get("affection_enabled", True))

    def _max(self):
        return max(1.0, _f(self.config, "affection_max", 100.0))

    def _low_threshold(self):
        return self._max() * max(0.0, _f(self.config, "affection_low_threshold_pct", 40.0)) / 100.0

    def _high_threshold(self):
        return self._max() * max(0.0, _f(self.config, "affection_high_threshold_pct", 80.0)) / 100.0

    def _gain(self):
        return max(0.0, _f(self.config, "affection_gain", 5.0))

    def _decay_seconds(self):
        # 每隔多少秒下降 1 点好感（非法值回退 300 秒）
        return max(1.0, _f(self.config, "affection_decay_sec", 300.0))

    def _emit_cooldown(self):
        return max(0.0, _f(self.config, "affection_quote_cooldown_sec", 600.0))

    # ---------- 状态读写 ----------
    def _load(self):
        self._value = max(0.0, _f(self.config, "affection_value", 70.0))
        self._value = min(self._value, self._max())
        # 上次更新时刻：新档位取当前时刻，避免新用户启动立刻掉好感
        last = _f(self.config, "affection_last_update", 0.0)
        self._last_update = last if last > 0 else self._mono_fn()

    def value(self):
        return self._value

    def tier(self):
        if self._value >= self._high_threshold():
            return "high"
        if self._value < self._low_threshold():
            return "low"
        return "mid"

    def _save(self):
        # 只持久化可变化的两项，其余参数由 DEFAULT_CONFIG 兜底
        self.config.set("affection_value", round(self._value, 1))
        self.config.set("affection_last_update", self._last_update)

    # ---------- 外部事件 ----------
    def note_pet(self):
        """摸头/单击互动：好感上升，刷新衰减计时。"""
        if not self.enabled():
            return
        self._last_update = self._mono_fn()
        self._value = min(self._max(), self._value + self._gain())
        self._save()
        petlog.log("affection: pet +%s -> %s (tier %s)" % (
            self._gain(), round(self._value, 1), self.tier()))
        self._emit_if_tier_changed()
        self.valueChanged.emit(self._value)

    def reset(self, value):
        """设置页"回到初始好感"：直接覆盖当前值。"""
        self._value = max(0.0, min(self._max(), value))
        self._last_update = self._mono_fn()
        self._save()
        self._emit_if_tier_changed()
        self.valueChanged.emit(self._value)

    def apply_config(self):
        """设置保存后重载参数（上限/阈值/初始值等可能已变化）。"""
        before = self._value
        self._load()
        if abs(self._value - before) >= 0.05:
            self._save()
            self._emit_if_tier_changed()
            self.valueChanged.emit(self._value)

    # ---------- 衰减 ----------
    def _on_tick(self):
        if not self.enabled():
            return
        now = self._mono_fn()
        elapsed = now - self._last_update
        step = self._decay_seconds()
        if elapsed < step:
            return
        # 用 elapsed // step 避免 30s 一次的小数累计误差
        drop = int(elapsed // step)
        if drop <= 0:
            return
        before = self._value
        self._value = max(0.0, self._value - drop)
        self._last_update = now  # 结清本次账，下一格重新计时
        self._save()
        petlog.log("affection: decay -%d (%ds idle) -> %s" % (
            drop, int(elapsed), round(self._value, 1)))
        self._emit_if_tier_changed()
        if self._value != before:
            self.valueChanged.emit(self._value)

    # ---------- 档位触发 ----------
    def _emit_if_tier_changed(self):
        """档位切换时发一次信号（冷却期内不重复发，防连续摸头刷屏）。"""
        tier = self.tier()
        changed = tier != self._last_tier
        mono = self._mono_fn()
        cooled = mono - self._last_emit.get(tier, 0.0) >= self._emit_cooldown()
        self._last_tier = tier
        if changed and cooled:
            self._last_emit[tier] = mono
            petlog.log("affection: tier change -> %s" % tier)
            self.tierChanged.emit(tier)
