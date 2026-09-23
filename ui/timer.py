from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

MODE_IDLE = "idle"
MODE_FOCUS = "focus"
MODE_BREAK = "break"


class FocusTimer(QObject):
    """单实例专注计时器：一段计时只绑一个任务，休息段不计入任务耗时。"""

    ticked = Signal()
    mode_changed = Signal(str)
    session_done = Signal(str, int)

    def __init__(self, store, parent: QObject | None = None):
        super().__init__(parent)
        self.store = store
        self.mode = MODE_IDLE
        self.paused = True
        self.task_id: str | None = None
        self.total_sec = 0
        self._left = 0
        self._deadline = 0.0
        self._started_at: datetime | None = None
        self._ticker = QTimer(self)
        self._ticker.setInterval(250)
        self._ticker.timeout.connect(self._on_tick)

    @property
    def running(self) -> bool:
        return self.mode != MODE_IDLE and not self.paused

    @property
    def remaining(self) -> int:
        if self.mode == MODE_IDLE:
            return 0
        return int(round(self._left)) if self.paused else max(0, self._deadline - time.monotonic())

    @property
    def progress(self) -> float:
        if not self.total_sec:
            return 0.0
        used = self.total_sec - self.remaining
        return min(max(used / self.total_sec, 0.0), 1.0)

    def clock_text(self) -> str:
        if self.mode == MODE_IDLE:
            return "--:--"
        seconds = int(self.remaining)
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def label(self) -> str:
        if self.mode == MODE_IDLE:
            return "未开始"
        head = "专注" if self.mode == MODE_FOCUS else "休息"
        return f"{head}·暂停" if self.paused else head

    def start_focus(self, task_id: str | None = None, minutes: int | None = None) -> None:
        if self.mode == MODE_FOCUS:
            self._commit()
        if minutes is None:
            task = self.store.get(task_id) if task_id else None
            minutes = getattr(task, "focus_min", None) or int(self.store.settings["focus_min"])
        self._begin(MODE_FOCUS, int(minutes) * 60, task_id)

    def start_break(self) -> None:
        if self.mode == MODE_FOCUS:
            self._commit()
        self._begin(MODE_BREAK, int(self.store.settings["break_min"]) * 60, None)

    def _begin(self, mode: str, seconds: int, task_id: str | None) -> None:
        self.mode = mode
        self.task_id = task_id
        self.total_sec = seconds
        self._left = seconds
        self._deadline = time.monotonic() + seconds
        self._started_at = datetime.now()
        self.paused = False
        self._ticker.start()
        self.mode_changed.emit(mode)

    def toggle_pause(self) -> None:
        if self.mode == MODE_IDLE:
            return
        if self.paused:
            self._deadline = time.monotonic() + self._left
            self.paused = False
            self._ticker.start()
        else:
            self._left = max(0.0, self._deadline - time.monotonic())
            self.paused = True
            self._ticker.stop()
        self.mode_changed.emit(self.mode)

    def stop(self, commit: bool = True) -> None:
        if self.mode == MODE_FOCUS and commit:
            self._commit()
        self._reset()

    def skip(self) -> None:
        if self.mode == MODE_FOCUS:
            self._commit()
            if int(self.store.settings["break_min"]) > 0:
                self._begin(MODE_BREAK, int(self.store.settings["break_min"]) * 60, None)
            else:
                self._reset()
            return
        self._reset()

    def _commit(self) -> None:
        elapsed = self.total_sec - self.remaining
        minutes = int(elapsed // 60)
        if minutes >= 1 and self._started_at:
            self.store.log_focus(self.task_id, minutes, self._started_at)

    def _reset(self) -> None:
        self._ticker.stop()
        self.mode = MODE_IDLE
        self.paused = True
        self.task_id = None
        self.total_sec = 0
        self._left = 0
        self._started_at = None
        self.mode_changed.emit(self.mode)

    def _on_tick(self) -> None:
        if self.paused or self.mode == MODE_IDLE:
            return
        left = self._deadline - time.monotonic()
        self._left = max(0.0, left)
        self.ticked.emit()
        if left <= 0:
            finished = self.mode
            minutes = int(self.total_sec // 60)
            if finished == MODE_FOCUS:
                self._commit()
                if int(self.store.settings["break_min"]) > 0:
                    self._begin(MODE_BREAK, int(self.store.settings["break_min"]) * 60, None)
                    self.session_done.emit(finished, minutes)
                    return
            self._reset()
            self.session_done.emit(finished, minutes)
