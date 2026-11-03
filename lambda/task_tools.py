"""Task tools: the student's real to-do list in Todoist.

These are the functions in the TaskTools action group. They translate what the
agent decided (title, due date, priority...) into Todoist API calls through
todoist_client.py. The *agent* plans dates and steps; these tools only create them.
"""
import logging
from datetime import date, timedelta

import academic_tools
import todoist_client
from todoist_client import TodoistError

logger = logging.getLogger(__name__)

# Todoist API priority: 4 is the most urgent (shown as p1 in the app).
PRIORITY_TO_API = {"low": 1, "medium": 2, "high": 3, "urgent": 4}
API_TO_PRIORITY = {value: name for name, value in PRIORITY_TO_API.items()}


def course_prefix(course_name: str) -> str:
    """'os' -> '[OS] ' so tasks can be found per course with a title search."""
    course_name = course_name.strip()
    return f"[{course_name.upper()}] " if course_name else ""


def due_date_of(task: dict) -> date | None:
    """The task's due date, or None. Todoist sends 'YYYY-MM-DD', or 'YYYY-MM-DDTHH:MM:SS' when a time is set."""
    text = (task.get("due") or {}).get("date")
    return date.fromisoformat(text[:10]) if text else None


def describe_task(task: dict) -> str:
    due_date = due_date_of(task)
    # Show the real calendar date ("Fri 13 Nov 2026"), not just "next friday", so the student can check it.
    due = f"{due_date:%a %d %b %Y}" if due_date else (task.get("due") or {}).get("string") or "no due date"
    priority = API_TO_PRIORITY.get(task.get("priority", 1), "low")
    return f"- {task['content']} (due: {due}, priority: {priority})"


def create_task_forgiving(title: str, due_string: str = "", **fields) -> tuple[dict, bool]:
    """Create a task. If Todoist can't understand the due date, create it without one instead of failing.

    Returns (task, due_was_understood). A model sometimes writes dates like "the day before the deadline";
    Todoist answers those with an error, and losing the whole task over a date would be a poor trade.
    """
    try:
        return todoist_client.create_task(title, due_string=due_string, **fields), True
    except TodoistError:
        if not due_string:
            raise  # the problem was not the date: let the caller report it
        return todoist_client.create_task(title, **fields), False


def add_task(student_id: str, params: dict) -> str:
    """Create one Todoist task."""
    # TODO (live): add_task
    # Hint: map priority, prefix [COURSE], call create_task
    raise NotImplementedError("add_task is filled in during the workshop: git checkout origin/solution -- lambda/task_tools.py")


def build_filter(filter_text: str) -> str:
    """Map the friendly filter words to Todoist filter queries."""
    word = (filter_text or "week").strip()
    simple = {"today": "today", "overdue": "overdue", "week": "7 days"}
    return simple.get(word.lower()) or f"search: [{word.upper()}]"


def requested_dates(params: dict) -> tuple[date, date] | None:
    """The date range the student asked for, or None for an ordinary filter.

    Todoist's own filter language has no reliable 'this week' / 'next week', so for those we fetch the
    tasks and compare due dates ourselves. The agent may also pass an explicit start_date / end_date
    (YYYY-MM-DD) for any other range, e.g. "the week of 16 Nov".
    """
    start_text, end_text = params.get("start_date", "").strip(), params.get("end_date", "").strip()
    if start_text or end_text:
        try:
            start = date.fromisoformat(start_text or end_text)
            return start, date.fromisoformat(end_text or start_text)
        except ValueError:
            raise ValueError("Dates must look like 2026-11-16 (year-month-day).") from None
    word = (params.get("filter") or "").strip().lower()
    if word in ("this week", "next week"):
        monday = date.today() - timedelta(days=date.today().weekday())  # weeks run Monday to Sunday
        if word == "next week":
            monday += timedelta(days=7)
        return monday, monday + timedelta(days=6)
    return None


def list_tasks_between(start: date, end: date) -> str:
    tasks = [t for t in todoist_client.all_active_tasks() if due_date_of(t) and start <= due_date_of(t) <= end]
    label = f"{start:%a %d %b} to {end:%a %d %b %Y}"
    if not tasks:
        return f"No active tasks due from {label}."
    tasks.sort(key=due_date_of)
    return f"{len(tasks)} task(s) due {label}:\n" + "\n".join(describe_task(t) for t in tasks)


def list_tasks(student_id: str, params: dict) -> str:
    """List active tasks matching a filter."""
    try:
        dates = requested_dates(params)
    except ValueError as error:
        return str(error)
    if dates:
        return list_tasks_between(*dates)
    # TODO (live): list_tasks
    # Hint: build_filter, filter_tasks, one line per task
    raise NotImplementedError("list_tasks is filled in during the workshop: git checkout origin/solution -- lambda/task_tools.py")


def complete_task(student_id: str, params: dict) -> str:
    """Close a task by fuzzy title match. Never guesses between several matches."""
    wanted = params.get("title", "").strip().lower()
    if not wanted:
        return "Which task did you finish?"
    tasks = todoist_client.all_active_tasks()
    exact = [t for t in tasks if t["content"].lower() == wanted]
    matches = exact or [t for t in tasks if all(word in t["content"].lower() for word in wanted.split())]
    if not matches:
        return f"I couldn't find an active task matching '{params['title']}'."
    if len(matches) > 1:
        titles = "\n".join(f"- {t['content']}" for t in matches)
        return f"Several tasks match '{params['title']}', so I completed none. Which one?\n{titles}"
    todoist_client.close_task(matches[0]["id"])
    return f"Marked '{matches[0]['content']}' as done."


def break_down_project(student_id: str, params: dict) -> str:
    """Create a parent task and dated subtasks (steps arrive as a JSON string)."""
    # TODO (live): break_down_project
    # Hint: parse steps, create parent, subtasks with parent_id
    raise NotImplementedError("break_down_project is filled in during the workshop: git checkout origin/solution -- lambda/task_tools.py")


def daily_brief(student_id: str, params: dict) -> str:
    """Today's and overdue tasks plus courses at risk."""
    tasks = todoist_client.filter_tasks("today | overdue")
    risky = academic_tools.courses_at_risk(student_id)
    text = f"{len(tasks)} task(s) today or overdue:\n" + "\n".join(describe_task(t) for t in tasks) if tasks \
        else "Nothing due today and nothing overdue."
    text += "\nCourses at risk: " + (", ".join(risky) if risky else "none.")
    return text
