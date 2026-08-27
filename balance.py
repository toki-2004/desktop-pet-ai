# -*- coding: utf-8 -*-
"""DeepSeek 开放平台余额监控：轮询多账号，增减时发信号。"""
import threading

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from platforms import PROVIDERS


def parse_account(acc):
    """兼容旧格式（纯字符串 = DeepSeek Key）与新格式（平台 + Key）。"""
    if isinstance(acc, str):
        return "deepseek", acc
    return acc.get("platform", "deepseek"), acc.get("api_key", "")


class BalanceMonitor(QObject):
    balanceUpdated = pyqtSignal(float, str)  # 总额, 显示文本
    balanceUp = pyqtSignal(str)              # 增加动画文本
    balanceDown = pyqtSignal(str)            # 减少动画文本
    fetchError = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._last_total = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.poll)

    def start(self):
        self.set_interval(int(self.config.get("poll_interval_sec", 60)))
        self.poll()

    def set_interval(self, seconds):
        self._timer.start(max(10, seconds) * 1000)

    def poll(self):
        accounts = self.config.get("accounts", {}) or {}
        if not accounts:
            self.balanceUpdated.emit(0.0, "未绑定账号")
            return
        threading.Thread(target=self._worker, args=(accounts,), daemon=True).start()

    def _worker(self, accounts):
        total = 0.0
        ok = 0
        errors = []
        for name, acc in accounts.items():
            platform, key = parse_account(acc)
            provider = PROVIDERS.get(platform)
            if provider is None:
                errors.append("%s: 未知平台 %s" % (name, platform))
                continue
            try:
                amount, _currency = provider.fetch(key)
                total += amount
                ok += 1
            except Exception as e:
                errors.append("%s: %s" % (name, e))
        if not ok:
            self.fetchError.emit("；".join(errors))
            return

        text = "¥%.2f" % total
        if self._last_total is None or abs(total - self._last_total) < 0.005:
            self.balanceUpdated.emit(total, text)
        elif total > self._last_total:
            self.balanceUpdated.emit(total, text)
            self.balanceUp.emit("+¥%.2f" % (total - self._last_total))
        else:
            self.balanceUpdated.emit(total, text)
            self.balanceDown.emit("-¥%.2f" % (self._last_total - total))
        self._last_total = total
