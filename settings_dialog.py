# -*- coding: utf-8 -*-
"""设置对话框：通知、外观、好感、AI 连接（OpenAI 兼容 + 厂商预设）。"""
import threading
import webbrowser

import requests
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPixmap
from PyQt5.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QColorDialog, QFileDialog,
    QDialogButtonBox, QMessageBox, QCheckBox, QPlainTextEdit, QSpinBox,
    QComboBox, QListWidget, QListWidgetItem,
)

from ai_client import PRESETS
from platforms import PROVIDERS

DEFAULT_PERSONA = (
    "你是一只住在用户桌面上的 AI 桌宠，说话可爱、简短、口语化，每次回复尽量不超过两句话。"
    "你会根据当前情境（时间、天气、好感度等）主动说话，也会回应主人的摸头和聊天。"
)


class AccountDialog(QDialog):
    """绑定余额查询账号：平台 + API Key。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("绑定余额账号")
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
        self._open_btn = open_btn
        self.platform_combo.currentIndexChanged.connect(self._open_btn_url)
        self._open_btn_url()
        form.addRow("", open_btn)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._check)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _open_btn_url(self):
        provider = PROVIDERS.get(self.platform_combo.currentData())
        if provider:
            try:
                self._open_btn.clicked.disconnect()
            except TypeError:
                pass
            self._open_btn.clicked.connect(
                lambda: webbrowser.open(provider.docs_url))

    def _check(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "提示", "请填写账号名称")
            return
        if not self.key_edit.text().strip():
            QMessageBox.warning(self, "提示", "请填写 API Key")
            return
        self.accept()

    def account(self):
        return (
            self.name_edit.text().strip(),
            self.platform_combo.currentData(),
            self.key_edit.text().strip(),
        )


class SettingsDialog(QDialog):
    models_loaded = pyqtSignal(list, bool)  # (模型 id 列表, 是否成功)

    def __init__(self, config, initial_tab=0, rebind_callback=None):
        super().__init__()
        self.config = config
        self._rebind_callback = rebind_callback
        self.setWindowTitle("桌宠设置")
        self.resize(500, 480)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_notify_tab(), "通知")
        self.tabs.addTab(self._build_appearance_tab(), "外观")
        self.tabs.addTab(self._build_affection_tab(), "好感")
        self.tabs.addTab(self._build_balance_tab(), "余额")
        self.tabs.addTab(self._build_ai_tab(), "AI")
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
        form.addRow("测试通知文本", self.text_edit)
        form.addRow("高峰开始文本", self.peak_edit)
        form.addRow("空闲开始文本", self.idle_edit)

        self.font_spin = QSpinBox()
        self.font_spin.setRange(8, 30)
        self.font_spin.setValue(int(self.config.get("balance_font_size", 14)))
        self.font_spin.setSuffix(" pt")
        form.addRow("文本字号（气泡/标签/输入框）", self.font_spin)

        self.fill_edit, _ = self._color_row(form, "气泡填充色", self.config.get("balloon_fill", "#FFFFFF"))
        self.outline_edit, _ = self._color_row(form, "气泡边框色", self.config.get("balloon_outline", "#1E3A8A"))
        return w

    # ---------- 外观页 ----------
    def _build_appearance_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.top_check = QCheckBox("窗口置顶（桌宠 / 通知 / 输入框 / 浮动字）")
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
        preview_lay.addWidget(self._preview_box("单击摸头 PNG/GIF", self.interact_preview))
        lay.addWidget(preview_row)

        btn2 = QPushButton("选择单击摸头 PNG/GIF…")
        btn2.clicked.connect(self._pick_interact)
        lay.addWidget(btn2, 0, Qt.AlignHCenter)
        self.interact_label = QLabel()
        self.interact_label.setWordWrap(True)
        lay.addWidget(self.interact_label)

        self._current_interact = self.config.get("pet_interact_image", "")
        self._current_image = self.config.get("pet_image", "")
        self._update_preview()
        self._update_interact_preview()

        self.head_check = QCheckBox("启用摸头反应（单击桌宠触发，AI 生成反应文本）")
        self.head_check.setChecked(bool(self.config.get("pet_head_enabled", True)))
        lay.addWidget(self.head_check)
        return w

    # ---------- 好感页 ----------
    def _build_affection_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        self.aff_check = QCheckBox("启用好感度系统")
        self.aff_check.setChecked(bool(self.config.get("affection_enabled", True)))
        form.addRow(self.aff_check)
        self.aff_label_check = QCheckBox("显示好感标签")
        self.aff_label_check.setChecked(bool(self.config.get("affection_label_enabled", True)))
        form.addRow(self.aff_label_check)

        self.aff_initial = QSpinBox(); self.aff_initial.setRange(0, 1000)
        self.aff_initial.setValue(int(self.config.get("affection_initial", 70)))
        form.addRow("初始好感", self.aff_initial)
        self.aff_max = QSpinBox(); self.aff_max.setRange(1, 100000)
        self.aff_max.setValue(int(self.config.get("affection_max", 100)))
        form.addRow("好感上限", self.aff_max)
        self.aff_gain = QSpinBox(); self.aff_gain.setRange(0, 1000)
        self.aff_gain.setValue(int(self.config.get("affection_gain", 5)))
        form.addRow("每次摸头增加", self.aff_gain)
        self.aff_decay = QSpinBox(); self.aff_decay.setRange(0, 86400)
        self.aff_decay.setValue(int(self.config.get("affection_decay_sec", 300)))
        self.aff_decay.setSuffix(" 秒")
        form.addRow("多久不互动衰减一次", self.aff_decay)
        self.aff_high = QSpinBox(); self.aff_high.setRange(1, 100)
        self.aff_high.setValue(int(self.config.get("affection_high_threshold_pct", 80)))
        self.aff_high.setSuffix(" %")
        form.addRow("高好感阈值", self.aff_high)
        self.aff_low = QSpinBox(); self.aff_low.setRange(0, 99)
        self.aff_low.setValue(int(self.config.get("affection_low_threshold_pct", 40)))
        self.aff_low.setSuffix(" %")
        form.addRow("低好感阈值", self.aff_low)
        self.aff_cooldown = QSpinBox(); self.aff_cooldown.setRange(0, 86400)
        self.aff_cooldown.setValue(int(self.config.get("affection_quote_cooldown_sec", 600)))
        self.aff_cooldown.setSuffix(" 秒")
        form.addRow("档位切换说话冷却", self.aff_cooldown)

        reset_btn = QPushButton("好感回到初始值")
        reset_btn.clicked.connect(self._reset_affection)
        form.addRow("", reset_btn)
        return w

    # ---------- AI 页 ----------
    def _build_ai_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        self.preset_combo = QComboBox()
        for pid, p in PRESETS.items():
            self.preset_combo.addItem(p["name"], pid)
        self.preset_combo.setCurrentIndex(
            max(0, list(PRESETS.keys()).index(self.config.get("ai_preset", "deepseek_web2api"))
                if self.config.get("ai_preset") in PRESETS else list(PRESETS.keys()).index("custom")))
        form.addRow("厂商预设", self.preset_combo)

        self.base_edit = QLineEdit(self.config.get("ai_base_url", ""))
        self.base_edit.setPlaceholderText("https://api.example.com/v1")
        form.addRow("API 地址（OpenAI 兼容）", self.base_edit)
        self.key_edit = QLineEdit(self.config.get("ai_api_key", ""))
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("sk-...（本机服务可留空）")
        form.addRow("API Key", self.key_edit)
        model_row = QWidget()
        model_lay = QHBoxLayout(model_row)
        model_lay.setContentsMargins(0, 0, 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setMinimumContentsLength(24)
        self.model_combo.setCurrentText(self.config.get("ai_model", ""))
        self.model_refresh = QPushButton("刷新")
        self.model_refresh.setFixedWidth(56)
        self.model_refresh.clicked.connect(self._fetch_models)
        model_lay.addWidget(self.model_combo, 1)
        model_lay.addWidget(self.model_refresh)
        form.addRow("模型名", model_row)

        self.web2api_msgs = QSpinBox()
        self.web2api_msgs.setRange(0, 500)
        self.web2api_msgs.setValue(int(self.config.get("ai_web2api_max_messages", 20)))
        self.web2api_msgs.setSuffix(" 条/对话")
        self.web2api_msgs.setToolTip("每个 DeepSeek 网页对话最多容纳的消息数，达到后自动开新对话（0=不限制）")
        form.addRow("内置对话消息上限", self.web2api_msgs)

        self.preset_combo.currentIndexChanged.connect(self._apply_preset)
        self._apply_preset(keep=True)
        self.models_loaded.connect(self._on_models_loaded)
        self._fetch_models()

        self.persona_edit = QPlainTextEdit()
        self.persona_edit.setPlainText(self.config.get("ai_persona") or DEFAULT_PERSONA)
        self.persona_edit.setFixedHeight(90)
        form.addRow("人设（system prompt）", self.persona_edit)

        self.ctx_spin = QSpinBox(); self.ctx_spin.setRange(0, 100)
        self.ctx_spin.setValue(int(self.config.get("ai_context_n", 10)))
        form.addRow("携带历史对话条数", self.ctx_spin)

        self.fallback_check = QCheckBox("AI 生成失败时显示兜底文本")
        self.fallback_check.setChecked(bool(self.config.get("ai_fallback_enabled", True)))
        form.addRow(self.fallback_check)
        self.fallback_edit = QLineEdit(self.config.get("ai_fallback_text", "唔……我现在有点短路了"))
        form.addRow("兜底文本", self.fallback_edit)

        self.talk_check = QCheckBox("启用自言自语（情境触发 + 定时随机）")
        self.talk_check.setChecked(bool(self.config.get("self_talk_enabled", True)))
        form.addRow(self.talk_check)
        self.talk_interval = QSpinBox(); self.talk_interval.setRange(0, 1800)
        self.talk_interval.setValue(int(self.config.get("self_talk_interval", 300)))
        self.talk_interval.setSuffix(" 秒")
        form.addRow("随机自言自语间隔（0=仅情境触发）", self.talk_interval)
        if self._rebind_callback is not None:
            self.rebind_btn = QPushButton("重新绑定（清空旧登录态，打开登录页切换账号）")
            self.rebind_btn.clicked.connect(self._rebind)
            form.addRow(self.rebind_btn)
        return w

    def _rebind(self):
        if self._rebind_callback is None:
            return
        self.rebind_btn.setEnabled(False)
        self.rebind_btn.setText("正在清空旧登录态并打开登录浏览器……登录完成后关闭控制台窗口")
        self._rebind_callback()

    def _apply_preset(self, _=None, keep=False):
        p = PRESETS.get(self.preset_combo.currentData())
        if not p:
            return
        changed = self.config.get("ai_preset") != self.preset_combo.currentData()
        if keep and changed:
            keep = False  # 用户切换了预设：覆盖 base/model
        if keep:
            self.base_edit.setText(self.config.get("ai_base_url", p["base_url"]))
            self.model_combo.setCurrentText(self.config.get("ai_model", p["model"]))
        elif self.preset_combo.currentData() != "custom":
            self.base_edit.setText(p["base_url"])
            self.model_combo.setCurrentText(p["model"])
            if p.get("key"):
                self.key_edit.setText(p["key"])
        if changed or not keep:
            self._fetch_models()

    def _fetch_models(self):
        base = self.base_edit.text().strip().rstrip("/")
        if not base:
            return
        key = self.key_edit.text().strip()
        self.model_refresh.setEnabled(False)
        self.model_refresh.setText("获取中…")
        threading.Thread(target=self._fetch_models_worker, args=(base, key), daemon=True).start()

    def _fetch_models_worker(self, base, key):
        try:
            r = requests.get(base + "/models",
                             headers={"Authorization": "Bearer " + key} if key else {},
                             timeout=8)
            if r.status_code == 200:
                ids = [str(m["id"]) for m in (r.json().get("data") or []) if m.get("id")]
                if ids:
                    self._emit_models(ids, True)
                    return
        except Exception:
            pass
        self._emit_models([], False)

    def _emit_models(self, ids, ok):
        try:
            self.models_loaded.emit(ids, ok)
        except RuntimeError:
            pass  # 对话框已关闭，线程收尾

    def _on_models_loaded(self, ids, ok):
        self.model_refresh.setEnabled(True)
        self.model_refresh.setText("刷新")
        current = self.model_combo.currentText()
        if ok:
            self.model_combo.clear()
            self.model_combo.addItems(ids)
            if current:
                self.model_combo.setCurrentText(current)
            elif ids:
                self.model_combo.setCurrentIndex(0)
        else:
            self.model_combo.setToolTip("获取模型列表失败，可手动输入模型名")

    def _reset_affection(self):
        self.config.set("affection_value", float(self.aff_initial.value()))
        self.config.set("affection_last_update", 0.0)

    # ---------- 余额页 ----------
    def _build_balance_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)

        self.balance_check = QCheckBox("显示余额文本（桌宠左上角，可拖动）")
        self.balance_check.setChecked(bool(self.config.get("show_balance", True)))
        lay.addWidget(self.balance_check)

        form = QFormLayout()
        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(1, 600)
        self.poll_spin.setValue(int(self.config.get("poll_interval_sec", 3)))
        self.poll_spin.setSuffix(" 秒")
        form.addRow("余额轮询间隔", self.poll_spin)

        self.work_label_check = QCheckBox("显示工作状态标签（余额升降判定）")
        self.work_label_check.setChecked(bool(self.config.get("work_label_enabled", True)))
        form.addRow("工作状态", self.work_label_check)
        self.work_hold_spin = QSpinBox()
        self.work_hold_spin.setRange(0, 86400)
        self.work_hold_spin.setValue(int(self.config.get("work_state_hold_sec", 180)))
        self.work_hold_spin.setSuffix(" 秒")
        self.work_hold_spin.setToolTip("余额下降后保持'工作中'的时长；余额同步往往没那么快，避免很快又显示'空闲中'")
        form.addRow("余额下降后保持'工作中'", self.work_hold_spin)
        lay.addLayout(form)

        lay.addWidget(QLabel("余额账号（多平台，未绑定则不查询）"))
        self.accounts_list = QListWidget()
        accounts = self.config.get("accounts", {}) or {}
        for name in accounts:
            acc = accounts[name]
            pid = acc.get("platform", "deepseek") if isinstance(acc, dict) else "deepseek"
            provider = PROVIDERS.get(pid)
            item = QListWidgetItem("%s（%s）" % (name, provider.name if provider else pid))
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
        item = QListWidgetItem("%s（%s）" % (name, provider.name if provider else platform))
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

    # ---------- 颜色 / 预览工具 ----------
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
            btn.setStyleSheet("background:%s; border:1px solid #888; border-radius:4px;" % color.name())

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
        path, _ = QFileDialog.getOpenFileName(self, "选择单击摸头 PNG/GIF", "", "图片 (*.png *.gif)")
        if path:
            self._current_interact = path
            self._update_interact_preview()

    def _update_interact_preview(self):
        self.interact_label.setText("当前单击摸头 PNG/GIF：%s" % (self._current_interact or "（未设置）"))
        pm = QPixmap(self._current_interact) if self._current_interact else QPixmap()
        if not pm.isNull():
            self.interact_preview.setPixmap(pm.scaled(self.interact_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.interact_preview.setText("预览")

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择桌宠图片", "", "图片 (*.png *.gif)")
        if path:
            self._current_image = path
            self._update_preview()

    def _update_preview(self):
        path = self._current_image
        self.image_path_label.setText("当前图片：%s" % (path or "（未设置，使用默认）"))
        pm = QPixmap(path) if path else QPixmap()
        if not pm.isNull():
            self.preview.setPixmap(pm.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.preview.setText("预览")

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
        self.config.set("balance_font_size", self.font_spin.value())
        self.config.set("pet_head_enabled", self.head_check.isChecked())
        self.config.set("affection_enabled", self.aff_check.isChecked())
        self.config.set("affection_initial", self.aff_initial.value())
        self.config.set("affection_max", self.aff_max.value())
        self.config.set("affection_gain", self.aff_gain.value())
        self.config.set("affection_decay_sec", self.aff_decay.value())
        self.config.set("affection_high_threshold_pct", self.aff_high.value())
        self.config.set("affection_low_threshold_pct", self.aff_low.value())
        self.config.set("affection_quote_cooldown_sec", self.aff_cooldown.value())
        self.config.set("affection_label_enabled", self.aff_label_check.isChecked())
        self.config.set("show_balance", self.balance_check.isChecked())
        self.config.set("poll_interval_sec", self.poll_spin.value())
        self.config.set("work_label_enabled", self.work_label_check.isChecked())
        self.config.set("work_state_hold_sec", self.work_hold_spin.value())
        self.config.set("ai_preset", self.preset_combo.currentData())
        self.config.set("ai_base_url", self.base_edit.text().strip())
        self.config.set("ai_api_key", self.key_edit.text().strip())
        self.config.set("ai_model", self.model_combo.currentText().strip())
        self.config.set("ai_persona", self.persona_edit.toPlainText().strip() or DEFAULT_PERSONA)
        self.config.set("ai_context_n", self.ctx_spin.value())
        self.config.set("ai_fallback_enabled", self.fallback_check.isChecked())
        self.config.set("ai_fallback_text", self.fallback_edit.text().strip() or "唔……我现在有点短路了")
        self.config.set("ai_web2api_max_messages", self.web2api_msgs.value())
        self.config.set("self_talk_enabled", self.talk_check.isChecked())
        self.config.set("self_talk_interval", self.talk_interval.value())
        self.accept()
