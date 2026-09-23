from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from models import STATUS_DONE, hours_text
from ui import theme

COLUMNS = ["状态", "任务", "标签", "截止", "剩余", "预估", "已用", "优先级"]
STATUS_TEXT = {"todo": "待办", "doing": "进行中", "done": "已完成"}


class AllView(QWidget):
    focus = Signal(str)
    removed = Signal(str)
    toggled = Signal(str, bool)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索任务标题…")
        self.search.setObjectName("quick")
        self.search.setFixedWidth(240)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["全部状态", "待办", "进行中", "已完成"])
        self.tag_filter = QComboBox()
        self.show_archived = QComboBox()
        self.show_archived.addItems(["隐藏归档", "显示归档"])
        for widget in (self.status_filter, self.tag_filter, self.show_archived):
            widget.setMinimumWidth(96)
            widget.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)
        archive = QPushButton("归档所选")
        archive.setObjectName("chipBtn")
        archive.clicked.connect(self.archive_selected)
        bar.addWidget(self.search)
        bar.addWidget(self.status_filter)
        bar.addWidget(self.tag_filter)
        bar.addWidget(self.show_archived)
        bar.addStretch(1)
        bar.addWidget(archive)
        layout.addLayout(bar)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table, 1)

        self.footer = QLabel("")
        self.footer.setObjectName("muted")
        layout.addWidget(self.footer)
        self.refresh()

    def _on_double_click(self, item: QTableWidgetItem) -> None:
        row = item.row()
        task_id = self.table.item(row, 0).data(Qt.UserRole)
        task = self.store.get(task_id)
        if task:
            self.toggled.emit(task.id, not task.done)

    def _rows(self):
        keyword = self.search.text().strip().lower()
        status_choice = ("", "todo", "doing", "done")[self.status_filter.currentIndex()]
        tag_choice = self.tag_filter.currentText()
        archived = self.show_archived.currentIndex() == 1
        now = datetime.now()
        found = []
        for task in self.store.tasks:
            if not archived and task.archived:
                continue
            if status_choice and task.status != status_choice:
                continue
            if tag_choice != "全部标签" and tag_choice not in task.tags:
                continue
            if keyword and keyword not in task.title.lower():
                continue
            found.append((task, now))
        return found

    def refresh(self) -> None:
        tags = sorted({tag for task in self.store.tasks for tag in task.tags})
        current = self.tag_filter.currentText()
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItems(["全部标签", *tags])
        self.tag_filter.setCurrentText(current if current in tags else "全部标签")
        self.tag_filter.blockSignals(False)

        rows = self._rows()
        rows.sort(key=lambda pair: (pair[0].done, pair[0].due_dt or datetime.max, -pair[0].priority))
        self.table.setRowCount(len(rows))
        for index, (task, now) in enumerate(rows):
            values = [
                STATUS_TEXT.get(task.status, task.status) + ("（归档）" if task.archived else ""),
                task.title,
                "/".join(task.tags) or "—",
                f"{task.due_dt:%m-%d %H:%M}" if task.due_dt else "—",
                task.remaining_text(now) or "—",
                hours_text(task.est_min),
                hours_text(task.spent_min),
                {1: "低", 2: "中", 3: "高"}.get(task.priority, "中"),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, task.id)
                if column in {0, 2, 4}:
                    item.setTextAlignment(Qt.AlignCenter)
                if column == 0:
                    item.setForeground(QColor(theme.DONE if task.done else theme.MUTED))
                if column == 4:
                    if task.done:
                        item.setForeground(QColor(theme.DONE))
                    elif task.is_overdue(now):
                        item.setForeground(QColor(theme.DANGER))
                        item.setFont(QFont(theme.FONT, 9, QFont.Bold))
                    elif task.due_dt:
                        item.setForeground(QColor(theme.WARN))
                if column == 7:
                    item.setForeground(QColor(theme.priority_color(task.priority)))
                if task.done:
                    item.setBackground(QColor("#f6fbf7"))
                self.table.setItem(index, column, item)
        total = len(rows)
        finished = sum(1 for task, _ in rows if task.status == STATUS_DONE)
        self.footer.setText(f"{total} 条 · 已完成 {finished} · 双击行可切换完成状态")

    def select_tag(self, tag: str) -> None:
        if self.tag_filter.findText(tag) >= 0:
            self.tag_filter.setCurrentText(tag)
        else:
            self.tag_filter.setCurrentIndex(0)
        self.refresh()

    def archive_selected(self) -> None:
        ids = {self.table.item(row, 0).data(Qt.UserRole) for row in {i.row() for i in self.table.selectedItems()}}
        ids.discard(None)
        if ids:
            self.store.archive_many(ids)
            self.refresh()
