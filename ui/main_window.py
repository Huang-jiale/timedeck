from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from models import STATUS_DOING, parse_quick
from ui import theme
from ui.calendar_view import CalendarView
from ui.quadrant_view import QuadrantView
from ui.schedule_dialog import ScheduleDialog
from ui.settings_dialog import SettingsDialog
from ui.task_dialog import TaskDialog
from ui.today_view import TodayView
from ui.timer import MODE_BREAK, MODE_FOCUS, MODE_IDLE, FocusTimer

NAV = [("今日", "today"), ("月历", "calendar"), ("四象限", "quadrant")]


class TimerCapsule(QFrame):
    def __init__(self, timer: FocusTimer, parent=None):
        super().__init__(parent)
        self.timer = timer
        self.setObjectName("card")
        self.setFixedHeight(46)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 8, 6)
        layout.setSpacing(8)
        self.state = QLabel("未开始")
        self.state.setStyleSheet(f"color: {theme.TEXT}; font-weight: 600;")
        self.clock = QLabel("--:--")
        self.clock.setStyleSheet(f"color: {theme.ACCENT}; font-size: 17px; font-weight: 700;")
        self.pause = QPushButton("暂停")
        self.skip = QPushButton("跳过")
        self.stop = QPushButton("结束")
        for btn in (self.pause, self.skip, self.stop):
            btn.setObjectName("ghostBtn")
            btn.setFixedHeight(28)
            btn.setMinimumWidth(46)
            btn.setCursor(Qt.PointingHandCursor)
        self.pause.clicked.connect(timer.toggle_pause)
        self.skip.clicked.connect(timer.skip)
        self.stop.clicked.connect(lambda: timer.stop(commit=False))
        layout.addWidget(self.state)
        layout.addWidget(self.clock)
        layout.addWidget(self.pause)
        layout.addWidget(self.skip)
        layout.addWidget(self.stop)
        timer.ticked.connect(self.sync)
        timer.mode_changed.connect(self.sync)
        self.sync()

    def sync(self, *_args) -> None:
        running = self.timer.mode != MODE_IDLE
        self.state.setText(self.timer.label())
        self.clock.setText(self.timer.clock_text())
        self.pause.setText("继续" if self.timer.paused else "暂停")
        for btn in (self.pause, self.skip, self.stop):
            btn.setVisible(running)
        self.clock.setStyleSheet(
            f"color: {theme.DONE if self.timer.mode == MODE_BREAK else theme.ACCENT};"
            "font-size: 17px; font-weight: 700;"
        )


class MainWindow(QWidget):
    request_quit = Signal()
    focus_task = Signal(str)
    float_visibility = Signal(bool)

    def __init__(self, store, timer: FocusTimer, parent=None):
        super().__init__(parent)
        self.store = store
        self.timer = timer
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._sidebar())
        right = QVBoxLayout()
        right.setContentsMargins(18, 14, 18, 0)
        right.setSpacing(10)
        right.addLayout(self._topbar())
        self.stack = QStackedWidget()
        self.today_view = TodayView(store)
        self.calendar_view = CalendarView(store)
        self.quadrant_view = QuadrantView(store)
        for widget in (self.today_view, self.calendar_view, self.quadrant_view):
            self.stack.addWidget(widget)
        right.addWidget(self.stack, 1)
        self.quick_host = self._quick_bar()
        right.addWidget(self.quick_host)
        wrapper = QWidget()
        wrapper.setLayout(right)
        body.addWidget(wrapper, 1)
        root.addLayout(body, 1)

        self.nav_buttons: dict[str, QPushButton] = {}
        self.show_view("today")

        for view in (self.today_view, self.quadrant_view):
            view.toggled.connect(self._toggle_done)
            view.focus.connect(self._start_focus)
            view.advance.connect(self._advance)
            view.duration.connect(self._set_duration)
            view.edit.connect(self._edit_task)
            view.plan_today.connect(self._plan_today)
            view.archive.connect(self._archive_task)
            view.remove.connect(self._remove_task)
        self.calendar_view.focus.connect(self._start_focus)
        self.calendar_view.edit.connect(self._edit_task)
        self.quadrant_view.assigned.connect(self._assign)
        self.quadrant_view.create.connect(lambda: self._edit_task(None))
        self.quadrant_view.schedule.connect(self._open_schedule)
        self.focus_task.connect(self._start_focus)

        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self.refresh)
        self._clock.start()
        store.changed.connect(self._store_changed)

    def _store_changed(self, _reason: str = "") -> None:
        self._rebuild_tags()
        self.refresh()

    def _sidebar(self) -> QWidget:
        sidebar = QFrame()
        self.sidebar = sidebar
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(176)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 20, 0, 16)
        layout.setSpacing(2)
        title = QLabel("TimeDeck")
        title.setObjectName("sidebarTitle")
        hint = QLabel("任务台")
        hint.setObjectName("sidebarHint")
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(14)
        self.nav_buttons = {}
        for label, key in NAV:
            button = QPushButton(label)
            button.setObjectName("navBtn")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self.show_view(k))
            layout.addWidget(button)
            self.nav_buttons[key] = button
        layout.addSpacing(12)
        tags_title = QLabel("标签")
        tags_title.setObjectName("sidebarHint")
        layout.addWidget(tags_title)
        self.tag_host = QVBoxLayout()
        self.tag_host.setSpacing(0)
        layout.addLayout(self.tag_host)
        layout.addStretch(1)
        settings = QPushButton("设置")
        settings.setObjectName("navBtn")
        settings.clicked.connect(self.open_settings)
        layout.addWidget(settings)
        return sidebar

    def _rebuild_tags(self) -> None:
        while self.tag_host.count():
            item = self.tag_host.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        counts: dict[str, int] = {}
        for task in self.store.active_tasks():
            for tag in task.tags or ["未分类"]:
                counts[tag] = counts.get(tag, 0) + 1
        for tag, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            button = QPushButton(f"{tag}  ·  {count}", self.sidebar)
            button.setObjectName("sideTag")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, t=tag: self.show_tag(t))
            self.tag_host.addWidget(button)

    def show_tag(self, tag: str) -> None:
        self.show_view("quadrant")
        self.quadrant_view.search.setText(tag)
        self.quadrant_view.refresh(datetime.now(), None)

    def _topbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.view_title = QLabel("今日")
        self.view_title.setObjectName("viewTitle")
        self.date_label = QLabel()
        self.date_label.setObjectName("muted")
        self.capsule = TimerCapsule(self.timer)
        self.float_toggle = QPushButton("悬浮窗")
        self.float_toggle.setObjectName("ghostBtn")
        self.float_toggle.setCheckable(True)
        self.float_toggle.setChecked(True)
        self.float_toggle.toggled.connect(self._on_float_toggled)
        self.float_toggle.setText("悬浮窗 · 开" if self.float_toggle.isChecked() else "悬浮窗 · 关")
        bar.addWidget(self.view_title)
        bar.addWidget(self.date_label)
        bar.addStretch(1)
        bar.addWidget(self.capsule)
        bar.addWidget(self.float_toggle)
        return bar

    def _on_float_toggled(self, on: bool) -> None:
        self.float_toggle.setText("悬浮窗 · 开" if on else "悬浮窗 · 关")
        self.float_visibility.emit(on)

    def _quick_bar(self) -> QWidget:
        box = QVBoxLayout()
        box.setSpacing(4)
        self.quick = QLineEdit()
        self.quick.setObjectName("quick")
        self.quick.setPlaceholderText("快速添加：明天18:00 写项目周报 #工作 !3 90min   （回车保存）")
        self.quick.returnPressed.connect(self._add_quick)
        self.new_task = QPushButton("＋ 新建任务")
        self.new_task.setObjectName("ghostBtn")
        self.new_task.setFixedHeight(38)
        self.new_task.setCursor(Qt.PointingHandCursor)
        self.new_task.setToolTip("逐项填写开始时间、专注时长、标签等")
        self.new_task.clicked.connect(lambda: self._edit_task(None))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.quick, 1)
        row.addWidget(self.new_task)
        tip = QLabel("支持：今天 / 明天 / 后天 / 周五 / 9-28 / 18:00 ；#标签 ；!1-!3 优先级 ；90min 或 1.5h 预估时长")
        tip.setObjectName("muted")
        tip.setStyleSheet("font-size: 11px; padding-bottom: 8px;")
        box.addLayout(row)
        box.addWidget(tip)
        host = QWidget()
        host.setLayout(box)
        return host

    def _add_quick(self) -> None:
        text = self.quick.text().strip()
        if not text:
            return
        fields = parse_quick(text)
        if not fields["title"]:
            return
        self.store.add(**fields)
        self.quick.clear()
        self.refresh()

    def show_view(self, key: str) -> None:
        index = {"today": 0, "calendar": 1, "quadrant": 2}[key]
        self.stack.setCurrentIndex(index)
        self.view_title.setText({"today": "今日", "calendar": "月历工作视图", "quadrant": "时间管理四象限"}[key])
        self.quick_host.setVisible(key != "calendar")
        for name, button in self.nav_buttons.items():
            button.setProperty("active", "true" if name == key else "false")
            button.style().unpolish(button)
            button.style().polish(button)
        self._rebuild_tags()
        self.refresh()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.store, self.window())
        if dialog.exec():
            dialog.apply()
        self.calendar_view.refresh()
        self.refresh()

    def _start_focus(self, task_id: str) -> None:
        task = self.store.get(task_id)
        if task and task.status != STATUS_DOING:
            self.store.update(task_id, status=STATUS_DOING)
        self.timer.start_focus(task_id)
        self.refresh()

    def _advance(self, task_id: str) -> None:
        self.store.update(task_id, status=STATUS_DOING)
        self.refresh()

    def _set_duration(self, task_id: str, minutes: int) -> None:
        self.store.update(task_id, focus_min=minutes)
        self.refresh()

    def _edit_task(self, task_id: str | None) -> None:
        task = self.store.get(task_id) if task_id else None
        dialog = TaskDialog(self.store, task, parent=self.window())
        if dialog.exec() != TaskDialog.Accept:
            return
        if dialog.delete_requested:
            self.refresh()
            return
        fields = dialog.fields()
        if task:
            self.store.update(task.id, **fields)
        else:
            self.store.add(**fields)
        self.refresh()

    def _plan_today(self, task_id: str) -> None:
        task = self.store.get(task_id)
        if not task:
            return
        now = datetime.now()
        keep = task.due_dt or task.start_dt
        when = now.replace(hour=keep.hour if keep else 18, minute=keep.minute if keep else 0,
                           second=0, microsecond=0)
        self.store.update(task_id, due=when)
        self.refresh()

    def _assign(self, quadrant, task_id: str) -> None:
        self.store.update(task_id, quadrant=quadrant)
        self.refresh()

    def _archive_task(self, task_id: str) -> None:
        task = self.store.get(task_id)
        if task:
            self.store.update(task_id, archived=not task.archived)
        self.refresh()

    def _remove_task(self, task_id: str) -> None:
        self.store.remove(task_id)
        self.refresh()

    def _open_schedule(self) -> None:
        dialog = ScheduleDialog(self.store, self.window())
        if dialog.exec() == ScheduleDialog.Accept:
            self.store.add_many(dialog.rows())
            self.refresh()

    def _toggle_done(self, task_id: str, done: bool) -> None:
        if done and self.timer.task_id == task_id and self.timer.mode == MODE_FOCUS:
            self.timer.stop(commit=True)
        self.store.set_status(task_id, "done" if done else "todo")
        self.refresh()

    def refresh(self) -> None:
        now = datetime.now()
        self.date_label.setText(f"{now:%Y年%m月%d日 %H:%M}")
        active = self.timer.task_id if self.timer.mode == MODE_FOCUS else None
        self.capsule.sync()
        index = self.stack.currentIndex()
        if index == 1:
            self.calendar_view.refresh()
        elif index == 2:
            self.quadrant_view.refresh(now, active)
        else:
            self.today_view.refresh(now, active)
