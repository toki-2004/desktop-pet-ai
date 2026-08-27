# -*- coding: utf-8 -*-
"""桌宠主窗口：透明置顶、可拖动、滚轮缩放、余额常态显示、浮动文字动画、
左键交互（按下即播放，循环，松开恢复，如摸头）。"""
import os

from PyQt5.QtCore import Qt, QPoint, QSize, QRectF, QTimer, pyqtSignal, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PyQt5.QtGui import QMovie, QPixmap, QPainter, QColor, QBrush, QPen
from PyQt5.QtWidgets import QWidget, QLabel, QMenu, QGraphicsOpacityEffect, QApplication

MAX_PET_SIZE = 240
MIN_PET_SIZE = 30
MAX_SCALE = 4.0
MIN_SCALE = 0.2


class BalanceLabel(QLabel):
    """余额文本标签（独立置顶小窗口）：可拖出图片范围，滚轮调整字号。"""

    def __init__(self, config, parent=None):
        super().__init__(
            None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)
        self.config = config
        self.pet_window = parent
        self._drag_pos = None

    def _current_fs(self):
        return int(self.config.get("balance_font_size", 14) or 14)

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


class PetWindow(QWidget):
    toggleBalanceRequested = pyqtSignal(bool)
    bindAccountRequested = pyqtSignal()
    settingsRequested = pyqtSignal()
    appearanceRequested = pyqtSignal()
    testNotifyRequested = pyqtSignal()
    quitRequested = pyqtSignal()
    autoStartRequested = pyqtSignal(bool)
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
        self._interact_shown = False

        self.pet_label = QLabel(self)
        self.balance_label = BalanceLabel(config, self)
        self.balance_label.hide()

        self.apply_config()

    # ---------- 外观 ----------
    def apply_config(self):
        self._normal_path = self.config.get("pet_image") or self.default_image
        self._load_pet(self._normal_path)
        self._apply_balance_style()
        self.balance_label.setVisible(bool(self.config.get("show_balance", True)))
        self._place_balance()

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
        elif not self._normal_pixmap.isNull():
            self.pet_label.setPixmap(
                self._normal_pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        self.pet_label.setFixedSize(size)
        self.setFixedSize(size)
        self._place_balance()

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
        self.config.set("pet_scale", round(self._scale, 3))
        self._apply_scale()

    # ---------- 余额常态显示 ----------
    def set_balance_text(self, total, text):
        self.balance_label.setText(text)
        self.balance_label._apply_style()

    def set_balance_visible(self, visible):
        self.balance_label.setVisible(visible)
        self.config.set("show_balance", bool(visible))

    def _apply_balance_style(self):
        self.balance_label._apply_style()

    def _place_balance(self):
        off = self.config.get("balance_offset")
        if isinstance(off, list) and len(off) == 2:
            dx, dy = int(off[0]), int(off[1])
        else:
            dx = self.width() - self.balance_label.width() - 6
            dy = 6
        self.balance_label.move(self.x() + dx, self.y() + dy)

    # ---------- 左键交互（按下即播放，循环，松开恢复） ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            self._interact_shown = self._show_interact()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._interact_shown:
                self._show_normal()
        self._drag_pos = None

    def _show_interact(self):
        path = self.config.get("pet_interact_image") or ""
        if not path or not os.path.exists(path):
            return False
        if self._movie:
            self._movie.stop()
        if self._interact_movie:
            self._interact_movie.stop()
            self._interact_movie = None
        self.pet_label.clear()
        if path.lower().endswith(".gif"):
            self._interact_movie = QMovie(path)
            self.pet_label.setMovie(self._interact_movie)
            self._interact_movie.start()
            frame = self._interact_movie.frameRect()
            nat = frame.size() if frame.isValid() else self._current_size
            size = self._fit_to(self._current_size, nat)
            self._interact_movie.setScaledSize(size)
        else:
            pm = QPixmap(path)
            if pm.isNull():
                return False
            size = self._fit_to(self._current_size, pm.size())
            self.pet_label.setPixmap(pm.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.pet_label.setFixedSize(size)
        self.setFixedSize(size)
        self._place_balance()
        return True

    def _show_normal(self):
        self._load_pet(self._normal_path or self.config.get("pet_image") or self.default_image)

    # ---------- 浮动文字动画 ----------
    def show_float_text(self, text, color):
        lab = QLabel(text)
        lab.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        lab.setAttribute(Qt.WA_TranslucentBackground)
        fs = int(self.config.get("balance_font_size", 14) or 14)
        lab.setStyleSheet(
            "color:%s; font-size:%dpx; font-weight:bold; background:transparent;"
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
            self.move(event.globalPos() - self._drag_pos)

    def moveEvent(self, event):
        if self._drag_pos is not None:
            self.moved.emit(self.pos())
        if self.balance_label.isVisible():
            self._place_balance()
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
