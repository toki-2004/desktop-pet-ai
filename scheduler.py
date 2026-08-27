# -*- coding: utf-8 -*-
"""高峰/空闲时段监控：北京时间周一至五 9:00-12:00、14:00-18:00 为高峰。"""
from datetime import datetime
from zoneinfo import ZoneInfo

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

TZ = ZoneInfo("Asia/Shanghai")


def is_peak(dt=None):
    dt = dt or datetime.now(TZ)
    if dt.weekday() >= 5:
        return False
    h = dt.hour
    return (9 <= h < 12) or (14 <= h < 18)


class ScheduleMonitor(QObject):
    peakStarted = pyqtSignal()
    idleStarted = pyqtSignal()

    def __init__(self, interval_ms=30000):
        super().__init__()
        self._peak = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check)
        self._timer.start(interval_ms)
        self.check()

    def check(self):
        p = is_peak()
        if self._peak is None:
            self._peak = p
            return
        if p != self._peak:
            self._peak = p
            (self.peakStarted if p else self.idleStarted).emit()
