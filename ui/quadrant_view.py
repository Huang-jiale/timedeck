from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from models import QUADRANTS, Task
from ui import theme
from ui.today_view import TASK_MIME, TaskRow

CELL_ACCENTS = {1: theme.DANGER, 2: theme.ACCENT, 3: theme.WARN, 4: theme.MUTED}


class QuadCell(QFrame):
    """一个象限格子：接受从别的格子拖进来的任务卡。"""

    dropped = Signal(object, str)
    focus = Signal(str)
    toggled = Signal(str, bool)
    advance = Signal(str)
    duration = Signal(str, int)
    edit = Signal(str)
    plan_today = Signal(str)
    archive = Signal(str)
    remove = Signal(str)

    def __init__(self, heading: str, hint: str, quadrant: int | None, accent: str, parent=None):
        super().__init__(parent)
        self.quadrant = quadrant
        self.accent = accent
        self._hot = False
        self.setObjectName("quadCell")
        self.setAcceptDrops(True)
        self.setMinimumHeight(150)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 10, 10)
        outer.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel(heading)
        title.setObjectName("quadTitle")
        title.setStyleSheet(f"color: {accent};")
        self.count = QLabel("0")
        self.count.setObjectName("muted")
        tip = QLabel(hint)
        tip.setObjectName("muted")
        tip.setStyleSheet("font-size: 11px;")
        head.addWidget(title)
        head.addWidget(self.count)
        head.addStretch(1)
        head.addWidget(tip)
        outer.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }")
        self.host = QWidget()
        self.body = QVBoxLayout(self.host)
        self.body.setContentsMargins(0, 0, 4, 0)
        self.body.setSpacing(6)
        self.scroll.setWidget(self.host)
        outer.addWidget(self.scroll, 1)
        self._empty = QLabel("把任务拖进来。")
        self._empty.setObjectName("muted")
        self._empty.setWordWrap(True)
        self._empty.setStyleSheet("font-size: 11px; padding: 6px 2px;")
        self.body.addWidget(self._empty)
        self.body.addStretch(1)
        self._rows: dict[str, TaskRow] = {}

    def clear_rows(self) -> None:
        self._rows = {}
        while self.body.count():
            item = self.body.takeAt(0)
            widget = item.widget()
            if widget and widget is not self._empty:
                widget.setParent(None)
                widget.deleteLater()

    def show_tasks(self, tasks: list[Task], now: datetime, active_id: str | None, store,
                   empty_hint: str | None = None) -> None:
        self.clear_rows()
        self.count.setText(str(len(tasks)))
        self._empty.setVisible(not tasks)
        if not tasks:
            self._empty.setText(empty_hint or "把任务拖进来。")
            self.body.addWidget(self._empty)
            self.body.addStretch(1)
            return
        default_min = int(store.settings["focus_min"])
        for task in tasks:
            row = TaskRow(task, now, active_id, self.host, compact=True,
                          default_min=default_min, today_button=True, draggable=True)
            row.setFixedHeight(58)
            for name in ("toggled", "focus", "advance", "duration", "edit", "plan_today", "archive", "remove"):
                getattr(row, name).connect(getattr(self, name))
            self._rows[task.id] = row
            self.body.addWidget(row)
        self.body.addStretch(1)

    def tick(self, now: datetime) -> None:
        for row in self._rows.values():
            row.tick(now)

    def dragEnterEvent(self, event):
        if event.mimeData().text().startswith(TASK_MIME):
            self._hot = True
            self._repolish()
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, _event):
        self._hot = False
        self._repolish()

    def dropEvent(self, event):
        self._hot = False
        self._repolish()
        text = event.mimeData().text()
        if not text.startswith(TASK_MIME):
            return event.ignore()
        event.acceptProposedAction()
        self.dropped.emit(self.quadrant, text[len(TASK_MIME):])

    def _repolish(self) -> None:
        self.setProperty("dropping", "true" if self._hot else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._hot:
            return
        painter = QPainter(self)
        painter.setPen(QPen(QColor(self.accent), 2, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 12, 12)


class QuadrantView(QWidget):
    """重要/紧急四象限：任务先写在这里，需要时一键「＋ 今日」排进今日计划。"""

    focus = Signal(str)
    toggled = Signal(str, bool)
    advance = Signal(str)
    duration = Signal(str, int)
    edit = Signal(str)
    plan_today = Signal(str)
    archive = Signal(str)
    remove = Signal(str)
    assigned = Signal(object, str)
    create = Signal()
    schedule = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._key: list = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索任务标题…")
        self.search.setObjectName("quick")
        self.search.setFixedWidth(220)
        self.search.textChanged.connect(lambda: self.refresh(datetime.now(), None))
        self.show_archived = QComboBox()
        self.show_archived.addItems(["隐藏归档", "显示归档"])
        self.show_archived.currentIndexChanged.connect(lambda: self.refresh(datetime.now(), None))
        new_btn = QPushButton("＋ 新建任务")
        new_btn.setObjectName("chipBtn")
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.clicked.connect(self.create)
        plan_btn = QPushButton("批量排期…")
        plan_btn.setObjectName("ghostBtn")
        plan_btn.setCursor(Qt.PointingHandCursor)
        plan_btn.setToolTip("按重复规则在未来一段时间里生成一串任务")
        plan_btn.clicked.connect(self.schedule)
        bar.addWidget(self.search)
        bar.addWidget(self.show_archived)
        bar.addStretch(1)
        bar.addWidget(plan_btn)
        bar.addWidget(new_btn)
        layout.addLayout(bar)

        grid = QGridLayout()
        grid.setSpacing(10)
        self.cells: dict[int | None, QuadCell] = {}
        for quadrant in (1, 2, 3, 4):
            heading, hint = QUADRANTS[quadrant]
            cell = QuadCell(f"Q{quadrant} · {heading}", hint, quadrant, CELL_ACCENTS[quadrant])
            cell.dropped.connect(self.assigned)
            self._wire(cell)
            self.cells[quadrant] = cell
            grid.addWidget(cell, (quadrant - 1) // 2, (quadrant - 1) % 2)
        layout.addLayout(grid, 4)

        pool = QuadCell("任务池 · 还没分象限", "拖到上面的格子里定象限", None, theme.MUTED)
        pool.dropped.connect(self.assigned)
        self._wire(pool)
        pool.setMinimumHeight(120)
        pool.setMaximumHeight(180)
        self.cells[None] = pool
        layout.addWidget(pool, 1)

        self.footer = QLabel("")
        self.footer.setObjectName("muted")
        self.footer.setStyleSheet("font-size: 11px; padding-bottom: 4px;")
        layout.addWidget(self.footer)

    def _wire(self, cell: QuadCell) -> None:
        for name in ("focus", "toggled", "advance", "duration", "edit", "plan_today", "archive", "remove"):
            getattr(cell, name).connect(getattr(self, name))

    def _partition(self, now: datetime) -> dict[int | None, list[Task]]:
        keyword = self.search.text().strip().lower()
        show_archived = self.show_archived.currentIndex() == 1
        groups: dict[int | None, list[Task]] = {key: [] for key in (1, 2, 3, 4, None)}
        done = 0
        for task in self.store.tasks:
            if task.archived and not show_archived:
                continue
            if task.done:
                done += 1
                continue
            if keyword and keyword not in task.title.lower():
                continue
            groups[task.quadrant].append(task)
        for tasks in groups.values():
            tasks.sort(key=lambda t: (t.due_dt or datetime.max, -t.priority))
        self._done_count = done
        return groups

    def refresh(self, now: datetime, active_task_id: str | None) -> None:
        groups = self._partition(now)
        key = [[(quadrant, tuple(_signature(task) for task in groups[quadrant]))
                for quadrant in (1, 2, 3, 4, None)], active_task_id,
               int(self.store.settings["focus_min"])]
        if key == self._key:
            for cell in self.cells.values():
                cell.tick(now)
            return
        self._key = key
        hint = ("这里还没有待办：任务都做完的话去「月历」回看，"
                "要加新的点右上「＋ 新建任务」或在下面输入框敲一句回车。") if not any(groups.values()) else None
        for quadrant, cell in self.cells.items():
            cell.show_tasks(groups[quadrant], now, active_task_id, self.store, hint)
        planned = sum(len(groups[q]) for q in (1, 2, 3, 4))
        self.footer.setText(f"已分象限 {planned} 条 · 池子里 {len(groups[None])} 条 · "
                            f"已完成 {getattr(self, '_done_count', 0)} 条在「月历」里回看")


def _signature(task: Task) -> tuple:
    return (task.id, task.title, task.due, task.start, task.focus_min, task.status,
            task.priority, tuple(task.tags), task.quadrant, task.archived, task.est_min, task.spent_min)
