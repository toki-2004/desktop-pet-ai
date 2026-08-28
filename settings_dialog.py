# -*- coding: utf-8 -*-
"""设置对话框：通知颜色/文本、外观、账号绑定（含浏览器打开 DeepSeek 平台）。"""
import json
import os
import webbrowser

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPixmap
from PyQt5.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QColorDialog, QFileDialog, QListWidget,
    QListWidgetItem, QDialogButtonBox, QMessageBox, QCheckBox, QPlainTextEdit,
    QSpinBox, QComboBox,
)

from platforms import PROVIDERS


class AccountDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("绑定 DeepSeek 账号")
        self.setMinimumWidth(360)
        form = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：主账号")
        self.platform_combo = QComboBox()
        for pid, provider in PROVIDERS.items():
            self.platform_combo.addItem(provider.name, pid)
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("sk-...")
        form.addRow("账号名称", self.name_edit)
        form.addRow("平台", self.platform_combo)
        form.addRow("API Key", self.key_edit)

        open_btn = QPushButton("在浏览器打开平台官网")
        open_btn.clicked.connect(lambda: webbrowser.open("https://platform.deepseek.com/"))
        self._open_btn = open_btn
        self.platform_combo.currentIndexChanged.connect(self._open_btn_url)
        self._open_btn_url()
        form.addRow("", open_btn)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._check)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _check(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "提示", "请填写账号名称")
            return
        if not self.key_edit.text().strip():
            QMessageBox.warning(self, "提示", "请填写 API Key")
            return
        self.accept()

    def _open_btn_url(self):
        provider = PROVIDERS.get(self.platform_combo.currentData())
        if provider:
            self._open_btn.clicked.disconnect()
            self._open_btn.clicked.connect(
                lambda: webbrowser.open(provider.docs_url)
            )

    def account(self):
        return (
            self.name_edit.text().strip(),
            self.platform_combo.currentData(),
            self.key_edit.text().strip(),
        )


class SettingsDialog(QDialog):
    def __init__(self, config, initial_tab=0):
        super().__init__()
        self.config = config
        self.setWindowTitle("桌宠设置")
        self.resize(480, 440)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_notify_tab(), "通知")
        self.tabs.addTab(self._build_appearance_tab(), "外观")
        self.tabs.addTab(self._build_accounts_tab(), "账号")
        self.tabs.setCurrentIndex(initial_tab)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs)
        lay.addWidget(btns)

    # ---------- 通知页 ----------
    def _build_notify_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        self.text_edit = QLineEdit(self.config.get("balloon_text", ""))
        self.peak_edit = QLineEdit(self.config.get("peak_balloon_text", ""))
        self.idle_edit = QLineEdit(self.config.get("idle_balloon_text", ""))
        form.addRow("通知文本", self.text_edit)
        form.addRow("高峰开始文本", self.peak_edit)
        form.addRow("空闲开始文本", self.idle_edit)

        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(1, 3600)
        self.poll_spin.setValue(int(self.config.get("poll_interval_sec", 3)))
        self.poll_spin.setSuffix(" 秒")
        form.addRow("余额刷新间隔", self.poll_spin)

        self.fill_edit, self.fill_btn = self._color_row(form, "云线填充色", self.config.get("balloon_fill", "#FFFFFF"))
        self.outline_edit, self.outline_btn = self._color_row(form, "云线描边色", self.config.get("balloon_outline", "#1E3A8A"))

        form.addRow(QLabel("自言自语（挂机闲聊通知）"))
        self.talk_check = QCheckBox("启用")
        self.talk_check.setChecked(bool(self.config.get("self_talk_enabled", True)))
        form.addRow("自言自语通知", self.talk_check)
        self.talk_edit = QPlainTextEdit()
        self.talk_edit.setPlainText("\n".join(self._load_talk_texts()))
        self.talk_edit.setPlaceholderText("每行一条，桌宠会随机自言自语")
        self.talk_edit.setFixedHeight(110)
        form.addRow("文本库（每行一条）", self.talk_edit)
        talk_file = self.config.get("self_talk_file") or ""
        path_lab = QLabel("文本库文件：%s" % talk_file)
        path_lab.setWordWrap(True)
        path_lab.setStyleSheet("color:#666; font-size:11px;")
        form.addRow("", path_lab)
        self.talk_interval = QSpinBox()
        self.talk_interval.setRange(0, 1800)
        self.talk_interval.setValue(int(self.config.get("self_talk_interval", 300)))
        self.talk_interval.setSuffix(" 秒")
        form.addRow("间隔（0~1800 秒）", self.talk_interval)
        return w

    def _load_talk_texts(self):
        return self._load_quotes("self_talk_file", "self_talk_texts")

    def _load_head_texts(self):
        return self._load_quotes("pet_head_file", "pet_head_texts")

    def _load_quotes(self, file_key, default_key):
        """读取 JSON 语录库；兼容旧 txt 每行一条格式。"""
        path = self.config.get(file_key) or ""
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    texts = [str(t).strip() for t in data if str(t).strip()]
                    if texts:
                        return texts
            except Exception:
                pass
            try:
                with open(path, encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip()]
                if lines:
                    return lines
            except Exception:
                pass
        return self.config.get(default_key) or []

    def _write_quotes(self, file_key, default_key, texts):
        path = self.config.get(file_key) or ""
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(texts, f, ensure_ascii=False, indent=2)
                return
            except Exception:
                pass
        # 无文件路径时退回配置内置数组
        self.config.set(default_key, texts)

    def _color_row(self, form, label, hex_color):
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit(hex_color)
        edit.setFixedWidth(90)
        btn = QPushButton()
        btn.setFixedSize(40, 24)
        btn.setToolTip("点击打开取色器（含吸管与十六进制输入）")
        self._paint_color_btn(btn, hex_color)
        edit.editingFinished.connect(lambda e=edit, b=btn: self._sync_hex(e, b))
        btn.clicked.connect(lambda _, e=edit, b=btn: self._pick_color(e, b))
        lay.addWidget(edit)
        lay.addWidget(btn)
        lay.addStretch(1)
        form.addRow(label, row)
        return edit, btn

    def _paint_color_btn(self, btn, hex_color):
        color = QColor(hex_color)
        if color.isValid():
            btn.setStyleSheet(
                "background:%s; border:1px solid #888; border-radius:4px;" % color.name()
            )

    def _sync_hex(self, edit, btn):
        color = QColor(edit.text().strip())
        if color.isValid():
            edit.setText(color.name().upper())
            self._paint_color_btn(btn, color.name())
        else:
            QMessageBox.warning(self, "提示", "无效的颜色代码，示例：#1E3A8A")

    def _pick_color(self, edit, btn):
        dlg = QColorDialog(QColor(edit.text().strip()), self)
        dlg.setOption(QColorDialog.DontUseNativeDialog, True)
        dlg.setOption(QColorDialog.ShowAlphaChannel, False)
        if dlg.exec_():
            name = dlg.currentColor().name().upper()
            edit.setText(name)
            self._paint_color_btn(btn, name)

    # ---------- 外观页 ----------
    def _build_appearance_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.top_check = QCheckBox("窗口置顶（桌宠 / 通知 / 余额 / 浮动字）")
        self.top_check.setChecked(bool(self.config.get("always_on_top", True)))
        lay.addWidget(self.top_check)

        self.image_path_label = QLabel()
        self.image_path_label.setWordWrap(True)
        lay.addWidget(self.image_path_label)
        btn = QPushButton("导入 PNG / GIF…")
        btn.clicked.connect(self._pick_image)
        lay.addWidget(btn, 0, Qt.AlignHCenter)

        preview_row = QWidget()
        preview_lay = QHBoxLayout(preview_row)
        preview_lay.setContentsMargins(0, 0, 0, 0)
        self.preview = self._make_preview()
        self.interact_preview = self._make_preview()
        preview_lay.addWidget(self._preview_box("默认图", self.preview))
        preview_lay.addWidget(self._preview_box("左键交互 PNG/GIF", self.interact_preview))
        lay.addWidget(preview_row)

        btn2 = QPushButton("选择左键交互 PNG/GIF…")
        btn2.clicked.connect(self._pick_interact)
        lay.addWidget(btn2, 0, Qt.AlignHCenter)
        self.interact_label = QLabel()
        self.interact_label.setWordWrap(True)
        lay.addWidget(self.interact_label)

        self._current_interact = self.config.get("pet_interact_image", "")
        self._current_image = self.config.get("pet_image", "")
        self._update_preview()
        self._update_interact_preview()

        # 摸头语录库（独立于自言自语，长按桌宠触发）
        head_box = QWidget()
        hv = QVBoxLayout(head_box)
        self.head_check = QCheckBox("启用摸头语录（长按桌宠触发）")
        self.head_check.setChecked(bool(self.config.get("pet_head_enabled", True)))
        hv.addWidget(self.head_check)
        self.head_edit = QPlainTextEdit()
        self.head_edit.setPlainText("\n".join(self._load_head_texts()))
        self.head_edit.setPlaceholderText("每行一条，长按桌宠时随机显示")
        self.head_edit.setFixedHeight(90)
        hv.addWidget(self.head_edit)
        head_row = QHBoxLayout()
        self.head_interval = QSpinBox()
        self.head_interval.setRange(1, 300)
        self.head_interval.setValue(int(self.config.get("pet_head_interval", 10)))
        self.head_interval.setSuffix(" 秒")
        self.head_press_ms = QSpinBox()
        self.head_press_ms.setRange(300, 2000)
        self.head_press_ms.setSingleStep(50)
        self.head_press_ms.setValue(int(self.config.get("pet_head_long_press_ms", 600)))
        self.head_press_ms.setSuffix(" 毫秒")
        head_row.addWidget(QLabel("按住期间换语录间隔"))
        head_row.addWidget(self.head_interval)
        head_row.addWidget(QLabel("长按判定"))
        head_row.addWidget(self.head_press_ms)
        head_row.addStretch(1)
        hv.addLayout(head_row)
        head_file = self.config.get("pet_head_file") or ""
        head_lab = QLabel("摸头语录库文件：%s" % head_file)
        head_lab.setWordWrap(True)
        head_lab.setStyleSheet("color:#666; font-size:11px;")
        hv.addWidget(head_lab)
        lay.addWidget(head_box)
        return w

    def _make_preview(self):
        lab = QLabel()
        lab.setAlignment(Qt.AlignCenter)
        lab.setFixedSize(150, 150)
        lab.setStyleSheet("border:1px dashed #aaa;")
        return lab

    def _preview_box(self, caption, preview):
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        cap = QLabel(caption)
        cap.setAlignment(Qt.AlignCenter)
        cap.setStyleSheet("color:#666; font-size:11px;")
        v.addWidget(cap)
        v.addWidget(preview, 0, Qt.AlignHCenter)
        return box

    def _pick_interact(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择左键交互 PNG/GIF", "", "图片 (*.png *.gif)"
        )
        if path:
            self._current_interact = path
            self._update_interact_preview()

    def _update_interact_preview(self):
        self.interact_label.setText(
            "当前左键交互 PNG/GIF：%s" % (self._current_interact or "（未设置）")
        )
        pm = QPixmap(self._current_interact) if self._current_interact else QPixmap()
        if not pm.isNull():
            self.interact_preview.setPixmap(
                pm.scaled(self.interact_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            self.interact_preview.setText("预览")

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择桌宠图片", "", "图片 (*.png *.gif)"
        )
        if path:
            self._current_image = path
            self._update_preview()

    def _update_preview(self):
        path = self._current_image
        self.image_path_label.setText("当前图片：%s" % (path or "（未设置，使用默认）"))
        pm = QPixmap(path) if path else QPixmap()
        if not pm.isNull():
            self.preview.setPixmap(
                pm.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            self.preview.setText("预览")

    # ---------- 账号页 ----------
    def _build_accounts_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.accounts_list = QListWidget()
        accounts = self.config.get("accounts", {}) or {}
        for name in accounts:
            acc = accounts[name]
            pid = acc.get("platform", "deepseek") if isinstance(acc, dict) else "deepseek"
            provider = PROVIDERS.get(pid)
            label = "%s（%s）" % (name, provider.name if provider else pid)
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, name)
            self.accounts_list.addItem(item)
        lay.addWidget(self.accounts_list)
        row = QHBoxLayout()
        add_btn = QPushButton("添加账号")
        add_btn.clicked.connect(self._add_account)
        del_btn = QPushButton("删除选中")
        del_btn.clicked.connect(self._del_account)
        row.addWidget(add_btn)
        row.addWidget(del_btn)
        lay.addLayout(row)
        return w

    def _add_account(self):
        dlg = AccountDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        name, platform, key = dlg.account()
        accounts = self.config.get("accounts", {}) or {}
        if name in accounts:
            QMessageBox.warning(self, "提示", "该账号名称已存在")
            return
        accounts[name] = {"platform": platform, "api_key": key}
        self.config.set("accounts", accounts)
        provider = PROVIDERS.get(platform)
        label = "%s（%s）" % (name, provider.name if provider else platform)
        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, name)
        self.accounts_list.addItem(item)

    def _del_account(self):
        item = self.accounts_list.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole) or item.text()
        accounts = self.config.get("accounts", {}) or {}
        accounts.pop(name, None)
        self.config.set("accounts", accounts)
        self.accounts_list.takeItem(self.accounts_list.row(item))

    # ---------- 保存 ----------
    def _save(self):
        self.config.set("balloon_text", self.text_edit.text().strip() or "主人，有新消息啦！")
        self.config.set("peak_balloon_text", self.peak_edit.text().strip() or "高峰时段开始啦……")
        self.config.set("idle_balloon_text", self.idle_edit.text().strip() or "空闲时段开始啦！")
        fill = QColor(self.fill_edit.text().strip())
        outline = QColor(self.outline_edit.text().strip())
        if fill.isValid():
            self.config.set("balloon_fill", fill.name().upper())
        if outline.isValid():
            self.config.set("balloon_outline", outline.name().upper())
        self.config.set("pet_image", self._current_image)
        self.config.set("pet_interact_image", self._current_interact)
        self.config.set("always_on_top", self.top_check.isChecked())
        self.config.set("poll_interval_sec", self.poll_spin.value())
        self.config.set("self_talk_enabled", self.talk_check.isChecked())
        self.config.set("self_talk_interval", self.talk_interval.value())
        texts = [t.strip() for t in self.talk_edit.toPlainText().splitlines() if t.strip()]
        self._write_quotes("self_talk_file", "self_talk_texts", texts)
        head_texts = [t.strip() for t in self.head_edit.toPlainText().splitlines() if t.strip()]
        self.config.set("pet_head_enabled", self.head_check.isChecked())
        self.config.set("pet_head_interval", self.head_interval.value())
        self.config.set("pet_head_long_press_ms", self.head_press_ms.value())
        self._write_quotes("pet_head_file", "pet_head_texts", head_texts)
        self.accept()
