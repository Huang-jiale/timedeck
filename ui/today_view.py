from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QPoint, QRect, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QInputDialog, QLabel, QMenu, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from models import STATUS_DOING, STATUS_TODO, Task, hours_text
from ui import theme

FOCUS_PRESETS = (15, 25, 45, 60)
TASK_MIME = "timedeck/task/"


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self._full = text
        self.setMinimumWidth(1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def setText(self, text: str) -> None:
        self._full = text
        self._render()

    def resizeEvent(self, event):
        self._render()
        super().resizeEvent(event)

    def _render(self):
        metrics = self.fontMetrics()
        room = max(self.width() - 2, 24)
        super().setText(metrics.elidedText(self._full, Qt.ElideRight, room))


class CheckCircle(QFrame):
    """完成勾选圈：未完成任务描边，已完成实心打勾。"""

    clicked = Signal()

    def __init__(self, checked: bool, accent: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.checked = checked
        self.accent = accent
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.checked:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.DONE))
            painter.drawEllipse(QRect(0, 0, 20, 20))
            pen = QPen(QColor("#ffffff"))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(5, 10, 9, 14)
            painter.drawLine(9, 14, 15, 6)
        else:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(self.accent), 2))
            painter.drawEllipse(QRect(1, 1, 18, 18))


class TaskRow(QFrame):
    toggled = Signal(str, bool)
    focus = Signal(str)
    advance = Signal(str)
    duration = Signal(str, int)
    edit = Signal(str)
    plan_today = Signal(str)
    archive = Signal(str)
    remove = Signal(str)
    dragged = Signal(str)

    def __init__(self, task: Task, now: datetime, active_task_id: str | None, parent=None,
                 compact: bool = False, default_min: int = 25, today_button: bool = False,
                 draggable: bool = False):
        super().__init__(parent)
        self.task = task
        self.compact = compact
        self.draggable = draggable
        self._press_at: QPoint | None = None
        self.default_min = default_min
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(68)
        self.setToolTip("双击编辑，右键更多操作")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        circle = CheckCircle(task.done, theme.priority_color(task.priority))
        circle.clicked.connect(lambda: self.toggled.emit(task.id, not task.done))
        layout.addWidget(circle)

        middle = QVBoxLayout()
        middle.setSpacing(3)
        title = ElidedLabel(task.title)
        title.setObjectName("taskTitle")
        title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        if task.done:
            font = QFont(title.font())
            font.setStrikeOut(True)
            title.setFont(font)
            title.setStyleSheet(f"color: {theme.MUTED};")
        middle.addWidget(title)

        self.meta = ElidedLabel(" · ".join(self._meta_parts(now)))
        self.meta.setObjectName("taskMeta")
        self._paint_meta(now)
        middle.addWidget(self.meta)
        layout.addLayout(middle, 1)

        for tag in task.tags[:1 if self.compact else 2]:
            chip = QLabel(tag)
            chip.setObjectName("chip")
            chip.setFixedHeight(20)
            chip.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            chip.setStyleSheet(f"background: {theme.tag_color(tag)};")
            layout.addWidget(chip, 0, Qt.AlignVCenter)

        if task.id == active_task_id:
            button = QPushButton("● 计时中")
            button.setObjectName("chipBtn")
            button.setStyleSheet("background: #dcecdf; color: #1f7a3f;")
            layout.addWidget(button, 0, Qt.AlignVCenter)
        elif not task.done:
            if task.status == STATUS_TODO and not self.compact:
                start = QPushButton("开始")
                start.setObjectName("ghostBtn")
                start.setToolTip("标记为进行中")
                start.clicked.connect(lambda: self.advance.emit(task.id))
                layout.addWidget(start, 0, Qt.AlignVCenter)
            if not self.compact:
                minutes = task.focus_min or self.default_min
                chip = QPushButton(f"{minutes} 分 ▾")
                chip.setObjectName("ghostBtn")
                chip.setToolTip("给这个任务选一段专注时长")
                chip.clicked.connect(lambda: self._pick_duration(chip))
                layout.addWidget(chip, 0, Qt.AlignVCenter)
            if today_button:
                plan = QPushButton("＋ 今日")
                plan.setObjectName("chipBtn")
                plan.setToolTip("截止日改到今天，进入今日计划")
                plan.clicked.connect(lambda: self.plan_today.emit(task.id))
                layout.addWidget(plan, 0, Qt.AlignVCenter)
            focus = QPushButton("▶ 专注")
            focus.setObjectName("chipBtn")
            focus.clicked.connect(lambda: self.focus.emit(task.id))
            layout.addWidget(focus, 0, Qt.AlignVCenter)
        for widget in self.findChildren(QPushButton):
            widget.setFixedHeight(30)
            widget.setCursor(Qt.PointingHandCursor)

    def _pick_duration(self, anchor: QPushButton) -> None:
        current = self.task.focus_min or self.default_min
        menu = QMenu(anchor)
        for minutes in FOCUS_PRESETS:
            mark = "●" if minutes == current else "○"
            action = menu.addAction(f"{mark} {minutes} 分钟")
            action.triggered.connect(lambda _=False, m=minutes: self.duration.emit(self.task.id, m))
        menu.addSeparator()
        menu.addAction(f"自定义…（当前 {current} 分钟）").triggered.connect(self._pick_custom)
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _pick_custom(self) -> None:
        minutes, ok = QInputDialog.getInt(self, "自定义专注时长", f"「{self.task.title}」一段专注（分钟）",
                                          self.task.focus_min or self.default_min, 5, 240)
        if ok:
            self.duration.emit(self.task.id, minutes)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.edit.emit(self.task.id)

    def mousePressEvent(self, event):
        self._press_at = event.position().toPoint() if event.button() == Qt.LeftButton else None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self.draggable or self._press_at is None or not (event.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(event)
        if (event.position().toPoint() - self._press_at).manhattanLength() < 8:
            return super().mouseMoveEvent(event)
        self._press_at = None
        data = QMimeData()
        data.setText(TASK_MIME + self.task.id)
        drag = QDrag(self)
        drag.setMimeData(data)
        drag.exec(Qt.MoveAction)

    def contextMenuEvent(self, event):
        task = self.task
        menu = QMenu(self)
        menu.addAction("编辑任务…", lambda: self.edit.emit(task.id))
        menu.addAction("重新打开" if task.done else "标记完成",
                       lambda: self.toggled.emit(task.id, not task.done))
        menu.addAction("排到今天", lambda: self.plan_today.emit(task.id))
        menu.addSeparator()
        menu.addAction("取消归档" if task.archived else "归档", lambda: self.archive.emit(task.id))
        menu.addAction("删除", lambda: self.remove.emit(task.id))
        menu.exec(event.globalPos())

    def _meta_parts(self, now: datetime) -> list[str]:
        remaining = self.task.remaining_text(now)
        parts = [remaining or ("无截止" if not self.task.done else "已完成")]
        if self.compact:
            if self.task.status == STATUS_DOING:
                parts.append("进行中")
            return parts
        parts.append(f"已用 {hours_text(self.task.spent_min)}")
        if self.task.status == STATUS_DOING:
            parts.append("进行中")
        return parts

    def _paint_meta(self, now: datetime) -> None:
        if self.task.is_overdue(now):
            self.meta.setStyleSheet(f"color: {theme.DANGER}; font-weight: 600;")
        elif self.task.remaining_text(now):
            self.meta.setStyleSheet(f"color: {theme.WARN};")
        else:
            self.meta.setStyleSheet(f"color: {theme.MUTED};")

    def tick(self, now: datetime) -> None:
        self.meta.setText(" · ".join(self._meta_parts(now)))
        self._paint_meta(now)


class TodayView(QWidget):
    toggled = Signal(str, bool)
    focus = Signal(str)
    advance = Signal(str)
    duration = Signal(str, int)
    edit = Signal(str)
    plan_today = Signal(str)
    archive = Signal(str)
    remove = Signal(str)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._rows: dict[str, TaskRow] = {}
        self._key: list = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.host = QWidget()
        self.body = QVBoxLayout(self.host)
        self.body.setContentsMargins(0, 4, 12, 0)
        self.body.setSpacing(8)
        self.scroll.setWidget(self.host)
        outer.addWidget(self.scroll)
        self.summary: QLabel | None = None
        self.refresh(datetime.now(), None)

    def _clear(self):
        self._rows = {}
        while self.body.count():
            item = self.body.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

    def _header(self, text: str, accent: str):
        label = QLabel(text, self.host)
        label.setStyleSheet(f"color: {accent}; font-size: 12px; font-weight: 700; padding-top: 8px;")
        self.body.addWidget(label)

    def _group(self, tasks: list[Task], now: datetime, active_id: str | None):
        default_min = int(self.store.settings["focus_min"])
        for task in sorted(tasks, key=lambda t: (t.due_dt or datetime.max, -t.priority)):
            row = TaskRow(task, now, active_id, self.host, default_min=default_min)
            row.toggled.connect(self.toggled)
            row.focus.connect(self.focus)
            row.advance.connect(self.advance)
            row.duration.connect(self.duration)
            row.edit.connect(self.edit)
            row.plan_today.connect(self.plan_today)
            row.archive.connect(self.archive)
            row.remove.connect(self.remove)
            self._rows[task.id] = row
            self.body.addWidget(row)

    def _buckets(self, now: datetime) -> list[tuple[str, list[Task]]]:
        pool = [task for task in self.store.active_tasks() if not task.done]
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = start_of_day + timedelta(days=8)
        return [
            ("已逾期", [t for t in pool if t.is_overdue(now)]),
            ("今天要做", [t for t in pool if t.due_dt
                       and start_of_day <= t.due_dt < start_of_day + timedelta(days=1) and not t.is_overdue(now)]),
            ("接下来一周", [t for t in pool if t.due_dt
                       and start_of_day + timedelta(days=1) <= t.due_dt < week_end]),
            ("待安排", [t for t in pool if t.due_dt is None]),
        ]

    def _summary_text(self, now: datetime, buckets: list[tuple[str, list[Task]]]) -> str:
        counts = {name: len(tasks) for name, tasks in buckets}
        text = (f"{now:%m月%d日 %H:%M} · 逾期 {counts.get('已逾期', 0)} · 今天 {counts.get('今天要做', 0)}"
                f" · 接下来一周 {counts.get('接下来一周', 0)}")
        if not buckets:
            text += "\n今天没有安排。用下方输入框加一条，支持这种写法：\n" \
                    "明天18:00 写项目周报 #工作 !3 90min"
        else:
            text += " · 已完成的去「月历」看"
        return text

    def refresh(self, now: datetime, active_task_id: str | None) -> None:
        buckets = [(name, tasks) for name, tasks in self._buckets(now) if tasks]
        key = [[(name, tuple(_signature(task) for task in tasks)) for name, tasks in buckets],
               active_task_id, int(self.store.settings["focus_min"])]
        if key == self._key:
            if self.summary is not None:
                self.summary.setText(self._summary_text(now, buckets))
            for _, tasks in buckets:
                for task in tasks:
                    self._rows[task.id].tick(now)
            return
        self._clear()
        self._key = key
        self.summary = QLabel(self._summary_text(now, buckets), self.host)
        self.summary.setObjectName("muted")
        self.summary.setWordWrap(True)
        self.body.addWidget(self.summary)
        accents = {"已逾期": theme.DANGER, "今天要做": theme.ACCENT}
        for name, tasks in buckets:
            self._header(f"{name} · {len(tasks)}", accents.get(name, theme.MUTED))
            self._group(tasks, now, active_task_id)
        self.body.addStretch(1)


def _signature(task: Task) -> tuple:
    """决定这一行要不要整只重建：文本/时长/标签/状态变了就重建，只有剩余时间变了走 tick。"""
    return (task.id, task.title, task.due, task.focus_min, task.status, task.priority,
            tuple(task.tags), task.est_min, task.spent_min, task.quadrant)
