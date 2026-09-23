from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QSystemTrayIcon

from store import Store
from ui import theme
from ui.floating_timer import FloatingTimer
from ui.main_window import MainWindow
from ui.timer import MODE_FOCUS, MODE_IDLE, FocusTimer


def install_crash_log(log_path: Path) -> None:
    """打包成无控制台的 exe 后，界面里的报错会静默闪退；落一份 error.log 才查得出来。"""

    def hook(kind, value, tb):
        text = "".join(traceback.format_exception(kind, value, tb))
        try:
            if log_path.exists() and log_path.stat().st_size > 200_000:
                log_path.unlink()
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{text}")
        except OSError:
            pass
        print(text, file=sys.stderr)

    sys.excepthook = hook


def make_icon(ring: bool = True) -> QIcon:
    size = 32
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#101720"))
    painter.setPen(QColor(theme.ACCENT))
    painter.drawEllipse(1, 1, size - 2, size - 2)
    pen = QColor("#ffffff") if ring else QColor("#7f8ea3")
    painter.setPen(pen)
    painter.drawLine(size // 2, size // 2, size // 2, 8)
    painter.drawLine(size // 2, size // 2, size - 11, size // 2 + 2)
    painter.end()
    return QIcon(pixmap)


class TimeDeck(QMainWindow):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.timer = FocusTimer(store, self)
        self.setWindowTitle("TimeDeck · 任务台")
        self.resize(1288, 820)
        self.setMinimumSize(1040, 660)
        self.setWindowIcon(make_icon())

        self.surface = MainWindow(store, self.timer)
        self.surface.setObjectName("central")
        self.setCentralWidget(self.surface)

        self.float_window = FloatingTimer(store, self.timer)
        self.float_window.focus_requested.connect(self.surface._start_focus)
        self.float_window.start_next.connect(lambda: self.timer.start_focus(None))
        self.float_window.pause_requested.connect(self.timer.toggle_pause)
        self.float_window.skip_requested.connect(self.timer.skip)
        self.float_window.stop_requested.connect(lambda: self.timer.stop(commit=True))
        self.float_window.open_main.connect(self.reveal)
        self.float_window.quit_app.connect(self.quit)
        self.float_window.visibility_changed.connect(self._sync_float_toggle)
        self.surface.float_visibility.connect(self._set_float_visible)
        self.surface.float_toggle.setChecked(store.float_visible)

        self.tray = self._build_tray()
        self.timer.mode_changed.connect(self._on_mode_change)
        self.timer.session_done.connect(self._on_session_done)
        self._first_hide = True
        self._quitting = False
        if store.float_visible:
            self.float_window.show()

    def _build_tray(self) -> QSystemTrayIcon:
        menu = QMenu()
        menu.addAction(QAction("打开主界面", self, triggered=self.reveal))
        menu.addAction(QAction("最小化", self, triggered=self.showMinimized))
        menu.addAction(QAction("关闭到托盘（后台继续计时）", self, triggered=self.hide))
        menu.addSeparator()
        self.act_start = QAction("开始一段专注", self, triggered=self._tray_start)
        self.act_pause = QAction("暂停/继续", self, triggered=lambda: self.timer.toggle_pause())
        self.act_stop = QAction("结束计时", self, triggered=lambda: self.timer.stop(commit=True))
        menu.addAction(self.act_start)
        menu.addAction(self.act_pause)
        menu.addAction(self.act_stop)
        menu.addSeparator()
        menu.addAction(QAction("显示悬浮窗", self, triggered=self._tray_show_float))
        menu.addSeparator()
        menu.addAction(QAction("退出 TimeDeck", self, triggered=self.quit))
        tray = QSystemTrayIcon(make_icon(), self)
        tray.setToolTip("TimeDeck · 任务台")
        tray.setContextMenu(menu)
        tray.activated.connect(self._tray_activated)
        tray.show()
        return tray

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.reveal()

    def _tray_start(self) -> None:
        candidates = [task for task in self.store.active_tasks() if not task.done]
        candidates.sort(key=lambda task: (task.due_dt is None, task.due_dt))
        self.timer.start_focus(candidates[0].id if candidates else None)
        if not self.float_window.isVisible():
            self.float_window.show()

    def _tray_show_float(self) -> None:
        self.store.float_visible = True
        self.float_window.show()
        self.surface.float_toggle.setChecked(True)

    def _set_float_visible(self, visible: bool) -> None:
        self.store.float_visible = visible
        self.store.mark_dirty("float_visible")
        if visible:
            self.float_window.show()
            self.float_window.raise_()
        else:
            self.float_window.hide()

    def _sync_float_toggle(self, visible: bool) -> None:
        self.surface.float_toggle.setChecked(visible)

    def reveal(self) -> None:
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        if not self.store.float_visible:
            self.float_window.hide()
        else:
            self.float_window.show()

    def closeEvent(self, event) -> None:
        if self._quitting:
            event.accept()
            return
        event.ignore()
        self.hide()
        if self._first_hide:
            self._first_hide = False
            if self.tray.isVisible():
                self.tray.showMessage("TimeDeck 仍在后台", "关闭后计时器继续运行。右下角悬浮窗可拖动；托盘菜单选「退出」才真正关闭。",
                                      QSystemTrayIcon.Information, 4000)

    def quit(self) -> None:
        self._quitting = True
        self.timer.stop(commit=True)
        self.store.flush()
        self.tray.hide()
        QApplication.instance().quit()

    def _on_mode_change(self, mode: str) -> None:
        running = mode != MODE_IDLE
        self.act_pause.setEnabled(running)
        self.act_stop.setEnabled(running)
        self.act_start.setText("再开一段专注" if running else "开始一段专注")
        self.tray.setIcon(make_icon(ring=running))
        if running:
            head = "专注中" if mode == MODE_FOCUS else "休息中"
            self.tray.setToolTip(f"TimeDeck · {head} {self.timer.clock_text()}")
        else:
            self.tray.setToolTip("TimeDeck · 任务台")

    def _on_session_done(self, mode: str, minutes: int) -> None:
        if not bool(self.store.settings["notify_on_finish"]) or not self.tray.isVisible():
            return
        head = "专注结束" if mode == MODE_FOCUS else "休息结束"
        body = f"完成 {minutes} 分钟" if mode == MODE_FOCUS else "可以回去干活了"
        task = self.store.get(self.timer.task_id) if self.timer.task_id else None
        if mode == MODE_FOCUS and task:
            body += f" · {task.title}"
        self.tray.showMessage(head, body, make_icon(), 5000)
        if bool(self.store.settings["sound_on_finish"]):
            QApplication.beep()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("TimeDeck")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setStyleSheet(theme.build_qss())
    store = Store()
    install_crash_log(store.data_path.parent / "error.log")
    window = TimeDeck(store)
    window.reveal()

    def shutdown() -> None:
        store.flush()

    app.aboutToQuit.connect(shutdown)
    if store.is_new:
        window.tray.showMessage("欢迎用 TimeDeck", f"数据存在 {store.data_path}", QSystemTrayIcon.Information, 5000)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
