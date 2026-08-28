# -*- coding: utf-8 -*-
"""思考云线：白底深蓝描边（可自定义），文字居中，可常驻直到确认。"""
import math

from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal, QTimer
from PyQt5.QtGui import QPainter, QColor, QPainterPath, QPen
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout

from pet_window import set_topmost_flag


class ThinkingBalloon(QWidget):
    """顶部置顶的云线气泡窗口。persistent=True 时显示"知道了"并停留到确认。"""

    confirmed = pyqtSignal()

    def __init__(self, text="", fill="#FFFFFF", outline="#1E3A8A",
                 persistent=False, always_on_top=True):
        flags = Qt.FramelessWindowHint | Qt.Tool
        if always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)
        self._always_on_top = bool(always_on_top)
        self._text = text
        self._fill = QColor(fill)
        self._outline = QColor(outline)
        self._persistent = persistent

        # 根据文本长度自适应气泡尺寸
        char_w = 17
        lines = max(1, math.ceil(len(text) / 13))
        w = min(460, max(210, 70 + char_w * min(len(text), 26)))
        h = min(230, max(92, 54 + 24 * lines))
        self.setFixedSize(w, h)

        if persistent:
            btn = QPushButton("知道了", self)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(self._confirm)
            lay = QVBoxLayout(self)
            lay.setContentsMargins(14, 12, 14, 8)
            lay.addStretch(1)
            lay.addWidget(btn, 0, Qt.AlignHCenter)

    def set_top_flag(self, on):
        """同步"显示在最上层"开关：与桌宠/余额/浮动字保持一致。"""
        self._always_on_top = bool(on)
        set_topmost_flag(self, self._always_on_top)

    def set_content(self, text, fill, outline):
        self._text = text
        self._fill = QColor(fill)
        self._outline = QColor(outline)
        self.update()

    def show_auto_hide(self, ms=8000):
        self.show()
        if not self._persistent:
            QTimer.singleShot(ms, self.hide)

    def show_at(self, anchor_rect):
        """anchor_rect：桌宠窗口的全局矩形，气泡显示在其上方居中。"""
        self.set_anchor(anchor_rect)
        self.show_auto_hide()

    def set_anchor(self, anchor_rect):
        """将气泡重新定位到锚点矩形（桌宠窗口）上方居中，不改变显示状态。"""
        geo = self.frameGeometry()
        geo.moveCenter(anchor_rect.center())
        geo.moveBottom(anchor_rect.top() - 8)
        screen = QApplication.screenAt(anchor_rect.center())
        avail = screen.availableGeometry() if screen else QApplication.primaryScreen().availableGeometry()
        geo.moveLeft(max(avail.left() + 4, min(geo.left(), avail.right() - geo.width() - 4)))
        geo.moveTop(max(avail.top() + 4, geo.top()))
        self.move(geo.topLeft())

    def _confirm(self):
        self.hide()
        self.confirmed.emit()

    def mousePressEvent(self, event):
        # 特殊通知（persistent）只能通过按钮确认关闭；普通通知点任意处关闭
        if not self._persistent:
            self.hide()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        bubble = QRectF(8, 8, self.width() - 16, self.height() - 16)
        path = QPainterPath()
        path.addRoundedRect(bubble, 18, 18)

        p.setPen(QPen(self._outline, 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(self._fill)
        p.drawPath(path)

        p.setPen(QColor(30, 30, 30))
        font = p.font()
        font.setPointSize(11)
        font.setBold(True)
        p.setFont(font)
        text_rect = QRectF(bubble.adjusted(18, 12, -18, -12))
        p.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, self._text)
