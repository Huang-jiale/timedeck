"""离屏渲染界面并导出 PNG，用于人工核对布局。用法：python shot.py [输出目录]"""
from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from main import TimeDeck
from store import Store
from ui import theme

DESK = "#dfe6ef"


def pump(app: QApplication, times: int = 4) -> None:
    for _ in range(times):
        app.processEvents()


def save(widget, target: Path, desktop: bool = False) -> None:
    widget.show()
    pump(app_global)
    shot = widget.grab()
    if not desktop:
        shot.save(str(target))
        return
    canvas = QPixmap(900, 300)
    canvas.fill(QColor(DESK))
    painter = QPainter(canvas)
    painter.drawPixmap(320, 120, shot)
    painter.end()
    canvas.save(str(target))


app_global = None


def main() -> int:
    global app_global
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "shots"
    out.mkdir(parents=True, exist_ok=True)
    data_dir = Path(__file__).parent / ".shotdata"
    data_dir.mkdir(exist_ok=True)
    data = data_dir / "data.json"
    if data.exists():
        data.unlink()

    app_global = QApplication(sys.argv)
    app_global.setStyle("Fusion")
    app_global.setStyleSheet(theme.build_qss())
    store = Store(data)
    window = TimeDeck(store)
    window.resize(1288, 820)
    window.show()
    pump(app_global, 6)

    store.add(title="准备季度复盘材料", due=None, tags=["工作"], priority=3, est_min=120)
    from datetime import datetime
    store.add(title="周五前提交需求清单", due=datetime.now() + timedelta(days=2, hours=5), tags=["工作"], priority=2, est_min=60)
    heavy = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=4)
    for index in range(11):
        store.add(title=f"超载日任务 {index + 1}", due=heavy + timedelta(hours=index), tags=["工作"], priority=1, est_min=30)
    for index, task in enumerate(store.tasks):
        if task.quadrant is None:
            task.quadrant = (index % 4) + 1 if index % 5 else None
    store.flush()
    pump(app_global, 4)

    window.surface.show_view("today")
    pump(app_global, 4)
    save(window, out / "01-today.png")

    window.surface.show_view("calendar")
    pump(app_global, 6)
    save(window, out / "02-calendar.png")
    cal = window.surface.calendar_view
    cal.grid.selected = heavy.date()
    cal.select_day(heavy.date())
    pump(app_global, 3)
    save(window, out / "02b-calendar-overload.png")
    cal.jump_today()

    window.timer.start_focus(store.tasks[-1].id)
    window.timer.total_sec = 2400
    pump(app_global, 4)
    window.surface.show_view("calendar")
    save(window, out / "03-calendar-timer.png")

    window.surface.show_view("today")
    save(window, out / "04-today-running.png")

    window.surface.show_view("quadrant")
    pump(app_global, 4)
    save(window, out / "05-quadrant.png")

    from ui.task_dialog import TaskDialog
    dialog = TaskDialog(store, None, parent=window)
    dialog.widgets["title"].setText("写项目周报")
    dialog.widgets["tags"].setText("工作")
    dialog.widgets["due_on"].setChecked(True)
    save(dialog, out / "06-task-dialog.png")

    from ui.schedule_dialog import ScheduleDialog
    schedule = ScheduleDialog(store, parent=window)
    schedule.title.setText("晨跑 5 公里")
    schedule.mode.setCurrentIndex(2)
    schedule.quadrant.setCurrentIndex(3)
    schedule.weekday_boxes[0].setChecked(True)
    schedule.weekday_boxes[2].setChecked(True)
    schedule.weekday_boxes[4].setChecked(True)
    schedule._preview()
    save(schedule, out / "06b-schedule-dialog.png")

    window.float_window._expanded = True
    window.float_window._apply_size()
    window.float_window.sync()
    pump(app_global, 4)
    save(window.float_window, out / "07-float-expanded.png", desktop=True)

    window.float_window._expanded = False
    window.float_window._apply_size()
    window.float_window.sync()
    pump(app_global, 3)
    save(window.float_window, out / "08-float-pill.png", desktop=True)

    from ui.settings_dialog import SettingsDialog
    dialog = SettingsDialog(store, window)
    save(dialog, out / "09-settings.png")

    store.flush()
    print("SHOTS ->", out)
    for png in sorted(out.glob("*.png")):
        print(png.name, png.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
