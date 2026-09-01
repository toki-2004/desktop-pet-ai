# -*- coding: utf-8 -*-
"""桌宠主窗口：透明置顶、可拖动、滚轮缩放、余额常态显示、浮动文字动画、
左键交互（单击播放一遍互动 GIF 并换一条摸头语录，拖动不触发；连点从头重放）、
时段常态显示（桌宠正下部）。"""
import os
import threading
import sys
import ctypes
import time

from PyQt5.QtCore import Qt, QPoint, QSize, QRectF, QTimer, pyqtSignal, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PyQt5.QtGui import QMovie, QPixmap, QPainter, QColor, QBrush, QPen, QImageReader, QFontMetrics
from PyQt5.QtWidgets import QWidget, QLabel, QMenu, QGraphicsOpacityEffect, QApplication, QLineEdit

from scheduler import is_peak
import petlog

MAX_PET_SIZE = 240
MIN_PET_SIZE = 30
MAX_SCALE = 4.0
MIN_SCALE = 0.2


def set_topmost_flag(widget, on):
    """切换置顶标志（桌宠/余额/浮动字/气泡通用）。

    setWindowFlag 会先隐藏可见的顶层窗口并重建原生窗口，紧接其后的
    isVisible() 恒为 False，导致窗口不再显示；这里先记录可见性，
    必要时重新 show()，并在 Windows 上原生强制 WS_EX_TOPMOST，
    避免原生窗口重建竞态导致置顶丢失。
    """
    was_visible = widget.isVisible()
    widget.setWindowFlag(Qt.WindowStaysOnTopHint, bool(on))
    if was_visible:
        widget.show()
    if sys.platform == "win32":
        try:
            hwnd = int(widget.winId())
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOACTIVATE = 0x0010
            ctypes.windll.user32.SetWindowPos(
                hwnd,
                -1 if on else -2,  # HWND_TOPMOST / HWND_NOTOPMOST
                0, 0, 0, 0,
                SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE,
            )
        except Exception:
            pass


class ChatInput(QLineEdit):
    """聊天输入框（独立置顶小窗口）：回车发送给 AI，可拖动并记住位置。"""

    def __init__(self, config, parent=None):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.config = config
        self.pet_window = parent
        self._drag_pos = None
        self.setPlaceholderText("和桌宠说点什么…")
        # 原生 QLineEdit 行为：空文本获得焦点时占位符自动消失、出现跳动光标
        # （像浏览器搜索栏）；自定义 paintEvent 只画圆角背景，文本/光标/占位符
        # 交给原生绘制，避免占位符与光标被手绘盖掉。
        self.setFrame(False)
        self.setStyleSheet("QLineEdit { background: transparent; border: none; }")
        self.setTextMargins(8, 3, 8, 3)
        self.returnPressed.connect(self._send)
        self._apply_style()

    def _send(self):
        text = self.text().strip()
        if text:
            self.clear()
            if self.pet_window is not None:
                self.pet_window.chatInputRequested.emit(text)

    def set_top_flag(self, on):
        set_topmost_flag(self, on)

    def _current_fs(self):
        return int(self.config.get("balance_font_size", 14) or 14)

    def _apply_style(self, fs=None):
        fs = fs if fs is not None else self._current_fs()
        font = self.font()
        font.setPointSize(fs)
        font.setBold(True)
        self.setFont(font)
        self.adjustSize()  # 宽度由 PetWindow._place_input 按标签组总宽统一控制
        if self.pet_window is not None:
            self.pet_window._place_input()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor("#3D8BFF"), 1))
        p.setBrush(QBrush(QColor(255, 255, 255, 235)))
        p.drawRoundedRect(rect, 8, 8)
        p.end()
        super().paintEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            screen = QApplication.screenAt(event.globalPos())
            avail = screen.availableGeometry() if screen else QApplication.primaryScreen().availableGeometry()
            x = event.globalPos().x() - self._drag_pos.x()
            y = event.globalPos().y() - self._drag_pos.y()
            x = max(avail.left(), min(x, avail.right() - self.width()))
            y = max(avail.top(), min(y, avail.bottom() - self.height()))
            self.move(x, y)
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_pos is not None:
            if self.pet_window is not None:
                self.config.set("chat_input_offset", [
                    self.x() - self.pet_window.x(),
                    self.y() - self.pet_window.y(),
                ])
            self._drag_pos = None
        event.accept()


class BalanceLabel(QLabel):
    """余额文本标签（独立置顶小窗口）：滚轮调整字号，可拖动并记住位置。"""

    def __init__(self, config, parent=None):
        super().__init__(
            None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)
        self.config = config
        self.pet_window = parent
        self._drag_pos = None
        self.setText("余额…")
        self._apply_style()

    def set_top_flag(self, on):
        set_topmost_flag(self, on)

    def _current_fs(self):
        return int(self.config.get("balance_font_size", 14) or 14)

    def set_balance(self, text):
        if text == self.text():
            return
        self.setText(text)
        self._apply_style()

    def _apply_style(self, fs=None):
        fs = fs if fs is not None else self._current_fs()
        font = self.font()
        font.setPointSize(fs)
        font.setBold(True)
        self.setFont(font)
        self.resize(max(24, self.sizeHint().width() + 16),
                    max(18, self.sizeHint().height() + 6))
        if self.pet_window is not None:
            self.pet_window._place_balance()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor("#CCCCCC"), 1))
        p.setBrush(QBrush(QColor("#FFFFFF")))
        p.drawRoundedRect(rect, 8, 8)
        p.setPen(QColor(0, 0, 0))
        p.drawText(rect.adjusted(8, 3, -8, -3), Qt.AlignCenter, self.text())

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta and self.pet_window is not None:
            self.pet_window._adjust_font(delta)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            screen = QApplication.screenAt(event.globalPos())
            avail = screen.availableGeometry() if screen else QApplication.primaryScreen().availableGeometry()
            x = event.globalPos().x() - self._drag_pos.x()
            y = event.globalPos().y() - self._drag_pos.y()
            x = max(avail.left(), min(x, avail.right() - self.width()))
            y = max(avail.top(), min(y, avail.bottom() - self.height()))
            self.move(x, y)
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag_pos is not None:
            if self.pet_window is not None:
                self.config.set("balance_offset", [
                    self.x() - self.pet_window.x(),
                    self.y() - self.pet_window.y(),
                ])
            self._drag_pos = None
        event.accept()


class WorkingStatusLabel(QLabel):
    """工作状态标签（独立置顶小窗口）：以余额升降作为判定标准。

    余额降低 = 正在工作（烧余额）-> "工作中"（琥珀色系）；
    余额不变 = 没在工作 -> "空闲中"（灰色系）；
    余额升高 = 充值 -> "充值了"（绿色系）；
    未取得数据 -> "余额未知"（深灰系）。文本与配色均可由 config 定制。
    """

    def __init__(self, config, parent=None):
        super().__init__(
            None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)
        self.config = config
        self.pet_window = parent
        self._state = "unknown"
        self._last_down = 0.0      # monotonic：最近一次余额下降时刻（保持期基准）
        self._hold_sec = 180.0     # 余额下降后保持"工作中"的秒数（默认 3 分钟）
        self.setText(self.config.get("work_unknown_text", "余额未知") or "余额未知")
        self._apply_style()

    def set_top_flag(self, on):
        set_topmost_flag(self, on)

    def set_hold_sec(self, seconds):
        try:
            self._hold_sec = max(0.0, float(seconds))
        except (TypeError, ValueError):
            self._hold_sec = 180.0

    def in_working_hold(self):
        return self._state == "down" and time.monotonic() - self._last_down < self._hold_sec

    def current_state(self):
        """当前工作状态键："up"/"down"/"flat"/"unknown"（供 AI prompt 使用）。"""
        return self._state

    def set_state(self, state):
        state = state if state in ("up", "down", "flat") else "unknown"
        if state == "down":
            self._last_down = time.monotonic()
        if state == "flat" and self.in_working_hold():
            return  # 余额同步往往没那么快：下降后保持期内不切回"空闲中"
        if state == self._state and self.text():
            return
        self._state = state
        if state == "up":
            self.setText(self.config.get("work_up_text", "充值了") or "充值了")
        elif state == "down":
            self.setText(self.config.get("work_down_text", "工作中") or "工作中")
        elif state == "flat":
            self.setText(self.config.get("work_flat_text", "空闲中") or "空闲中")
        else:
            self.setText(self.config.get("work_unknown_text", "余额未知") or "余额未知")
        self._apply_style()

    def _apply_style(self, fs=None):
        fs = fs if fs is not None else int(self.config.get("balance_font_size", 14) or 14)
        font = self.font()
        font.setPointSize(max(9, fs - 2))
        font.setBold(True)
        self.setFont(font)
        self.resize(max(24, self.sizeHint().width() + 16),
                    max(18, self.sizeHint().height() + 6))
        self.update()
        if self.pet_window is not None:
            self.pet_window._place_work()

    PALETTE = {
        "up": {"border": QColor("#27AE60"), "text": QColor("#1E7B4F"), "fill": QColor(39, 174, 96, 34)},
        "down": {"border": QColor("#E67E22"), "text": QColor("#C65E0E"), "fill": QColor(230, 126, 34, 34)},
        "flat": {"border": QColor("#95A5A6"), "text": QColor("#6B7B7C"), "fill": QColor(149, 165, 166, 32)},
        "unknown": {"border": QColor("#5D6D7E"), "text": QColor("#34495E"), "fill": QColor(93, 109, 126, 32)},
    }

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        c = self.PALETTE[self._state]
        p.setPen(QPen(c["border"], 1))
        p.setBrush(c["fill"])
        p.drawRoundedRect(rect, 8, 8)
        p.setPen(c["text"])
        p.drawText(rect.adjusted(8, 3, -8, -3), Qt.AlignCenter, self.text())


class StatusLabel(QLabel):
    """时段状态标签（独立置顶小窗口）：常态显示当前是高峰还是空闲时段。

    展示层级与余额文本保持一致——同样跟随 always_on_top 置顶开关
    （_apply_top_flag 里一起 set_top_flag）。
    """

    def __init__(self, config, parent=None):
        super().__init__(
            None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)
        self.config = config
        self.pet_window = parent
        self._peak = None
        self.set_state(is_peak())

    def set_top_flag(self, on):
        set_topmost_flag(self, on)

    def set_state(self, peak):
        if peak == self._peak and self.text():
            return
        self._peak = bool(peak)
        peak_t = self.config.get("peak_status_text", "高峰时段") or "高峰时段"
        idle_t = self.config.get("idle_status_text", "空闲时段") or "空闲时段"
        self.setText(peak_t if peak else idle_t)
        self._apply_style()

    def _apply_style(self, fs=None):
        if fs is None:
            fs = int(self.config.get("balance_font_size", 14) or 14)
        font = self.font()
        font.setPointSize(max(9, fs - 2))
        font.setBold(True)
        self.setFont(font)
        self.resize(max(24, self.sizeHint().width() + 16),
                    max(18, self.sizeHint().height() + 6))
        self.update()
        if self.pet_window is not None:
            self.pet_window._place_status()

    # 配色（用户指定）：高峰=红色系，空闲=绿色系；纯色边框 + 半透明底纹 + 纯色文字
    PALETTE = {
        True: {"border": QColor("#E03E3E"), "text": QColor("#C62828"), "fill": QColor(224, 62, 62, 36)},
        False: {"border": QColor("#27AE60"), "text": QColor("#1E7B4F"), "fill": QColor(39, 174, 96, 34)},
    }

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        c = self.PALETTE[bool(self._peak)]
        p.setPen(QPen(c["border"], 1))
        p.setBrush(c["fill"])
        p.drawRoundedRect(rect, 8, 8)
        p.setPen(c["text"])
        p.drawText(rect.adjusted(8, 3, -8, -3), Qt.AlignCenter, self.text())


class AffectionLabel(QLabel):
    """好感标签（独立置顶小窗口）：常态显示当前好感值与档位配色。

    与时段/工作状态标签同一层级，跟随 always_on_top 与桌宠显隐。
    """

    def __init__(self, config, parent=None):
        super().__init__(
            None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)
        self.config = config
        self.pet_window = parent
        self._value = 0.0
        self.setText("好感 …")
        self._apply_style()

    def set_top_flag(self, on):
        set_topmost_flag(self, on)

    def set_affection(self, value):
        try:
            self._value = float(value)
        except (TypeError, ValueError):
            self._value = 0.0
        self._apply_style()

    def _apply_style(self, fs=None):
        if fs is None:
            fs = int(self.config.get("balance_font_size", 14) or 14)
        font = self.font()
        font.setPointSize(max(9, fs - 2))
        font.setBold(True)
        self.setFont(font)
        self.setText("好感 %d" % int(round(self._value)))
        self.resize(max(24, self.sizeHint().width() + 16),
                    max(18, self.sizeHint().height() + 6))
        self.update()
        if self.pet_window is not None:
            self.pet_window._place_affection()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta and self.pet_window is not None:
            self.pet_window._adjust_font(delta)
        event.accept()

    # 好感档位配色：高=粉色系，中=蓝色系，低=灰蓝色系
    PALETTE = {
        "high": {"border": QColor("#E91E8C"), "text": QColor("#C2185B"), "fill": QColor(233, 30, 140, 34)},
        "mid": {"border": QColor("#3D8BFF"), "text": QColor("#1E5FC4"), "fill": QColor(61, 139, 255, 34)},
        "low": {"border": QColor("#78909C"), "text": QColor("#546E7A"), "fill": QColor(120, 144, 156, 34)},
    }

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        max_v = int(self.config.get("affection_max", 100) or 100)
        try:
            max_v = float(max_v)
        except (TypeError, ValueError):
            max_v = 100.0
        low = float(self.config.get("affection_low_threshold_pct", 40) or 40) / 100.0 * max_v
        high = float(self.config.get("affection_high_threshold_pct", 80) or 80) / 100.0 * max_v
        tier = "high" if self._value >= high else ("low" if self._value < low else "mid")
        c = self.PALETTE[tier]
        p.setPen(QPen(c["border"], 1))
        p.setBrush(c["fill"])
        p.drawRoundedRect(rect, 8, 8)
        p.setPen(c["text"])
        p.drawText(rect.adjusted(8, 3, -8, -3), Qt.AlignCenter, self.text())


class PetWindow(QWidget):
    settingsRequested = pyqtSignal()
    appearanceRequested = pyqtSignal()
    testNotifyRequested = pyqtSignal()
    quitRequested = pyqtSignal()
    autoStartRequested = pyqtSignal(bool)
    petHeadRequested = pyqtSignal()
    chatInputRequested = pyqtSignal(str)
    historyRequested = pyqtSignal()
    balanceVisibleRequested = pyqtSignal(bool)
    moved = pyqtSignal(QPoint)

    def __init__(self, config, default_image=""):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)
        self.setWindowTitle("桌宠")
        self.config = config
        self.default_image = default_image
        self._drag_pos = None
        self._floats = set()
        self._movie = None
        self._normal_pixmap = QPixmap()
        self._normal_path = ""
        self._base_size = QSize(MAX_PET_SIZE, MAX_PET_SIZE)
        self._current_size = QSize(MAX_PET_SIZE, MAX_PET_SIZE)
        self._scale = float(self.config.get("pet_scale", 1.0) or 1.0)
        self._interact_movie = None
        self._interact_total = 0
        self._normal_display_size = None  # 常态桌宠的实际显示尺寸（互动动画的上限）
        self._status_frozen = False       # 互动播放中：时段标签冻结在常态位置不动
        self._pre_interact_rect = None    # 点击前的窗口几何（冻结定位的基准）
        self._press_global = None   # 按下时的全局位置：用于区分拖动与单击
        self._press_moved = False
        self._scale_save_timer = QTimer(self)
        self._scale_save_timer.setSingleShot(True)
        self._scale_save_timer.setInterval(800)
        self._scale_save_timer.timeout.connect(
            lambda: self.config.set("pet_scale", round(self._scale, 3)))
        self._font_save_timer = QTimer(self)
        self._font_save_timer.setSingleShot(True)
        self._font_save_timer.setInterval(800)
        self._font_save_timer.timeout.connect(self._save_font_size)
        self._font_size_pending = None

        self.pet_label = QLabel(self)
        self.chat_input = ChatInput(config, self)
        self.balance_label = BalanceLabel(config, self)
        self.balance_label.setText("余额…")  # 首次拉取前的占位
        self.balance_label.hide()
        self.work_label = WorkingStatusLabel(config, self)
        self.work_label.set_hold_sec(self.config.get("work_state_hold_sec", 180))
        self.status_label = StatusLabel(config, self)
        self.affection_label = AffectionLabel(config, self)

        self.apply_config()

    # ---------- 外观 ----------
    def apply_config(self):
        path = self.config.get("pet_image")
        # 配置路径失效（如打包后临时解压目录变化）时回退内置默认图
        if not path or not os.path.exists(path):
            path = self.default_image
        self._normal_path = path
        self._load_pet(self._normal_path)
        self._apply_top_flag()
        # 时段状态常态显示：文案可被 config 自定义，这里同步刷新并随窗口显示
        self.status_label.set_state(is_peak())
        self.status_label.show()
        self.balance_label.setVisible(bool(self.config.get("show_balance", True)))
        self.work_label.set_hold_sec(self.config.get("work_state_hold_sec", 180))
        self.work_label.setVisible(bool(self.config.get("work_label_enabled", True)))
        self.affection_label.setVisible(bool(self.config.get("affection_label_enabled", True)))
        self.chat_input.setVisible(True)
        # 统一刷新出口：字号跟随 balance_font_size（-2），任何入口
        # （滚轮/设置保存/隐藏-显示）都走这里，三个标签尺寸同步
        self._place_balance()
        self._place_status()

    def _apply_top_flag(self):
        """同步置顶开关：桌宠、余额文本、时段状态、已有浮动字一起切换。"""
        on = bool(self.config.get("always_on_top", True))
        set_topmost_flag(self, on)
        self.chat_input.set_top_flag(on)
        self.balance_label.set_top_flag(on)
        self.work_label.set_top_flag(on)
        self.status_label.set_top_flag(on)
        self.affection_label.set_top_flag(on)
        for lab in list(self._floats):
            set_topmost_flag(lab, on)

    def _load_pet(self, path):
        if self._movie:
            self._movie.stop()
            self._movie = None
        if self._interact_movie:
            self._interact_movie.stop()
            self._interact_movie = None
        self._normal_path = path
        self.pet_label.clear()
        self._normal_pixmap = QPixmap()
        if path and os.path.exists(path):
            if path.lower().endswith(".gif"):
                self._movie = QMovie(path)
                self.pet_label.setMovie(self._movie)
                self._movie.start()
                frame = self._movie.frameRect()
                natural = frame.size() if frame.isValid() else QSize(MAX_PET_SIZE, MAX_PET_SIZE)
            else:
                self._normal_pixmap = QPixmap(path)
                natural = self._normal_pixmap.size() if not self._normal_pixmap.isNull() else QSize(MAX_PET_SIZE, MAX_PET_SIZE)
        else:
            self._normal_pixmap = self._placeholder()
            natural = self._normal_pixmap.size()
        self._base_size = self._fit(natural)
        self._apply_scale()

    @staticmethod
    def _placeholder():
        pm = QPixmap(120, 120)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(QColor(90, 160, 255)))
        p.drawEllipse(5, 5, 110, 110)
        p.end()
        return pm

    def _apply_scale(self):
        size = QSize(
            max(MIN_PET_SIZE, int(self._base_size.width() * self._scale)),
            max(MIN_PET_SIZE, int(self._base_size.height() * self._scale)),
        )
        self._current_size = size
        if self._movie:
            self._movie.setScaledSize(size)
            self._normal_display_size = QSize(size)
        elif not self._normal_pixmap.isNull():
            fitted = self._normal_pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.pet_label.setPixmap(fitted)
            self._normal_display_size = fitted.size()
        self.pet_label.setFixedSize(size)
        self.setFixedSize(size)
        self._place_balance()
        self._place_status()

    @staticmethod
    def _fit(src_size):
        if src_size.width() <= MAX_PET_SIZE and src_size.height() <= MAX_PET_SIZE:
            return src_size
        ratio = min(MAX_PET_SIZE / src_size.width(), MAX_PET_SIZE / src_size.height())
        return QSize(max(1, int(src_size.width() * ratio)), max(1, int(src_size.height() * ratio)))

    @staticmethod
    def _fit_to(box, src):
        if src.width() <= 0 or src.height() <= 0:
            return box
        ratio = min(box.width() / src.width(), box.height() / src.height())
        return QSize(max(1, int(src.width() * ratio)), max(1, int(src.height() * ratio)))

    # ---------- 滚轮缩放 ----------
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if not delta:
            return
        factor = 1.12 if delta > 0 else 1 / 1.12
        self._scale = max(MIN_SCALE, min(MAX_SCALE, self._scale * factor))
        # 停止滚动 800ms 后才落盘：每格滚轮写一次盘的旧做法会高频重写 config.json
        self._scale_save_timer.start()
        self._apply_scale()

    def _place_status(self):
        """时段/好感/工作状态三个标签并排一行（等高圆角矩形），整组居中在桌宠正下方。

        StatusLabel 构造期间会回调到这里，此时其余标签可能尚未挂到 self 上；
        互动 GIF 播放中整组冻结在常态位置不动。
        """
        labels = self._status_group_labels()
        status = getattr(self, "status_label", None)
        if status is None or not labels:
            return
        aff = getattr(self, "affection_label", None)
        work = getattr(self, "work_label", None)
        aff_on = aff in labels
        work_on = work in labels
        rect = self._pre_interact_rect if self._status_frozen and self._pre_interact_rect else self
        y = rect.y() + rect.height()
        # 相同高度且随字号自适应：用 fontMetrics 直接算内容高度（不受旧尺寸
        # 约束影响）。不能用 sizeHint().height()——一旦 setFixedHeight 锁过高度，
        # sizeHint 会返回"当前高度-内边距"导致高度只增不减（滚轮放大缩小后
        # 标签无限变高）；也不能 setFixedHeight（Fixed 策略让 resize 无法缩小）。
        h = max(max(18, l.fontMetrics().height() + 6) for l in labels)
        for l in labels:
            l.setMinimumHeight(h)
            l.resize(max(24, l.sizeHint().width() + 16), h)
        gap = 6
        total = sum(l.width() for l in labels) + gap * max(0, len(labels) - 1)
        # 中轴线对齐：即使标签组比桌宠图片还宽，也保持组中心 == 图片中心
        x = rect.x() + (rect.width() - total) // 2
        if aff_on:
            aff.move(x, y)
            x += aff.width() + gap
        status.move(x, y)
        x += status.width() + gap
        if work_on:
            work.move(x, y)
        self._place_input()

    def _status_group_labels(self):
        """当前参与并排的标签列表（与配置开关一致，供排版与输入框宽度共用）。"""
        labels = []
        aff = getattr(self, "affection_label", None)
        status = getattr(self, "status_label", None)
        work = getattr(self, "work_label", None)
        if aff is not None and bool(self.config.get("affection_label_enabled", True)):
            labels.append(aff)
        if status is not None:
            labels.append(status)
        if work is not None and bool(self.config.get("work_label_enabled", True)):
            labels.append(work)
        return labels

    def _label_group_width(self):
        """三标签组的总宽（含间距），输入框宽度跟随它以便与标签组对齐。"""
        labels = self._status_group_labels()
        if not labels:
            return 0
        return sum(l.width() for l in labels) + 6 * max(0, len(labels) - 1)

    def _place_balance(self):
        """余额文本：默认在桌宠左上角（可用 offset 记忆拖动位置）。"""
        label = getattr(self, "balance_label", None)
        if label is None:
            return
        off = self.config.get("balance_offset")
        if isinstance(off, list) and len(off) == 2:
            dx, dy = int(off[0]), int(off[1])
        else:
            dx = label.width() and (self.width() - label.width() - 6) or 6
            dy = 6
        label.move(self.x() + dx, self.y() + dy)

    def set_balance_text(self, total, text):
        self.balance_label.set_balance(text)

    def set_balance_visible(self, visible):
        self.balance_label.setVisible(visible)
        self.config.set("show_balance", bool(visible))

    def _place_work(self):
        """工作状态标签定位入口：整组并排由 _place_status 统一处理。"""
        self._place_status()

    def _place_affection(self):
        """好感标签定位入口：整组并排由 _place_status 统一处理。"""
        self._place_status()

    def _place_input(self):
        """聊天输入框：宽度始终等于标签组总宽（可完美对齐），
        默认在标签组正下方居中，用户可拖动后按偏移记忆。"""
        box = getattr(self, "chat_input", None)
        if box is None:
            return
        group_w = self._label_group_width()
        if group_w > 0:
            box.setFixedWidth(group_w)
        off = self.config.get("chat_input_offset")
        if isinstance(off, list) and len(off) == 2:
            box.move(self.x() + int(off[0]), self.y() + int(off[1]))
        else:
            status = getattr(self, "status_label", None)
            if status is None:
                return
            box.move(self.x() + max(0, (self.width() - box.width()) // 2),
                     status.y() + status.height() + 6)

    # ---------- 左键交互（单击从头播放一遍互动 GIF，连点重放；长按出摸头语录） ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            self._press_global = event.globalPos()
            self._press_moved = False

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._drag_pos is not None:
                # 单击（按下后未拖动）= 播放一遍互动 GIF + 换一条摸头语录；拖动不触发
                if not self._press_moved and self.config.get("pet_head_enabled", True):
                    self._play_interact_once()
                    self.petHeadRequested.emit()
                # 位置在拖动结束时落盘一次：moveEvent 每像素写盘的旧做法会高频重写 config.json
                self.config.set("pet_pos", [self.x(), self.y()])
        self._press_moved = False
        self._press_global = None
        self._drag_pos = None

    def save_state(self):
        """退出前落盘位置与缩放，保证下次启动恢复到上次的位置和大小。"""
        self.config.set("pet_pos", [self.x(), self.y()])
        self.config.set("pet_scale", round(self._scale, 3))

    def recall_to_center(self):
        """一键召回：不改变大小，把桌宠放到当前屏幕的正中间。"""
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        geo = screen.availableGeometry()
        self.move(geo.x() + max(0, (geo.width() - self.width()) // 2),
                  geo.y() + max(0, (geo.height() - self.height()) // 2))
        self.config.set("pet_pos", [self.x(), self.y()])

    def _play_interact_once(self):
        """左键单击：互动 GIF 从头播放一遍，播完自动恢复常态图。

        每次都重建 QMovie 并从头 start——连点时上一次播放随即被终止，
        不会出现两个动画叠加或越播越卡。静态互动图则短暂显示后恢复。
        """
        path = self.config.get("pet_interact_image") or ""
        if not path or not os.path.exists(path):
            return False
        if not self._status_frozen:
            # 记录点击前的窗口几何：播放期间时段标签固定在这个位置不动
            self._pre_interact_rect = self.geometry()
            self._status_frozen = True
        if self._movie:
            self._movie.stop()
        if self._interact_movie is not None:
            self._interact_movie.stop()
            self._interact_movie.deleteLater()
            self._interact_movie = None
        self.pet_label.clear()
        size = None
        # 以常态桌宠的实际显示尺寸为上限：互动动画永远不大于常态桌宠
        box = self._normal_display_size or self._current_size
        if path.lower().endswith(".gif"):
            # 尺寸用 QImageReader 预读（不启播）；缩放必须在 start 之前设置，
            # 否则首帧会按原生尺寸渲染一瞬（互动 GIF 原生较大时表现为骤然放大）
            reader = QImageReader(path)
            total = reader.imageCount()
            self._interact_total = total if total and total > 0 else 0
            nat = reader.size()
            if nat is None or nat.isEmpty():
                nat = self._current_size
            size = self._fit_to(box, nat)
            movie = QMovie(path)
            self._interact_movie = movie
            movie.frameChanged.connect(self._on_interact_frame)
            movie.setScaledSize(size)
            self.pet_label.setMovie(movie)
            movie.start()
            if self._interact_total <= 0:
                self._interact_total = movie.frameCount()
        else:
            pm = QPixmap(path)
            if pm.isNull():
                return False
            size = self._fit_to(box, pm.size())
            self.pet_label.setPixmap(pm.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            # 静态图没有帧回调：定时恢复常态
            QTimer.singleShot(600, self._show_normal)
        self.pet_label.setFixedSize(size)
        self.setFixedSize(size)
        self._place_status()
        return True

    def _on_interact_frame(self, frame_no):
        """互动 GIF 播到最后一帧：停止并恢复常态（只播一遍的关键）。"""
        movie = self._interact_movie
        if movie is None:
            return
        total = self._interact_total or movie.frameCount()
        if total > 0 and frame_no >= total - 1:
            self._interact_movie = None
            movie.stop()
            movie.deleteLater()
            self._show_normal()

    def _show_normal(self):
        self._load_pet(self._normal_path or self.config.get("pet_image") or self.default_image)
        # 恢复常态后解冻（恢复后的几何与冻结值一致，定位结果不变）
        self._status_frozen = False
        self._pre_interact_rect = None

    # ---------- 浮动文字动画 ----------
    def show_float_text(self, text, color):
        lab = QLabel(text)
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self.config.get("always_on_top", True):
            flags |= Qt.WindowStaysOnTopHint
        lab.setWindowFlags(flags)
        lab.setAttribute(Qt.WA_TranslucentBackground)
        fs = int(self.config.get("balance_font_size", 14) or 14)
        font = lab.font()
        font.setPointSize(fs)
        font.setBold(True)
        lab.setFont(font)
        lab.setStyleSheet("color:%s; background:transparent;" % color)
        # 不用 sizeHint：真实字体下可能偏小导致截断；用字体度量显式计算，
        # 并强制居中（QLabel 默认左对齐，窗口加宽后文字会偏左）。
        lab.setAlignment(Qt.AlignCenter)
        fm = QFontMetrics(lab.font())
        lab.resize(fm.horizontalAdvance(text) + 16, fm.height() + 8)
        geo = self.geometry()
        screen = QApplication.screenAt(geo.center())
        avail = screen.availableGeometry() if screen else QApplication.primaryScreen().availableGeometry()
        x = max(avail.left(), min(geo.center().x() - lab.width() // 2,
                                  avail.right() - lab.width()))
        y = geo.top() - lab.height() - 6
        if y < avail.top():
            y = geo.bottom() + 6  # 桌宠贴近屏幕顶时改在下方浮动，避免被裁
        lab.move(x, y)
        lab.show()
        self._floats.add(lab)

        eff = QGraphicsOpacityEffect(lab)
        lab.setGraphicsEffect(eff)
        group = QParallelAnimationGroup(lab)
        pos_anim = QPropertyAnimation(lab, b"pos")
        pos_anim.setDuration(1800)
        pos_anim.setStartValue(lab.pos())
        pos_anim.setEndValue(lab.pos() + QPoint(0, -70))
        pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        op_anim = QPropertyAnimation(eff, b"opacity")
        op_anim.setDuration(1800)
        op_anim.setStartValue(1.0)
        op_anim.setEndValue(0.0)
        group.addAnimation(pos_anim)
        group.addAnimation(op_anim)

        def _done():
            self._floats.discard(lab)
            lab.deleteLater()

        group.finished.connect(_done)
        group.start()

    # ---------- 拖动 ----------
    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            # 移动超过阈值判定为拖动：本次按下不再触发单击动画/语录
            if self._press_global is not None and \
               (event.globalPos() - self._press_global).manhattanLength() > 6:
                self._press_moved = True
            screen = QApplication.screenAt(event.globalPos())
            avail = screen.availableGeometry() if screen else QApplication.primaryScreen().availableGeometry()
            pos = event.globalPos() - self._drag_pos
            # 钳制在屏幕可用区内，避免拖出屏幕后无法右键退出
            x = max(avail.left(), min(pos.x(), avail.right() - self.width()))
            y = max(avail.top(), min(pos.y(), avail.bottom() - self.height()))
            self.move(x, y)

    def moveEvent(self, event):
        if self._drag_pos is not None:
            self.moved.emit(self.pos())
        if self.chat_input.isVisible():
            self._place_input()
        if self.balance_label.isVisible():
            self._place_balance()
        self._place_status()
        self._place_affection()
        super().moveEvent(event)

    def _adjust_font(self, delta):
        """滚轮调全局字号：好感/时段/输入框/通知文本同步（通知取值于弹窗时刻）。"""
        base = self._font_size_pending
        if base is None:
            base = int(self.config.get("balance_font_size", 14) or 14)
        self._font_size_pending = max(8, min(30, base + (1 if delta > 0 else -1)))
        self._refresh_fonts()
        self._font_save_timer.start()

    def _save_font_size(self):
        if self._font_size_pending is not None:
            self.config.set("balance_font_size", self._font_size_pending)
            self._font_size_pending = None

    def _refresh_fonts(self):
        fs = self._font_size_pending
        if fs is None:
            fs = int(self.config.get("balance_font_size", 14) or 14)
        for lab in (self.balance_label, self.work_label, self.status_label,
                    self.affection_label, self.chat_input):
            lab._apply_style(fs)

    # ---------- 右键菜单 ----------
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_balance = menu.addAction("余额常态显示")
        act_balance.setCheckable(True)
        act_balance.setChecked(bool(self.config.get("show_balance", True)))
        act_balance.triggered.connect(self.balanceVisibleRequested.emit)
        act_hist = menu.addAction("聊天记录…")
        act_hist.triggered.connect(self.historyRequested.emit)
        act_autostart = menu.addAction("开机自启")
        act_autostart.setCheckable(True)
        act_autostart.setChecked(bool(self.config.get("auto_start", False)))
        act_autostart.triggered.connect(self.autoStartRequested.emit)
        menu.addAction("通知设置…", self.settingsRequested.emit)
        menu.addAction("更换外观 (PNG/GIF)…", self.appearanceRequested.emit)
        menu.addAction("发送测试通知", self.testNotifyRequested.emit)
        menu.addSeparator()
        menu.addAction("退出", self.quitRequested.emit)
        menu.exec_(event.globalPos())
