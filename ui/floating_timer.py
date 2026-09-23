from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QRegion
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget,
)

from ui import theme
from ui.timer import MODE_FOCUS, MODE_IDLE

PILL = (172, 40)
CARD = (272, 112)
EDGE = 18
SNAP = 26
RADIUS = 16


def rounded_region(rect: QRect, radius: int) -> QRegion:
    """按行扫描生成圆角区域：Qt 的位图转区域在 Mono 图上不可靠，逐行最稳。"""
    radius = max(1, min(radius, rect.height() // 2, rect.width() // 2))
    region = QRegion()
    height = rect.height()
    for y in range(height):
        if y < radius:
            offset = radius - 1 - y
        elif y >= height - radius:
            offset = y - (height - radius)
        else:
            offset = -1
        inset = 0 if offset < 0 else radius - int((radius * radius - offset * offset) ** 0.5)
        width = rect.width() - inset * 2
        if width > 0:
            region = region.united(QRegion(rect.left() + inset, rect.top() + y, width, 1))
    return region


class PillBar(QWidget):
    def __init__(self, timer, parent: QWidget | None = None):
        super().__init__(parent)
        self.timer = timer
        self.setFixedHeight(6)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        area = self.rect()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#2b3a55"))
        painter.drawRoundedRect(area, 3, 3)
        filled = int(area.width() * self.timer.progress)
        if filled > 6:
            color = theme.ACCENT if self.timer.mode == MODE_FOCUS else theme.DONE
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(QRect(0, 0, filled, area.height()), 3, 3)


class FloatingTimer(QWidget):
    """右下角常驻倒计时：无边框、置顶、不抢焦点，按住即可拖动并吸附屏幕边缘。"""

    focus_requested = Signal(str)
    start_next = Signal()
    pause_requested = Signal()
    skip_requested = Signal()
    stop_requested = Signal()
    open_main = Signal()
    quit_app = Signal()
    pos_changed = Signal(int, int, int)
    visibility_changed = Signal(bool)

    def __init__(self, store, timer, parent=None):
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus,
        )
        self.store = store
        self.timer = timer
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setCursor(Qt.OpenHandCursor)
        self._drag: QPoint | None = None
        self._expanded = False
        self._flash = 0
        self._idle_left = 0

        self.state_label = QLabel("点我开专注")
        self.state_label.setObjectName("floatState")
        self.clock_label = QLabel("--:--")
        self.clock_label.setObjectName("floatClock")

        self.pill = QWidget()
        self.pill.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.pill.setFixedHeight(PILL[1])
        head = QHBoxLayout(self.pill)
        head.setContentsMargins(14, 0, 14, 0)
        head.setSpacing(8)
        head.addWidget(self.state_label)
        head.addStretch(1)
        head.addWidget(self.clock_label)

        self.title_label = QLabel("")
        self.bar_host = PillBar(self.timer)
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.btn_pause = QPushButton("暂停")
        self.btn_skip = QPushButton("跳过")
        self.btn_stop = QPushButton("结束")
        for btn in (self.btn_pause, self.btn_skip, self.btn_stop):
            btn.setFixedHeight(24)
            btn.setMinimumWidth(44)
            btn.setCursor(Qt.PointingHandCursor)
            buttons.addWidget(btn)
        self.btn_pause.clicked.connect(self.pause_requested)
        self.btn_skip.clicked.connect(self.skip_requested)
        self.btn_stop.clicked.connect(lambda: self.stop_requested.emit())
        open_main = QPushButton("主界面")
        open_main.setObjectName("floatGhost")
        open_main.setCursor(Qt.PointingHandCursor)
        open_main.clicked.connect(self.open_main)
        buttons.addStretch(1)
        buttons.addWidget(open_main)

        self.details = QWidget()
        detail_box = QVBoxLayout(self.details)
        detail_box.setContentsMargins(14, 0, 14, 12)
        detail_box.setSpacing(6)
        detail_box.addWidget(self.title_label)
        detail_box.addWidget(self.bar_host)
        detail_box.addLayout(buttons)
        self.details.setVisible(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(EDGE, EDGE, EDGE, EDGE)
        root.setSpacing(4)
        root.addWidget(self.pill, 0, Qt.AlignLeft)
        root.addWidget(self.details)
        root.addStretch(1)

        style = f"""
            QLabel#floatState {{ color: #dbe6f5; font-size: 12px; }}
            QLabel#floatClock {{ color: #ffffff; font-size: 17px; font-weight: 700; letter-spacing: 1px; }}
            QLabel#floatTitle {{ color: #ffffff; font-size: 12px; }}
            QPushButton {{ background: #24324a; color: #e6edf7; border: none; border-radius: 5px; font-size: 12px; }}
            QPushButton:hover {{ background: #33456a; }}
            QPushButton#floatGhost {{ background: transparent; color: #93a5c2; padding: 0 6px; }}
        """
        self.setStyleSheet(style)
        self.title_label.setObjectName("floatTitle")

        self._ticker = QTimer(self)
        self._ticker.setInterval(1000)
        self._ticker.timeout.connect(self._on_second)
        self._ticker.start()

        self.timer.ticked.connect(self.sync)
        self.timer.mode_changed.connect(lambda _m: (self.sync(), self._repaint()))
        self.timer.session_done.connect(self._on_session_done)

        self.setFixedSize(CARD[0] + EDGE * 2, CARD[1] + EDGE * 2)
        self._apply_size()
        self.restore_position()
        self.sync()

    def _on_session_done(self, mode: str, minutes: int) -> None:
        self._flash = 3
        self._repaint()

    def _shape(self) -> QRect:
        width, height = CARD if self._expanded else PILL
        return QRect(EDGE, EDGE, width, height)

    def _apply_size(self) -> None:
        """窗口几何恒定，展开/收起只换遮罩：改尺寸会让鼠标瞬间"离开"，来回抖动。"""
        self.pill.setMaximumWidth(PILL[0] if not self._expanded else CARD[0])
        self.details.setVisible(self._expanded)
        self._apply_mask()
        self._repaint()

    def _apply_mask(self) -> None:
        """遮罩裁掉透明边距：点击只落在可见卡片上，不会挡住卡片外的桌面。"""
        self.setMask(rounded_region(self._shape(), RADIUS))

    def _default_pos(self) -> QPoint:
        screen = QApplication.primaryScreen().availableGeometry()
        return QPoint(screen.right() - self.width() - 12, screen.bottom() - self.height() - 12)

    def restore_position(self) -> None:
        saved = self.store.float_pos
        if saved:
            point = QPoint(int(saved.get("x", 0)), int(saved.get("y", 0)))
            for screen in QApplication.screens():
                if screen.availableGeometry().adjusted(-40, -40, 40, 40).contains(point):
                    self.move(point)
                    return
        self.move(self._default_pos())

    def paintEvent(self, event):
        rect = self._shape()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        alpha = 232 if self.timer.mode != MODE_IDLE else 214
        glow = QColor(theme.ACCENT)
        glow.setAlpha(190 if self._flash else 70)
        painter.setPen(QPen(glow, 3 if self._flash else 2))
        painter.setBrush(QColor(16, 23, 32, alpha))
        painter.drawRoundedRect(rect, RADIUS, RADIUS)
        super().paintEvent(event)

    def sync(self) -> None:
        mode = self.timer.mode
        running = mode != MODE_IDLE
        if mode == MODE_IDLE:
            self.state_label.setText("点我开专注")
            self.clock_label.setText("--:--" if not self._expanded else "空闲")
            self.title_label.setText("选择一个任务开始计时")
        else:
            self.state_label.setText(self.timer.label())
            self.clock_label.setText(self.timer.clock_text())
            task = self.store.get(self.timer.task_id) if self.timer.task_id else None
            self.title_label.setText(task.title if task else "自由专注（不绑任务）")
        self.btn_pause.setText("继续" if self.timer.paused else "暂停")
        self.btn_pause.setVisible(running)
        self.btn_skip.setVisible(running)
        self.btn_stop.setVisible(running)
        self._idle_left = 0
        self.bar_host.update()
        self._repaint()

    def _repaint(self) -> None:
        if self._flash:
            self._flash -= 1
        self.update()

    def _on_second(self) -> None:
        if self.timer.mode == MODE_IDLE:
            self.clock_label.setText("--:--")
        self._idle_left += 1
        wanted = float(self.store.settings["float_opacity"]) if self._idle_left < 8 else float(self.store.settings["idle_opacity"])
        target = max(0.66, wanted)
        if abs(self.windowOpacity() - target) > 0.02:
            self.setWindowOpacity(min(1.0, max(0.3, self.windowOpacity() + (target - self.windowOpacity()) * 0.25)))
        else:
            self.setWindowOpacity(target)
        self.sync()

    def enterEvent(self, event):
        self._expanded = True
        self._idle_left = 0
        self.setWindowOpacity(float(self.store.settings["float_opacity"]))
        self._apply_size()
        self.sync()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._expanded = False
        self._apply_size()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._press_at = event.globalPosition().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
        elif event.button() == Qt.RightButton:
            self._menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)
            self._idle_left = 0

    def mouseReleaseEvent(self, event):
        if self._drag is None:
            return
        released = event.globalPosition().toPoint()
        moved = (released - getattr(self, "_press_at", released)).manhattanLength()
        self._drag = None
        self.setCursor(Qt.OpenHandCursor)
        self._snap()
        if moved >= 5:
            return
        if self.timer.mode == MODE_IDLE:
            self._pick_task(released)
        elif self._shape().contains(event.position().toPoint()):
            self.pause_requested.emit()

    def _snap(self) -> None:
        pin = 8
        center = self.frameGeometry().center()
        target = QApplication.primaryScreen().availableGeometry()
        for screen in QApplication.screens():
            if screen.availableGeometry().contains(center):
                target = screen.availableGeometry()
                break
        left, top = target.left(), target.top()
        right, bottom = target.right() - self.width(), target.bottom() - self.height()
        x = max(left, min(self.x(), right))
        y = max(top, min(self.y(), bottom))
        if x - left < SNAP:
            x = left + pin
        if right - x < SNAP:
            x = right - pin
        if y - top < SNAP:
            y = top + pin
        if bottom - y < SNAP:
            y = bottom - pin
        self.move(x, y)
        index = 0
        moved = self.frameGeometry().center()
        for i, screen in enumerate(QApplication.screens()):
            if screen.availableGeometry().contains(moved):
                index = i
                break
        self.store.float_pos = {"x": x, "y": y, "screen": index}
        self.store.mark_dirty("float_pos")
        self.pos_changed.emit(x, y, index)

    def _pick_task(self, global_pos: QPoint) -> None:
        menu = QMenu()
        menu.setStyleSheet(f"QMenu {{ background: #101720; color: #e6edf7; border: 1px solid #24324a; }}"
                           f"QMenu::item:selected {{ background: {theme.ACCENT}; }}")
        now = datetime.now()
        candidates = [t for t in self.store.active_tasks() if not t.done]
        candidates.sort(key=lambda t: (t.due_dt or datetime.max))
        for task in candidates[:8]:
            action = menu.addAction(f"▶ {task.title}")
            action.setData(task.id)
        menu.addSeparator()
        fallback = menu.addAction("▶ 自由专注（不绑任务）")
        fallback.setData("__free__")
        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        payload = chosen.data()
        if payload == "__free__":
            self.start_next.emit()
        else:
            self.focus_requested.emit(payload)

    def _menu(self, global_pos: QPoint) -> None:
        menu = QMenu()
        menu.addAction("显示主界面", lambda: (self.show_main_request(),))
        menu.addAction("隐藏悬浮窗", self._hide_self)
        topmost = menu.addAction("取消置顶") if self.windowFlags() & Qt.WindowStaysOnTopHint else menu.addAction("保持置顶")
        topmost.triggered.connect(self._toggle_topmost)
        menu.addSeparator()
        menu.addAction("退出程序", self.quit_app)
        menu.exec(global_pos)

    def show_main_request(self) -> None:
        self.open_main.emit()

    def _toggle_topmost(self) -> None:
        visible = self.isVisible()
        flags = self.windowFlags()
        if flags & Qt.WindowStaysOnTopHint:
            flags &= ~Qt.WindowStaysOnTopHint
        else:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        if visible:
            self.show()

    def _hide_self(self) -> None:
        self.hide()
        self.store.float_visible = False
        self.store.mark_dirty("float_visible")
        self.visibility_changed.emit(False)
