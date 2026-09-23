from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QPoint, QRect, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from models import hours_text
from ui import theme

WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]
HEADER_H = 26
PAD = 14
GAP = 5


class MonthGrid(QWidget):
    day_clicked = Signal(date)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.month = date.today().replace(day=1)
        self.selected: date | None = None
        self.today = date.today()
        self.setMinimumSize(640, 430)
        self.setMouseTracking(True)
        self.hover: date | None = None

    def set_month(self, month: date) -> None:
        self.month = month
        self.update()

    def grid_rows(self) -> list[list[date]]:
        first = self.month
        start = first - timedelta(days=(first.weekday()))
        weeks = []
        for row in range(6):
            week = [start + timedelta(days=row * 7 + col) for col in range(7)]
            weeks.append(week)
        return weeks

    def _cell_rects(self) -> dict[date, QRect]:
        width = (self.width() - PAD * 2 - GAP * 6) / 7
        height = (self.height() - HEADER_H - PAD - GAP * 5) / 6
        cells = {}
        for r, week in enumerate(self.grid_rows()):
            for c, day in enumerate(week):
                x = PAD + c * (width + GAP)
                y = HEADER_H + PAD // 2 + r * (height + GAP)
                cells[day] = QRect(int(x), int(y), int(width), int(height))
        return cells

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        hit = self._hit(pos)
        if hit != self.hover:
            self.hover = hit
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, _event):
        self.hover = None
        self.update()

    def mousePressEvent(self, event):
        hit = self._hit(event.position().toPoint())
        if hit:
            self.selected = hit
            self.day_clicked.emit(hit)
            self.update()

    def _hit(self, point: QPoint) -> date | None:
        for day, rect in self._cell_rects().items():
            if rect.contains(point):
                return day
        return None

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        header_font = QFont(theme.FONT, 9)
        header_font.setBold(True)
        painter.setFont(header_font)
        width = (self.width() - PAD * 2 - GAP * 6) / 7
        for col, name in enumerate(WEEKDAYS):
            rect = QRect(int(PAD + col * (width + GAP)), 2, int(width), HEADER_H - 6)
            painter.setPen(QColor(theme.MUTED) if col < 5 else QColor("#b4574f"))
            painter.drawText(rect, Qt.AlignCenter, name)

        threshold = int(self.store.settings["busy_threshold"])
        for day, rect in self._cell_rects().items():
            self._paint_cell(painter, day, rect, threshold)

    def _paint_cell(self, painter: QPainter, day: date, rect: QRect, threshold: int):
        in_month = day.month == self.month.month
        summary = self.store.day_summary(day)
        total, done, focus_min = summary["total"], summary["done"], summary["focus_min"]
        future = day > date.today()
        background = theme.heat_color(total, done, focus_min, threshold) if in_month else "#f7f9fc"
        if future and total == 0:
            background = "#fbfcfe"

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(rect, 8, 8)

        selected = self.selected == day
        is_today = day == self.today
        if selected or is_today:
            pen_color = QColor(theme.ACCENT) if selected else QColor("#b6c6da")
            pen_width = 2 if selected else 1
            painter.setBrush(Qt.NoBrush)
            pen = painter.pen()
            pen.setColor(pen_color)
            pen.setWidth(pen_width)
            painter.setPen(pen)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)

        text_color = QColor(theme.heat_text_color(background)) if in_month else QColor("#c2cad6")
        if self.hover == day:
            text_color = QColor(theme.TEXT) if text_color.lightnessF() > 0.5 else QColor("#ffffff")
        painter.setPen(text_color)

        number_font = QFont(theme.FONT, 11)
        number_font.setBold(is_today)
        painter.setFont(number_font)
        painter.drawText(rect.adjusted(9, 5, -9, 0), Qt.AlignLeft | Qt.AlignTop, str(day.day))

        if not in_month:
            return

        painter.setFont(QFont(theme.FONT, 8))
        lines = []
        if total:
            lines.append(f"{done}/{total}")
            if done == total:
                lines[-1] = f"{done}/{total} ✓"
        if focus_min:
            lines.append(hours_text(focus_min))
        if total and total > threshold:
            lines.append("超载")
        body = QRect(rect.left() + 9, rect.top() + 24, rect.width() - 18, rect.height() - 30)
        painter.drawText(body, Qt.AlignLeft | Qt.AlignTop, "\n".join(lines))

        if is_today:
            painter.setPen(QColor(theme.ACCENT))
            painter.setFont(QFont(theme.FONT, 8))
            painter.drawText(rect.adjusted(9, 0, -9, -6), Qt.AlignLeft | Qt.AlignBottom, "今天")


class DayDetail(QFrame):
    focus = Signal(str)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.store = store
        self.setMinimumWidth(268)
        self.setMaximumWidth(320)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        self.title = QLabel("选择一天")
        self.title.setObjectName("viewTitle")
        self.title.setStyleSheet("font-size: 15px;")
        layout.addWidget(self.title)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }")
        self.host = QWidget()
        self.body = QVBoxLayout(self.host)
        self.body.setContentsMargins(0, 0, 4, 0)
        self.body.setSpacing(6)
        self.scroll.setWidget(self.host)
        layout.addWidget(self.scroll, 1)
        self.hint = QLabel("点左侧日历格子查看当天任务与专注时长。")
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

    def show_day(self, day: date) -> None:
        self.hint.setVisible(False)
        summary = self.store.day_summary(day)
        self.title.setText(f"{day:%m月%d日} · {summary['done']}/{summary['total']} 完成 · {hours_text(summary['focus_min'])}")
        while self.body.count():
            item = self.body.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        from ui.today_view import TaskRow
        now = datetime.now()
        for task in sorted(summary["tasks"], key=lambda t: (t.done, t.due_dt or datetime.max)):
            row = TaskRow(task, now, None, self.host, compact=True)
            row.setFixedHeight(58)
            row.focus.connect(self.focus)
            self.body.addWidget(row)
        if not summary["tasks"]:
            empty = QLabel("这天没有排任务。", self.host)
            empty.setObjectName("muted")
            self.body.addWidget(empty)
        self.body.addStretch(1)


class CalendarView(QWidget):
    focus = Signal(str)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.today = date.today()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        nav = QHBoxLayout()
        nav.setSpacing(8)
        prev = QPushButton("◀")
        prev.setObjectName("ghostBtn")
        prev.setFixedWidth(38)
        prev.clicked.connect(lambda: self.shift(-1))
        nxt = QPushButton("▶")
        nxt.setObjectName("ghostBtn")
        nxt.setFixedWidth(38)
        nxt.clicked.connect(lambda: self.shift(1))
        self.caption = QLabel()
        self.caption.setObjectName("viewTitle")
        home = QPushButton("回到今天")
        home.setObjectName("chipBtn")
        home.clicked.connect(self.jump_today)
        nav.addWidget(prev)
        nav.addWidget(self.caption)
        nav.addWidget(nxt)
        nav.addStretch(1)
        nav.addWidget(home)
        layout.addLayout(nav)

        stats = QHBoxLayout()
        stats.setSpacing(8)
        self.stat_cards = {}
        for key, label in (("rate", "本月完成率"), ("focus", "本月专注"), ("busy", "最忙一天"), ("streak", "连续达标")):
            card = QFrame()
            card.setObjectName("card")
            box = QVBoxLayout(card)
            box.setContentsMargins(14, 10, 14, 10)
            box.setSpacing(2)
            value = QLabel("—")
            value.setObjectName("statValue")
            name = QLabel(label)
            name.setObjectName("statLabel")
            box.addWidget(value)
            box.addWidget(name)
            self.stat_cards[key] = value
            stats.addWidget(card)
        layout.addLayout(stats)

        legend = QHBoxLayout()
        legend.setSpacing(6)
        caption = QLabel("负荷")
        caption.setObjectName("muted")
        legend.addWidget(caption)
        for ratio, color in ((0, "#f7fafd"), (1, "#eef4fc"), (2, "#cfe1f7"), (3, "#9cbdea"), (4, "#5b90d4"), (5, "#2a5fae"), (6, "#b4483c")):
            swatch = QFrame()
            swatch.setFixedSize(24, 12)
            swatch.setStyleSheet(f"background: {color}; border-radius: 3px;")
            legend.addWidget(swatch)
        ends = QLabel("空闲 → 半满 → 超载")
        ends.setObjectName("muted")
        legend.addWidget(ends)
        legend.addStretch(1)
        layout.addLayout(legend)

        body = QHBoxLayout()
        body.setSpacing(10)
        self.grid = MonthGrid(store)
        self.grid.day_clicked.connect(self.select_day)
        body.addWidget(self.grid, 1)
        self.detail = DayDetail(store)
        self.detail.focus.connect(self.focus)
        body.addWidget(self.detail)
        layout.addLayout(body, 1)

        self._shown_day: date | None = None
        self.jump_today()

    def shift(self, delta: int) -> None:
        month = self.grid.month
        total = month.month - 1 + delta
        year = month.year + total // 12
        mon = total % 12 + 1
        self.grid.set_month(date(year, mon, 1))
        self.refresh()

    def jump_today(self) -> None:
        self.grid.set_month(self.today.replace(day=1))
        self.grid.selected = self.today
        self.select_day(self.today, keep_stats=True)

    def select_day(self, day: date, keep_stats: bool = False) -> None:
        self.detail.show_day(day)
        self._shown_day = day
        if day.month != self.grid.month.month:
            self.grid.set_month(date(day.year, day.month, 1))
        self.refresh()

    def month_days(self) -> list[date]:
        first = self.grid.month
        count = calendar.monthrange(first.year, first.month)[1]
        return [date(first.year, first.month, day) for day in range(1, count + 1)]

    def refresh(self) -> None:
        self.caption.setText(f"{self.grid.month.year} 年 {self.grid.month.month} 月工作视图")
        threshold = int(self.store.settings["busy_threshold"])
        total = done = focus_min = 0
        busiest = (0, None)
        today = date.today()
        for day in self.month_days():
            summary = self.store.day_summary(day)
            total += summary["total"]
            done += summary["done"]
            focus_min += summary["focus_min"]
            if summary["total"] > busiest[0]:
                busiest = (summary["total"], day)
        rate = f"{done / total * 100:.0f}%" if total else "—"
        self.stat_cards["rate"].setText(rate)
        self.stat_cards["focus"].setText(hours_text(focus_min))
        self.stat_cards["busy"].setText(f"{busiest[1]:%d日} · {busiest[0]}件" if busiest[1] else "—")
        self.stat_cards["streak"].setText(f"{self._streak(today)} 天")
        if self.grid.selected and self.grid.selected != self._shown_day:
            self.detail.show_day(self.grid.selected)
        self.grid.update()

    def _streak(self, today: date) -> int:
        streak = 0
        probe = today
        for _ in range(120):
            summary = self.store.day_summary(probe)
            if summary["done"] > 0:
                streak += 1
                probe -= timedelta(days=1)
                continue
            if probe == today:
                probe -= timedelta(days=1)
                continue
            break
        return streak
