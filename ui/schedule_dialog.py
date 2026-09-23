from __future__ import annotations

from datetime import date, datetime, time, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDateTimeEdit, QDialog,
    QDialogButtonBox, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QVBoxLayout, QWidget,
)

from models import QUADRANTS
from ui.task_dialog import UNSET

MODES = [("每天", "daily"), ("每隔 N 天", "every"), ("每个工作日", "workday"), ("每周固定几天", "weekday")]
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


class ScheduleDialog(QDialog):
    """在未来一段时间里按重复规则批量生成任务。"""

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("批量排期")
        self.setMinimumWidth(470)
        today = date.today()

        self.title = QLineEdit()
        self.title.setPlaceholderText("例如：晨跑 5 公里")
        self.start_on = QDateEdit(today, displayFormat="yyyy-MM-dd")
        self.start_on.setCalendarPopup(True)
        self.at_time = QDateTimeEdit(datetime.combine(today, time(18, 0)), displayFormat="HH:mm")
        self.at_time.setDisplayFormat("HH:mm")
        self.at_time.setCalendarPopup(False)
        self.mode = QComboBox()
        for label, _ in MODES:
            self.mode.addItem(label, _)
        self.mode.currentIndexChanged.connect(self._sync_mode)
        self.interval = QSpinBox()
        self.interval.setRange(2, 60)
        self.interval.setValue(3)
        self.interval.setSuffix(" 天")
        self.interval.setEnabled(False)

        self.weekday_boxes = []
        weekday_row = QWidget()
        grid = QGridLayout(weekday_row)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        for index, name in enumerate(WEEKDAYS):
            box = QCheckBox(name)
            box.stateChanged.connect(self._preview)
            grid.addWidget(box, 0, index)
            self.weekday_boxes.append(box)
        self.weekday_row = weekday_row
        self.weekday_row.setVisible(False)

        self.by_count = QComboBox()
        self.by_count.addItems(["按次数", "按结束日期"])
        self.by_count.currentIndexChanged.connect(self._sync_end)
        self.repeat_times = QSpinBox()
        self.repeat_times.setRange(1, 60)
        self.repeat_times.setValue(7)
        self.repeat_times.setSuffix(" 次")
        self.until = QDateEdit(today + timedelta(days=30), displayFormat="yyyy-MM-dd")
        self.until.setCalendarPopup(True)
        self.until.setEnabled(False)

        self.tags = QLineEdit()
        self.tags.setPlaceholderText("空格分隔，可留空")
        self.focus = QSpinBox()
        self.focus.setRange(0, 480)
        self.focus.setSingleStep(5)
        self.focus.setSuffix(" 分钟")
        self.focus.setValue(int(self.store.settings["focus_min"]))
        self.quadrant = QComboBox()
        self.quadrant.addItem("请选择象限…", UNSET)
        self.quadrant.addItem("不分象限（进任务池）", None)
        for key, (label, _) in QUADRANTS.items():
            self.quadrant.addItem(f"Q{key} · {label}", key)
        self.quadrant.setCurrentIndex(0)
        self.suffix_date = QCheckBox("标题后面带上日期")
        self.suffix_date.setChecked(True)

        self.preview = QLabel("")
        self.preview.setObjectName("muted")
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet("font-size: 12px;")

        end_row = QHBoxLayout()
        end_row.setContentsMargins(0, 0, 0, 0)
        end_row.setSpacing(6)
        end_row.addWidget(self.by_count)
        end_row.addWidget(self.repeat_times)
        end_row.addWidget(QLabel("或截止"))
        end_row.addWidget(self.until)
        end_row.addStretch(1)
        interval_row = QHBoxLayout()
        interval_row.setContentsMargins(0, 0, 0, 0)
        interval_row.setSpacing(6)
        interval_row.addWidget(self.interval)
        interval_row.addWidget(QLabel("（仅「每隔 N 天」生效）"))
        interval_row.addStretch(1)

        form = QFormLayout()
        form.setSpacing(9)
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("任务", self.title)
        form.addRow("起始日期", self.start_on)
        form.addRow("当天时间", self.at_time)
        form.addRow("重复", self.mode)
        form.addRow("", interval_row)
        form.addRow("", self.weekday_row)
        form.addRow("范围", self._wrap(end_row))
        form.addRow("标签", self.tags)
        form.addRow("象限", self.quadrant)
        form.addRow("一段专注", self.focus)
        form.addRow("", self.suffix_date)
        form.addRow("", self.preview)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("生成任务")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        box = QVBoxLayout(self)
        box.setContentsMargins(18, 16, 18, 14)
        box.setSpacing(10)
        box.addLayout(form)
        box.addWidget(buttons)

        for widget in (self.title, self.start_on, self.at_time, self.interval,
                       self.repeat_times, self.until, self.tags, self.focus):
            for signal in ("textChanged", "dateChanged", "dateTimeChanged", "valueChanged"):
                if hasattr(widget, signal):
                    getattr(widget, signal).connect(self._preview)
                    break
        self.mode.currentIndexChanged.connect(self._preview)
        self.by_count.currentIndexChanged.connect(self._preview)
        self.quadrant.currentIndexChanged.connect(self._preview)
        self.suffix_date.toggled.connect(self._preview)
        self._sync_mode()
        self._sync_end()
        self._preview()

    def _wrap(self, layout: QHBoxLayout) -> QWidget:
        holder = QWidget()
        holder.setLayout(layout)
        return holder

    def _sync_mode(self) -> None:
        mode = self.mode.currentData()
        self.interval.setEnabled(mode == "every")
        self.weekday_row.setVisible(mode == "weekday")

    def _sync_end(self) -> None:
        by_count = self.by_count.currentIndex() == 0
        self.repeat_times.setEnabled(by_count)
        self.until.setEnabled(not by_count)

    def dates(self) -> list[datetime]:
        mode = self.mode.currentData()
        start = self.start_on.date().toPython()
        hour, minute = self.at_time.time().hour(), self.at_time.time().minute()
        if self.by_count.currentIndex() == 0:
            limit, end = self.repeat_times.value(), None
        else:
            until = self.until.date().toPython()
            limit, end = 60, until if until >= start else None
            if end is None:
                return []
        step = self.interval.value() if mode == "every" else 1
        chosen = [index for index, box in enumerate(self.weekday_boxes) if box.isChecked()]
        if mode == "weekday" and not chosen:
            return []
        picked: list[datetime] = []
        probe = start
        while len(picked) < limit and (end is None or probe <= end) and probe <= start + timedelta(days=400):
            hit = (mode in {"daily", "every"}
                   or (mode == "workday" and probe.weekday() < 5)
                   or (mode == "weekday" and probe.weekday() in chosen))
            if hit:
                picked.append(datetime(probe.year, probe.month, probe.day, hour, minute))
            probe += timedelta(days=step)
        return picked

    def rows(self) -> list[dict]:
        title = self.title.text().strip() or "未命名任务"
        tags = [tag for tag in self.tags.text().replace("#", " ").replace("，", " ").split() if tag]
        focus = self.focus.value()
        rows = []
        quadrant = self.quadrant.currentData()
        for stamp in self.dates():
            name = f"{title} {stamp:%m-%d}" if self.suffix_date.isChecked() else title
            rows.append({"title": name, "due": stamp, "tags": list(tags),
                         "focus_min": focus or None,
                         "quadrant": None if quadrant == UNSET else quadrant})
        return rows

    def _preview(self, *_args) -> None:
        stamps = self.dates()
        if not stamps:
            self.preview.setText("按当前条件生成不出日期：勾一下星期，或把范围调大。")
            return
        head = "、".join(f"{stamp:%m-%d %H:%M}" for stamp in stamps[:4])
        more = f" …共 {len(stamps)} 条" if len(stamps) > 4 else f" 共 {len(stamps)} 条"
        self.preview.setText(f"将生成：{head}{more}")

    def _accept(self) -> None:
        if self.quadrant.currentData() == UNSET:
            self.quadrant.setStyleSheet("border: 1px solid #e0574f;")
            self.preview.setText("先选一个象限（或选「不分象限（进任务池）」）再生成。")
            return
        if not self.dates():
            self._preview()
            return
        self.accept()
