from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

STATUS_TODO = "todo"
STATUS_DOING = "doing"
STATUS_DONE = "done"

WEEKDAY_OFFSET = {"周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6}
WORD_OFFSET = {"今天": 0, "明天": 1, "后天": 2, "大后天": 3}


def new_id() -> str:
    return "t_" + uuid.uuid4().hex[:10]


def iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.replace(second=0, microsecond=0).isoformat(timespec="minutes")


def parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def shift_to_next_weekday(base: date, target_weekday: int) -> date:
    delta = (target_weekday - base.weekday()) % 7
    return base + timedelta(days=delta if delta else 7)


def format_remaining(due: datetime | None, now: datetime, done: bool = False) -> str:
    if due is None:
        return ""
    if done:
        return "已完成"
    total = due - now
    overdue = total < timedelta(0)
    abs_total = -total if overdue else total
    mins = int(abs_total.total_seconds() // 60)
    days, rem = divmod(max(mins, 0), 1440)
    hours, minutes = divmod(rem, 60)
    if days >= 2:
        body = f"{days}天{hours}小时" if hours else f"{days}天"
    elif days == 1:
        body = f"1天{hours}小时" if hours else "1天"
    elif hours >= 1:
        body = f"{hours}小时{minutes}分" if minutes else f"{hours}小时"
    else:
        body = f"{minutes}分钟"
    return f"逾期 {body}" if overdue else f"还剩 {body}"


@dataclass
class Task:
    id: str
    title: str
    due: str | None = None
    est_min: int = 30
    spent_min: int = 0
    focus_min: int | None = None
    tags: list[str] = field(default_factory=list)
    priority: int = 1
    status: str = STATUS_TODO
    created: str = ""
    done_at: str | None = None
    archived: bool = False

    @classmethod
    def create(cls, title: str, due: datetime | None = None, tags: list[str] | None = None,
               priority: int = 1, est_min: int = 30) -> Task:
        return cls(id=new_id(), title=title.strip(), due=iso(due), est_min=est_min,
                   tags=tags or [], priority=priority, created=iso(datetime.now()) or "")

    @property
    def due_dt(self) -> datetime | None:
        return parse_dt(self.due)

    @property
    def done(self) -> bool:
        return self.status == STATUS_DONE

    def is_overdue(self, now: datetime) -> bool:
        due = self.due_dt
        return bool(due and not self.done and due < now)

    def remaining_text(self, now: datetime) -> str:
        return format_remaining(self.due_dt, now, self.done)

    def tag(self) -> str:
        return self.tags[0] if self.tags else "未分类"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "due": self.due,
            "est_min": self.est_min, "spent_min": self.spent_min,
            "focus_min": self.focus_min,
            "tags": list(self.tags), "priority": self.priority,
            "status": self.status, "created": self.created,
            "done_at": self.done_at, "archived": self.archived,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> Task:
        return cls(
            id=str(raw.get("id") or new_id()),
            title=str(raw.get("title") or "(未命名任务)"),
            due=raw.get("due"),
            est_min=int(raw.get("est_min") or 30),
            spent_min=int(raw.get("spent_min") or 0),
            focus_min=int(raw["focus_min"]) if raw.get("focus_min") else None,
            tags=[str(t) for t in raw.get("tags") or []],
            priority=int(raw.get("priority") or 1),
            status=raw.get("status") or STATUS_TODO,
            created=raw.get("created") or "",
            done_at=raw.get("done_at"),
            archived=bool(raw.get("archived")),
        )


TAG_RE = re.compile(r"#(\S+)")
PRIO_RE = re.compile(r"!([123])")
EST_RE = re.compile(r"(?<![\d:])(\d+(?:\.\d+)?)\s*(h|小时|hm|min|分钟|m)\b", re.IGNORECASE)
DATE_RE = re.compile(r"(\d{4}-\d{1,2}-\d{1,2})|(\d{1,2})([-/])(\d{1,2})")
TIME_RE = re.compile(r"(\d{1,2})[:：](\d{2})")


def parse_quick(text: str, now: datetime | None = None) -> dict:
    """把 "明天18:00 写项目周报 #工作 !3 90min" 这样的输入解析成任务字段。"""
    now = now or datetime.now()
    raw = text
    tags = TAG_RE.findall(raw)
    raw = TAG_RE.sub("", raw)
    priority = 1
    prio = PRIO_RE.search(raw)
    if prio:
        priority = int(prio.group(1))
        raw = PRIO_RE.sub("", raw)
    est = None
    estm = EST_RE.search(raw)
    if estm:
        value = float(estm.group(1))
        unit = estm.group(2).lower()
        est = int(value * 60) if unit in {"h", "小时"} else int(value)
        raw = EST_RE.sub("", raw)

    day = None
    for word, offset in WORD_OFFSET.items():
        if word in raw:
            day = (now + timedelta(days=offset)).date()
            raw = raw.replace(word, " ")
            break
    if day is None:
        for word, target in WEEKDAY_OFFSET.items():
            if word in raw:
                day = shift_to_next_weekday(now.date(), target)
                raw = raw.replace(word, " ")
                break
    if day is None:
        dated = DATE_RE.search(raw)
        if dated:
            if dated.group(1):
                year, month, dom = (int(x) for x in dated.group(1).split("-"))
            else:
                month, dom = int(dated.group(2)), int(dated.group(4))
                year = now.year
                if (month, dom) < (now.month, now.day):
                    year += 1
            try:
                day = date(year, month, dom)
            except ValueError:
                day = None
            raw = DATE_RE.sub(" ", raw)

    timed = TIME_RE.search(raw)
    if timed:
        hour, minute = int(timed.group(1)), int(timed.group(2))
        raw = TIME_RE.sub(" ", raw)
    else:
        hour, minute = 23, 59

    due = datetime(day.year, day.month, day.day, hour, minute) if day else None
    title = re.sub(r"\s{2,}", " ", raw).strip(" ,，-")
    if not title:
        title = re.sub(r"\s{2,}", " ", raw).strip() or text.strip()
    return {"title": title, "due": due, "tags": tags, "priority": priority, "est_min": est}


def day_span(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day)
    return start, start + timedelta(days=1)


def hours_text(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}m"
    value = minutes / 60
    return f"{value:.1f}h".replace(".0h", "h")
