from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from models import STATUS_DONE, Task, iso, new_id, parse_dt

KEEP_BACKUPS = 10
DEBOUNCE_MS = 2000


def seed_focus(tasks: list[Task]) -> list[dict]:
    """给演示任务补上对应的专注记录，否则月历的专注统计会是空的。"""
    log = []
    for task in tasks:
        if task.spent_min <= 0 or not task.due:
            continue
        start = parse_dt(task.due) - timedelta(minutes=task.spent_min)
        log.append({"id": new_id(), "task_id": task.id, "start": iso(start), "min": task.spent_min})
    return log


def seed_tasks() -> list[Task]:
    today = datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)
    # 标题, 截止, 标签, 优先级, 预估, 已用, 状态, 象限
    plan = [
        ("整理本周项目周报", today + timedelta(hours=2), ["工作"], 3, 90, 25, "doing", 1),
        ("英语学习：阅读 3 篇", today + timedelta(days=1), ["学习"], 2, 60, 0, "todo", 2),
        ("晨间拉伸 30 分钟", today - timedelta(hours=5), ["生活"], 1, 45, 45, "done", 2),
        ("预约牙医 + 交房租", today + timedelta(days=3), ["杂事"], 1, 15, 0, "todo", 3),
        ("复盘本周数据看板", today + timedelta(days=2), ["工作"], 2, 40, 0, "todo", 2),
        ("整理手机相册备份", today + timedelta(days=9), ["生活"], 1, 30, 0, "todo", 4),
        ("读完手上那本专业书", None, ["学习"], 2, 180, 0, "todo", None),
        ("给桌面工具写使用心得", None, ["杂事"], 1, 25, 0, "todo", None),
    ]
    tasks = []
    for title, due, tags, prio, est, spent, status, quadrant in plan:
        task = Task.create(title, due, tags, prio, est)
        task.spent_min = spent
        task.status = status
        task.quadrant = quadrant
        task.focus_min = min(est, 25)
        if status == STATUS_DONE:
            task.done_at = iso(due)
        tasks.append(task)
    return tasks


DEFAULT_SETTINGS = {
    "focus_min": 25,
    "break_min": 5,
    "busy_threshold": 8,
    "float_opacity": 0.92,
    "idle_opacity": 0.72,
    "sound_on_finish": True,
    "notify_on_finish": True,
}


class Store(QObject):
    changed = Signal(str)
    tasks_saved = Signal()

    def __init__(self, path: Path | str | None = None):
        super().__init__()
        self.path = Path(path) if path else Path.home() / ".timedeck" / "data.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.tasks: list[Task] = []
        self.focus_log: list[dict] = []
        self.settings: dict = dict(DEFAULT_SETTINGS)
        self.float_pos: dict | None = None
        self.float_visible: bool = True
        self.ui: dict = {}
        self._dirty = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.flush)
        self.load()

    @property
    def data_path(self) -> Path:
        return self.path

    @property
    def is_new(self) -> bool:
        return not self.path.exists()

    def load(self) -> None:
        if not self.path.exists():
            self.tasks = seed_tasks()
            self.focus_log = seed_focus(self.tasks)
            self._write()
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            self._rescue_corrupt()
            raw = {}
        self.tasks = [Task.from_dict(item) for item in raw.get("tasks", [])]
        self.focus_log = list(raw.get("focus_log", []))
        self.settings = {**DEFAULT_SETTINGS, **(raw.get("settings") or {})}
        self.float_pos = raw.get("float_pos")
        self.float_visible = bool(raw.get("float_visible", True))
        self.ui = raw.get("ui") or {}

    def _rescue_corrupt(self) -> None:
        broken = self.path.with_suffix(f".corrupt-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(self.path, broken)
        self.tasks = seed_tasks()
        self.focus_log = seed_focus(self.tasks)
        self._write()

    def _rotate_backups(self) -> None:
        for index in range(KEEP_BACKUPS - 1, 0, -1):
            older = self.path.with_name(f"data.json.bak{index}")
            newer = self.path.with_name(f"data.json.bak{index - 1}")
            if newer.exists():
                if older.exists():
                    older.unlink()
                newer.rename(older)
        first = self.path.with_name("data.json.bak0")
        if self.path.exists():
            shutil.copy2(self.path, first)

    def snapshot(self) -> dict:
        return {
            "version": 1,
            "updated": iso(datetime.now()),
            "tasks": [task.to_dict() for task in self.tasks],
            "focus_log": self.focus_log[-2000:],
            "settings": self.settings,
            "float_pos": self.float_pos,
            "float_visible": self.float_visible,
            "ui": self.ui,
        }

    def _write(self) -> None:
        self._rotate_backups()
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
        if self.path.exists():
            self.path.unlink()
        tmp.replace(self.path)

    def mark_dirty(self, reason: str = "change") -> None:
        self._dirty = True
        self.changed.emit(reason)
        self._timer.start(DEBOUNCE_MS)

    def flush(self) -> None:
        self._timer.stop()
        if self._dirty:
            self._write()
            self._dirty = False
        self.tasks_saved.emit()

    def export_to(self, target: Path | str) -> Path:
        Path(target).write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
        return Path(target)

    def import_from(self, source: Path | str) -> None:
        raw = json.loads(Path(source).read_text(encoding="utf-8"))
        self.tasks = [Task.from_dict(item) for item in raw.get("tasks", [])]
        self.focus_log = list(raw.get("focus_log", []))
        self.settings = {**DEFAULT_SETTINGS, **(raw.get("settings") or {})}
        self.mark_dirty("import")

    def get(self, task_id: str) -> Task | None:
        return next((task for task in self.tasks if task.id == task_id), None)

    def add(self, **fields) -> Task:
        task = Task.create(
            title=fields["title"],
            due=fields.get("due"),
            tags=fields.get("tags") or [],
            priority=fields.get("priority", 1),
            est_min=fields.get("est_min") or 30,
            start=fields.get("start"),
        )
        for key in ("focus_min", "quadrant", "status"):
            if fields.get(key) is not None:
                setattr(task, key, fields[key])
        self.tasks.append(task)
        self.mark_dirty("add")
        return task

    def add_many(self, rows: list[dict]) -> list[Task]:
        created = [self.add(**row) for row in rows]
        self.flush()
        return created

    def update(self, task_id: str, **fields) -> None:
        task = self.get(task_id)
        if not task:
            return
        for key, value in fields.items():
            if key in {"due", "start"} and isinstance(value, datetime):
                value = iso(value)
            if hasattr(task, key):
                setattr(task, key, value)
        self.mark_dirty("update")

    def set_status(self, task_id: str, status: str) -> None:
        task = self.get(task_id)
        if not task:
            return
        task.status = status
        task.done_at = iso(datetime.now()) if status == STATUS_DONE else None
        self.mark_dirty("status")

    def remove(self, task_id: str) -> None:
        self.tasks = [task for task in self.tasks if task.id != task_id]
        self.focus_log = [row for row in self.focus_log if row.get("task_id") != task_id]
        self.mark_dirty("remove")

    def archive_many(self, task_ids: set[str]) -> int:
        count = 0
        for task in self.tasks:
            if task.id in task_ids:
                task.archived = True
                count += 1
        if count:
            self.mark_dirty("archive")
        return count

    def log_focus(self, task_id: str | None, minutes: int, start: datetime) -> None:
        if minutes <= 0:
            return
        self.focus_log.append({
            "id": new_id(),
            "task_id": task_id,
            "start": iso(start),
            "min": minutes,
        })
        task = self.get(task_id) if task_id else None
        if task:
            task.spent_min += minutes
        self.mark_dirty("focus")

    def active_tasks(self) -> list[Task]:
        return [task for task in self.tasks if not task.archived]

    def day_summary(self, day) -> dict:
        from models import day_span
        start, end = day_span(day)
        pool = [task for task in self.active_tasks() if task.due_dt and start <= task.due_dt < end]
        done = [task for task in pool if task.done]
        focus_min = 0
        for row in self.focus_log:
            stamp = row.get("start")
            if not stamp:
                continue
            try:
                when = datetime.fromisoformat(stamp)
            except ValueError:
                continue
            if start <= when < end:
                focus_min += int(row.get("min") or 0)
        return {"total": len(pool), "done": len(done), "focus_min": focus_min, "tasks": pool}
