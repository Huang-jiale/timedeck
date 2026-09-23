from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from ui import theme


class SettingsDialog(QDialog):
    def __init__(self, store, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("设置")
        self.resize(420, 360)
        self.setStyleSheet(f"QDialog {{ background: {theme.BG}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        title = QLabel("计时与视图")
        title.setObjectName("viewTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft)
        s = store.settings
        self.focus_min = QSpinBox()
        self.focus_min.setRange(5, 180)
        self.focus_min.setValue(int(s["focus_min"]))
        self.focus_min.setSuffix(" 分钟")
        self.break_min = QSpinBox()
        self.break_min.setRange(0, 60)
        self.break_min.setValue(int(s["break_min"]))
        self.break_min.setSuffix(" 分钟")
        self.busy = QSpinBox()
        self.busy.setRange(1, 40)
        self.busy.setValue(int(s["busy_threshold"]))
        self.busy.setSuffix(" 件任务")
        self.busy.setToolTip("一天任务数超过这个值，日历格会变红表示超载")
        self.focus_min.setToolTip("新建任务默认用这个时长；任务行上的「N 分 ▾」可以给单个任务单独设")
        form.addRow("默认专注时长", self.focus_min)
        form.addRow("休息时长", self.break_min)
        form.addRow("超载阈值", self.busy)
        layout.addLayout(form)

        opacity = QFormLayout()
        opacity.setSpacing(10)
        self.float_opacity = self._slider(int(float(s["float_opacity"]) * 100))
        self.idle_opacity = self._slider(int(float(s["idle_opacity"]) * 100))
        opacity.addRow("悬浮窗不透明度", self.float_opacity[0])
        opacity.addRow("闲置淡出后", self.idle_opacity[0])
        layout.addLayout(opacity)

        self.notify = QCheckBox("计时结束时发系统通知")
        self.notify.setChecked(bool(s["notify_on_finish"]))
        self.sound = QCheckBox("计时结束时响一声")
        self.sound.setChecked(bool(s["sound_on_finish"]))
        layout.addWidget(self.notify)
        layout.addWidget(self.sound)

        path = QLabel(f"数据文件：{store.data_path}")
        path.setObjectName("muted")
        path.setWordWrap(True)
        layout.addWidget(path)

        backup = QHBoxLayout()
        export = QPushButton("导出 data.json 副本")
        export.setObjectName("chipBtn")
        export.clicked.connect(self._export)
        import_btn = QPushButton("从文件导入")
        import_btn.setObjectName("ghostBtn")
        import_btn.clicked.connect(self._import)
        restore = QPushButton("回退到最近备份")
        restore.setObjectName("ghostBtn")
        restore.clicked.connect(self._restore)
        backup.addWidget(export)
        backup.addWidget(import_btn)
        backup.addWidget(restore)
        backup.addStretch(1)
        layout.addLayout(backup)
        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _slider(self, value: int):
        holder = QWidget()
        box = QHBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(30, 100)
        slider.setValue(value)
        slider.setFixedWidth(180)
        readout = QLabel(f"{value}%")
        readout.setObjectName("muted")
        slider.valueChanged.connect(lambda v: readout.setText(f"{v}%"))
        box.addWidget(slider)
        box.addWidget(readout)
        box.addStretch(1)
        holder.slider = slider
        return holder, slider

    def _export(self) -> None:
        from PySide6.QtGui import QGuiApplication
        target, _ = QFileDialog.getSaveFileName(self, "导出到", "timedeck-data.json", "JSON (*.json)")
        if target:
            self.store.export_to(target)
            QGuiApplication.clipboard().setText(str(target))

    def _import(self) -> None:
        source, _ = QFileDialog.getOpenFileName(self, "选择 data.json", "", "JSON (*.json)")
        if source:
            self.store.import_from(source)

    def _restore(self) -> None:
        backup = self.store.path.with_name("data.json.bak0")
        if backup.exists():
            self.store.path.unlink()
            backup.rename(self.store.path)
            self.store.load()

    def apply(self) -> None:
        s = self.store.settings
        s["focus_min"] = self.focus_min.value()
        s["break_min"] = self.break_min.value()
        s["busy_threshold"] = self.busy.value()
        s["float_opacity"] = self.float_opacity.slider.value() / 100
        s["idle_opacity"] = self.idle_opacity.slider.value() / 100
        s["notify_on_finish"] = self.notify.isChecked()
        s["sound_on_finish"] = self.sound.isChecked()
        self.store.mark_dirty("settings")
