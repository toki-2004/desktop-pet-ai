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
from PyQt5.QtGui import QMovie, QPixmap, QPainter, QColor, QBrush, QPen, QImageReader
from PyQt5.QtWidgets import QWidget, QLabel, QMenu, QGraphicsOpacityEffect, QApplication

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


class BalanceLabel(QLabel):
    """余额文本标签（独立置顶小窗口）：滚轮调整字号，可拖动并记住位置。

    文本更新统一走 set_balance()——带日志，便于定位"信号发了但标签没变"。
    """

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
        """同步"显示在最上层"开关：与桌宠/通知/浮动字保持一致。"""
        set_topmost_flag(self, on)

    def _current_fs(self):
        return int(self.config.get("balance_font_size", 14) or 14)

    def set_balance(self, text):
        if text == self.text():
            return
        petlog.log("balance label: %r -> %r" % (self.text(), text))
        self.setText(text)
        self._apply_style()

    def _apply_style(self):
        fs = self._current_fs()
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
        if delta:
            factor = 1.12 if delta > 0 else 1 / 1.12
            fs = max(8, min(30, int(round(self._current_fs() * factor))))
            self.config.set("balance_font_size", fs)
            self._apply_style()
            # 状态标签字号跟随全局字号（-2）：滚轮入口也要同步刷新（2026-08-30 修复）
            if self.pet_window is not None:
                self.pet_window.status_label._apply_style()
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


class StatusLabel(QLabel):
    """时段状态标签（独立置顶小窗口）：常态显示当前是高峰还是空闲时段。

    展示层级与余额文本保持一致——同样跟随 always_on_top 置顶开关
    （_apply_top_flag 里一起 set_top_flag），挂在桌宠左上角。
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

    def _apply_style(self):
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
        """余额下降后保持"工作中"的时长（配置热更新入口）。"""
        try:
            self._hold_sec = max(0.0, float(seconds))
        except (TypeError, ValueError):
            self._hold_sec = 180.0

    def in_working_hold(self):
        """是否处于"余额下降后的保持期"：是则 flat 信号应维持"工作中"。"""
        return self._state == "down" and time.monotonic() - self._last_down < self._hold_sec

    def set_state(self, state):
        """state: "up"（充值）/ "down"（工作中）/ "flat"（空闲中）/ "unknown"。"""
        state = state if state in ("up", "down", "flat") else "unknown"
        if state == "down":
            self._last_down = time.monotonic()
        # 保持期判定要在更新 _last_down 之后、状态切换之前做，
        # 否则刚收到的 down 事件会把旧的 flat 也当成"保持期内"拦掉
        if state == "flat" and self.in_working_hold():
            # 余额同步往往没那么快：下降后保持期内不切回"空闲中"
            return
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

    def _apply_style(self):
        fs = int(self.config.get("balance_font_size", 14) or 14)
        font = self.font()
        font.setPointSize(max(9, fs - 2))
        font.setBold(True)
        self.setFont(font)
        self.resize(max(24, self.sizeHint().width() + 16),
                    max(18, self.sizeHint().height() + 6))
        self.update()
        if self.pet_window is not None:
            self.pet_window._place_work()

    # 配色：充值=绿色系，工作中=琥珀色系，空闲中=灰色系，未知=深灰系
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

    def _apply_style(self):
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
    toggleBalanceRequested = pyqtSignal(bool)
    bindAccountRequested = pyqtSignal()
    settingsRequested = pyqtSignal()
    appearanceRequested = pyqtSignal()
    testNotifyRequested = pyqtSignal()
    quitRequested = pyqtSignal()
    autoStartRequested = pyqtSignal(bool)
    petHeadRequested = pyqtSignal()
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

        self.pet_label = QLabel(self)
        self.balance_label = BalanceLabel(config, self)
        self.balance_label.setText("余额…")  # 首次拉取前的占位，避免空白圆角框
        self.balance_label.hide()
        self.status_label = StatusLabel(config, self)
        self.work_label = WorkingStatusLabel(config, self)
        self.work_label.set_hold_sec(self.config.get("work_state_hold_sec", 180))
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
        self._apply_balance_style()
        self.balance_label.setVisible(bool(self.config.get("show_balance", True)))
        self._place_balance()
        self._place_status()
        self._apply_top_flag()
        # 时段状态常态显示：文案可被 config 自定义，这里同步刷新并随窗口显示
        self.status_label.set_state(is_peak())
        self.status_label._apply_style()  # 字号跟随 balance_font_size（-2），设置改动后强制刷新
        self.work_label.set_hold_sec(self.config.get("work_state_hold_sec", 180))
        self._place_status()
        self.status_label.show()
        self.work_label.setVisible(bool(self.config.get("work_label_enabled", True)))
        self.work_label._apply_style()
        self.affection_label.setVisible(bool(self.config.get("affection_label_enabled", True)))
        self.affection_label._apply_style()

    def _apply_top_flag(self):
        """同步置顶开关：桌宠、余额文本、时段状态、已有浮动字一起切换。"""
        on = bool(self.config.get("always_on_top", True))
        set_topmost_flag(self, on)
        self.balance_label.set_top_flag(on)
        self.status_label.set_top_flag(on)
        self.work_label.set_top_flag(on)
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

    # ---------- 余额常态显示 ----------
    def set_balance_text(self, total, text):
        # 余额更新唯一入口（信号槽）：日志用于区分"信号没到"与"到了没画"
        petlog.log("set_balance_text %r (thread %s)" % (text, threading.get_ident()))
        self.balance_label.set_balance(text)

    def set_balance_visible(self, visible):
        self.balance_label.setVisible(visible)
        self.config.set("show_balance", bool(visible))

    def _apply_balance_style(self):
        self.balance_label._apply_style()

    def _place_balance(self):
        # BalanceLabel 构造期间会回调到这里，此时 balance_label 尚未挂到 self 上
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

    def _place_status(self):
        # 时段状态放在桌宠正下部（用户指定）：文本框上缘紧贴桌宠窗口下缘，水平居中。
        # StatusLabel 构造期间会回调到这里，此时 status_label 尚未挂到 self 上。
        # 互动 GIF 播放中冻结在常态位置不动（用户指定）。
        label = getattr(self, "status_label", None)
        if label is None:
            return
        rect = self._pre_interact_rect if self._status_frozen and self._pre_interact_rect else self
        x = rect.x() + max(0, (rect.width() - label.width()) // 2)
        label.move(x, rect.y() + rect.height())
        self._place_work()

    def _place_work(self):
        """工作状态标签：以时段标签当前位置为基准，紧贴其右侧同一行。

        独立定位（不依赖 _place_status 重算），保证状态标签在
        冻结/播放/恢复等路径归位时，工作标签始终跟随。
        """
        status = getattr(self, "status_label", None)
        work = getattr(self, "work_label", None)
        if status is None or work is None or not work.isVisible():
            return
        gap = 6
        work.move(status.x() + status.width() + gap, status.y())
        self._place_affection()

    def _place_affection(self):
        """好感标签：紧贴时段/工作状态组的左侧同一行。"""
        status = getattr(self, "status_label", None)
        aff = getattr(self, "affection_label", None)
        if status is None or aff is None or not aff.isVisible():
            return
        gap = 6
        aff.move(status.x() - aff.width() - gap, status.y())

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
        self._place_balance()
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
        lab.setStyleSheet(
            "color:%s; font-size:%dpt; font-weight:bold; background:transparent;"
            % (color, fs)
        )
        lab.adjustSize()
        geo = self.geometry()
        lab.move(geo.center().x() - lab.width() // 2, geo.top() - lab.height() - 6)
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
        if self.balance_label.isVisible():
            self._place_balance()
        self._place_status()
        super().moveEvent(event)

    # ---------- 右键菜单 ----------
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        act_balance = menu.addAction("余额常态显示")
        act_balance.setCheckable(True)
        act_balance.setChecked(bool(self.config.get("show_balance", True)))
        act_balance.triggered.connect(self.set_balance_visible)
        act_autostart = menu.addAction("开机自启")
        act_autostart.setCheckable(True)
        act_autostart.setChecked(bool(self.config.get("auto_start", False)))
        act_autostart.triggered.connect(self.autoStartRequested.emit)
        menu.addAction("绑定/管理账号…", self.bindAccountRequested.emit)
        menu.addAction("通知设置…", self.settingsRequested.emit)
        menu.addAction("更换外观 (PNG/GIF)…", self.appearanceRequested.emit)
        menu.addAction("发送测试通知", self.testNotifyRequested.emit)
        menu.addSeparator()
        menu.addAction("退出", self.quitRequested.emit)
        menu.exec_(event.globalPos())
