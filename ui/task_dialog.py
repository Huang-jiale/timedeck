from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from models import QUADRANTS, STATUS_DOING, STATUS_DONE, STATUS_TODO, Task
from ui import theme

STATUS_CHOICES = [("待办", STATUS_TODO), ("进行中", STATUS_DOING), ("已完成", STATUS_DONE)]


def tags_from_text(text: str) -> list[str]:
    parts = text.replace("#", " ").replace("，", " ").replace(",", " ").split()
    seen: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return seen


def _datetime_edit(value: datetime | None, fallback: datetime) -> QDateTimeEdit:
    editor = QDateTimeEdit(value or fallback)
    editor.setDisplayFormat("yyyy-MM-dd HH:mm")
    editor.setCalendarPopup(True)
    editor.setButtonSymbols(QDateTimeEdit.NoButtons)
    return editor


class TaskDialog(QDialog):
    """新建 / 编辑任务：开始时间、专注时长、标签等全部交给用户自己填。"""

    def __init__(self, store, task: Task | None = None, preset: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.task = task
        self.delete_requested = False
        preset = preset or {}
        self.setWindowTitle("编辑任务" if task else "新建任务")
        self.setMinimumWidth(430)

        now = datetime.now()
        today_evening = now.replace(hour=18, minute=0, second=0, microsecond=0)
        title = QLineEdit(task.title if task else preset.get("title", ""))
        title.setPlaceholderText("要做什么")
        start_on = QCheckBox("设定")
        start_at = _datetime_edit((task.start_dt if task else preset.get("start")), now.replace(second=0, microsecond=0))
        due_on = QCheckBox("设定")
        due_at = _datetime_edit((task.due_dt if task else preset.get("due")), today_evening)
        for box, editor in ((start_on, start_at), (due_on, due_at)):
            editor.setEnabled(False)
            box.toggled.connect(editor.setEnabled)
        if task and task.start_dt:
            start_on.setChecked(True)
        if task and task.due_dt:
            due_on.setChecked(True)

        tag_input = QLineEdit(" ".join(task.tags if task else preset.get("tags", [])))
        tag_input.setPlaceholderText("空格分隔，例如：工作 学习")
        self.tag_chips = QWidget()
        chips = QHBoxLayout(self.tag_chips)
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(6)
        self._tag_buttons: dict[str, QPushButton] = {}
        existing = sorted({tag for item in self.store.active_tasks() for tag in item.tags})
        for tag in existing[:8]:
            button = QPushButton(tag)
            button.setObjectName("ghostBtn")
            button.setCheckable(True)
            button.setStyleSheet("padding: 2px 9px; font-size: 11px;")
            if tag in (task.tags if task else preset.get("tags", [])):
                button.setChecked(True)
            button.toggled.connect(lambda on, t=tag: self._sync_tag(t, on))
            chips.addWidget(button)
            self._tag_buttons[tag] = button
        chips.addStretch(1)
        if not existing:
            self.tag_chips.hide()

        priority = QComboBox()
        for label, value in (("低", 1), ("中", 2), ("高", 3)):
            priority.addItem(label, value)
        priority.setCurrentIndex({"1": 0, "2": 1, "3": 2}.get(str(task.priority if task else preset.get("priority", 1)), 0))

        est = QSpinBox()
        est.setRange(5, 1440)
        est.setSingleStep(15)
        est.setSuffix(" 分钟")
        est.setValue(int(task.est_min if task else preset.get("est_min") or 60))

        focus = QSpinBox()
        focus.setRange(0, 480)
        focus.setSingleStep(5)
        focus.setSuffix(" 分钟")
        default_min = int(self.store.settings["focus_min"])
        focus.setValue(int(task.focus_min if task and task.focus_min else preset.get("focus_min") or default_min))
        self.focus_hint = QLabel(f"0 表示跟随默认（当前默认 {default_min} 分钟）")

        quadrant = QComboBox()
        quadrant.addItem("还没分派", None)
        for key, (label, _) in QUADRANTS.items():
            quadrant.addItem(f"Q{key} · {label}", key)
        wanted = task.quadrant if task else preset.get("quadrant")
        index = quadrant.findData(wanted)
        quadrant.setCurrentIndex(index if index >= 0 else 0)

        status = QComboBox()
        for label, value in STATUS_CHOICES:
            status.addItem(label, value)
        status.setCurrentIndex(max(0, [value for _, value in STATUS_CHOICES].index(task.status if task else STATUS_TODO)))
        status.setVisible(bool(task))

        form = QFormLayout()
        form.setSpacing(9)
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("标题", title)
        form.addRow("开始时间", self._pair(start_on, start_at))
        form.addRow("截止时间", self._pair(due_on, due_at))
        form.addRow("标签", tag_input)
        form.addRow("", self.tag_chips)
        form.addRow("优先级", priority)
        form.addRow("预估总时长", est)
        form.addRow("一段专注", focus)
        form.addRow("", self.focus_hint)
        form.addRow("象限", quadrant)
        if task:
            form.addRow("状态", status)

        self.widgets = {"title": title, "start_on": start_on, "start_at": start_at,
                        "due_on": due_on, "due_at": due_at, "tags": tag_input,
                        "priority": priority, "est": est, "focus": focus,
                        "quadrant": quadrant, "status": status}

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        row = QHBoxLayout()
        if task:
            delete = QPushButton("删除任务")
            delete.setObjectName("dangerBtn")
            delete.setCursor(Qt.PointingHandCursor)
            delete.clicked.connect(self._delete)
            row.addWidget(delete)
        row.addStretch(1)
        row.addWidget(buttons)

        box = QVBoxLayout(self)
        box.setContentsMargins(18, 16, 18, 14)
        box.setSpacing(10)
        box.addLayout(form)
        box.addLayout(row)
        title.setFocus()

    def _pair(self, check: QCheckBox, editor: QDateTimeEdit) -> QWidget:
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(editor, 1)
        layout.addWidget(check)
        return holder

    def _sync_tag(self, tag: str, on: bool) -> None:
        current = tags_from_text(self.widgets["tags"].text())
        if on and tag not in current:
            current.append(tag)
        if not on and tag in current:
            current = [item for item in current if item != tag]
        self.widgets["tags"].setText(" ".join(current))

    def fields(self) -> dict:
        title = self.widgets["title"].text().strip()
        tags = tags_from_text(self.widgets["tags"].text())
        for tag, button in self._tag_buttons.items():
            button.blockSignals(True)
            button.setChecked(tag in tags)
            button.blockSignals(False)
        focus = int(self.widgets["focus"].value())
        return {
            "title": title,
            "start": self.widgets["start_at"].dateTime().toPython() if self.widgets["start_on"].isChecked() else None,
            "due": self.widgets["due_at"].dateTime().toPython() if self.widgets["due_on"].isChecked() else None,
            "tags": tags,
            "priority": int(self.widgets["priority"].currentData()),
            "est_min": int(self.widgets["est"].value()),
            "focus_min": focus or None,
            "quadrant": self.widgets["quadrant"].currentData(),
            "status": self.widgets["status"].currentData(),
        }

    def _accept(self) -> None:
        if not self.widgets["title"].text().strip():
            self.widgets["title"].setFocus()
            self.widgets["title"].setStyleSheet(f"border: 1px solid {theme.DANGER};")
            return
        self.accept()

    def _delete(self) -> None:
        if self.task:
            self.store.remove(self.task.id)
            self.delete_requested = True
        self.accept()
