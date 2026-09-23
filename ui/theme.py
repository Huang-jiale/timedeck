from __future__ import annotations

from PySide6.QtGui import QColor

BG = "#f4f6f9"
CARD = "#ffffff"
SIDEBAR = "#101720"
SIDEBAR_TEXT = "#c7d2e0"
TEXT = "#1b2430"
MUTED = "#7a8798"
LINE = "#e3e8ef"
ACCENT = "#2563eb"
ACCENT_SOFT = "#e9f1ff"
DANGER = "#d1493f"
WARN = "#e07a2f"
DONE = "#1f9d55"

FONT = "Microsoft YaHei UI"

HEAT_STOPS = ["#eef4fc", "#cfe1f7", "#9cbdea", "#5b90d4", "#2a5fae"]

TAG_COLORS = {
    "工作": "#2563eb",
    "学习": "#0f8b8d",
    "杂事": "#7c5cbf",
    "未分类": "#8794a6",
}

PRIORITY_COLORS = {1: "#8794a6", 2: "#e07a2f", 3: "#d1493f"}


def tag_color(tag: str) -> str:
    return TAG_COLORS.get(tag, "#5b7fa6")


def priority_color(priority: int) -> str:
    return PRIORITY_COLORS.get(priority, "#8794a6")


def mix(color_a: str, color_b: str, ratio: float) -> str:
    left, right = QColor(color_a), QColor(color_b)
    channel = lambda a, b: int(round(a + (b - a) * ratio))
    return QColor(
        channel(left.red(), right.red()),
        channel(left.green(), right.green()),
        channel(left.blue(), right.blue()),
    ).name()


def heat_color(total: int, done: int, focus_min: int, busy_threshold: int) -> str:
    """空闲最浅，按负荷逐级加深到蓝，超载转红。开方压缩让每天 1-2 件也看得出深浅。"""
    if total == 0:
        return HEAT_STOPS[1] if focus_min else "#f7fafd"
    load = (total / max(busy_threshold, 1)) ** 0.45
    if done == total:
        load *= 0.8
    if load >= 1:
        overload = min((load - 1) / 0.4, 1)
        return mix("#b4483c", "#7d1f16", overload)
    position = min(load, 0.999) * (len(HEAT_STOPS) - 1)
    index = int(position)
    return mix(HEAT_STOPS[index], HEAT_STOPS[min(index + 1, len(HEAT_STOPS) - 1)], position - index)


def heat_text_color(background: str) -> str:
    return "#ffffff" if QColor(background).lightnessF() < 0.55 else "#1b2430"


def build_qss() -> str:
    return f"""
* {{ font-family: "{FONT}"; font-size: 13px; }}
QMainWindow, QWidget#central {{ background: {BG}; }}
QWidget#sidebar {{ background: {SIDEBAR}; }}
QPushButton#navBtn {{
    background: transparent; color: {SIDEBAR_TEXT}; border: none;
    text-align: left; padding: 11px 18px; border-radius: 8px; font-size: 14px;
}}
QPushButton#navBtn:hover {{ background: #1b2533; color: #ffffff; }}
QPushButton#navBtn[active="true"] {{ background: {ACCENT}; color: #ffffff; font-weight: 600; }}
QLabel#sidebarTitle {{ color: #ffffff; font-size: 17px; font-weight: 700; padding: 0 0 0 18px; }}
QLabel#sidebarHint {{ color: #64748b; font-size: 11px; padding: 0 0 0 18px; }}
QPushButton#sideTag {{
    background: transparent; color: {SIDEBAR_TEXT}; border: none;
    text-align: left; padding: 5px 18px; font-size: 12px;
}}
QPushButton#sideTag:hover {{ color: #ffffff; background: #1b2533; }}
QFrame#card {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 10px; }}
QLabel#viewTitle {{ font-size: 19px; font-weight: 700; color: {TEXT}; }}
QLabel#statValue {{ font-size: 21px; font-weight: 700; color: {ACCENT}; }}
QLabel#statLabel {{ font-size: 11px; color: {MUTED}; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#taskTitle {{ font-size: 14px; color: {TEXT}; }}
QLabel#taskMeta {{ font-size: 12px; color: {MUTED}; }}
QLabel#chip {{ color: #ffffff; border-radius: 4px; padding: 2px 7px; font-size: 11px; background: {ACCENT}; }}
QPushButton#chipBtn {{
    background: {ACCENT_SOFT}; color: {ACCENT}; border: none;
    border-radius: 6px; padding: 5px 12px; font-size: 12px;
}}
QPushButton#chipBtn:hover {{ background: #d6e6ff; }}
QPushButton#ghostBtn {{ background: #ffffff; color: #46536b; border: 1px solid #cfd8e3; border-radius: 6px; padding: 5px 12px; }}
QPushButton#ghostBtn:hover {{ color: {TEXT}; border-color: {ACCENT}; }}
QLineEdit#quick {{
    background: {CARD}; border: 1px solid {LINE}; border-radius: 8px;
    padding: 9px 12px; font-size: 13px; color: {TEXT};
}}
QLineEdit#quick:focus {{ border-color: {ACCENT}; }}
QScrollArea, QListView, QTableWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #c3ccd8; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QToolTip {{ background: {SIDEBAR}; color: #ffffff; border: none; padding: 6px 9px; }}
QHeaderView::section {{ background: #eef2f7; color: {MUTED}; border: none; padding: 8px; font-size: 12px; }}
QTableWidget {{ background: {CARD}; gridline-color: {LINE}; }}
"""
