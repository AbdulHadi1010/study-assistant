"""Tests for task_tools.py and todoist_client.py with Todoist HTTP faked."""
import json
from datetime import date, timedelta
import logging
import socket
import urllib.error
from urllib.parse import parse_qs, urlparse

import pytest
import task_tools as tools
from todoist_client import TodoistError
from conftest import TEST_TOKEN


def test_add_task_payload(todoist):
    reply = tools.add_task("s1", {"title": "DB assignment", "due": "next Friday", "priority": "high",
                                  "course_name": "os", "description": "chapter 3"})
    method, path, body = todoist.calls[0]
    assert (method, path) == ("POST", "tasks")
    assert body == {"content": "[OS] DB assignment", "description": "chapter 3",
                    "due_string": "next Friday", "priority": 3}
    assert "Added '[OS] DB assignment'" in reply


def test_add_task_without_optionals(todoist):
    tools.add_task("s1", {"title": "Read"})
    assert todoist.calls[0][2] == {"content": "Read"}


def test_list_tasks_filters(todoist):
    todoist.replies[("GET", "tasks/filter")] = {"results": [], "next_cursor": None}
    cases = (("week", "7 days"), ("today", "today"), ("overdue", "overdue"), ("os", "search: [OS]"), ("", "7 days"))
    for given, query in cases:
        tools.list_tasks("s1", {"filter": given})
        sent = parse_qs(urlparse(todoist.calls[-1][1]).query)["query"][0]
        assert sent == query


def test_list_tasks_output_and_pagination(todoist):
    task = {"content": "[OS] Lab", "priority": 4, "due": {"string": "tomorrow"}}
    todoist.replies[("GET", "tasks/filter")] = [{"results": [task], "next_cursor": "abc"},
                                                {"results": [task], "next_cursor": None}]
    reply = tools.list_tasks("s1", {"filter": "today"})
    assert "2 task(s)" in reply and "priority: urgent" in reply
    assert "cursor=abc" in todoist.calls[1][1]


def test_complete_single_match(todoist):
    todoist.replies[("GET", "tasks")] = {"results": [{"id": "7", "content": "[DB] Assignment 1"},
                                                     {"id": "8", "content": "Buy milk"}], "next_cursor": None}
    reply = tools.complete_task("s1", {"title": "db assignment"})
    assert ("POST", "tasks/7/close", None) in todoist.calls and "done" in reply


def test_complete_multiple_matches_closes_none(todoist):
    todoist.replies[("GET", "tasks")] = {"results": [{"id": "1", "content": "DB quiz"},
                                                     {"id": "2", "content": "DB project"}], "next_cursor": None}
    reply = tools.complete_task("s1", {"title": "DB"})
    assert not any(c[0] == "POST" for c in todoist.calls)
    assert "DB quiz" in reply and "DB project" in reply


def test_complete_no_match(todoist):
    todoist.replies[("GET", "tasks")] = {"results": [], "next_cursor": None}
    assert "couldn't find" in tools.complete_task("s1", {"title": "nothing"})


def test_break_down_project(todoist):
    steps = [{"title": "Design", "due": "Nov 5"}, {"title": "Build", "due": "Nov 10"}, {"title": "Review", "due": "Nov 13"}]
    reply = tools.break_down_project("s1", {"project_name": "DB project", "steps": json.dumps(steps), "course_name": "DB"})
    posts = [c[2] for c in todoist.calls]
    assert posts[0]["content"] == "[DB] DB project" and "parent_id" not in posts[0]
    assert [p["parent_id"] for p in posts[1:]] == ["id1"] * 3
    assert "3 subtasks" in reply


def test_break_down_invalid_steps(todoist):
    assert "couldn't read the steps" in tools.break_down_project("s1", {"project_name": "X", "steps": "oops"})
    assert todoist.calls == []


def test_http_401_is_friendly(todoist):
    todoist.replies[("POST", "tasks")] = todoist.http_error(401)
    try:
        tools.add_task("s1", {"title": "x"})
    except Exception as error:  # the handler turns this into text; tested in test_handler
        assert "token looks invalid" in str(error)
    else:
        raise AssertionError("expected TodoistError")


def test_timeout_is_friendly(todoist):
    todoist.replies[("POST", "tasks")] = socket.timeout()
    try:
        tools.add_task("s1", {"title": "x"})
    except Exception as error:
        assert "too long" in str(error)
    else:
        raise AssertionError("expected TodoistError")


def test_token_never_logged_or_returned(todoist, caplog):
    caplog.set_level(logging.DEBUG)
    reply = tools.add_task("s1", {"title": "x"})
    todoist.replies[("POST", "tasks")] = urllib.error.URLError("boom")
    try:
        tools.add_task("s1", {"title": "y"})
    except Exception as error:
        reply += str(error)
    assert TEST_TOKEN not in reply and TEST_TOKEN not in caplog.text


def due(content, day):
    return {"id": content, "content": content, "priority": 1, "due": {"date": day.isoformat(), "string": "whatever"}}


def test_this_week_and_next_week_use_monday_to_sunday(todoist):
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    todoist.replies[("GET", "tasks")] = {"results": [
        due("[DB] This week", monday + timedelta(days=4)),
        due("[OS] Next week", monday + timedelta(days=9)),
        due("Far away", monday + timedelta(days=40)),
        {"id": "x", "content": "No date", "priority": 1, "due": None},
    ], "next_cursor": None}
    this_week = tools.list_tasks("s1", {"filter": "this week"})
    assert "1 task(s)" in this_week and "This week" in this_week and "Next week" not in this_week
    assert f"{monday:%a %d %b} to {monday + timedelta(days=6):%a %d %b %Y}" in this_week
    next_week = tools.list_tasks("s1", {"filter": "Next Week"})
    assert "1 task(s)" in next_week and "[OS] Next week" in next_week


def test_explicit_date_range_is_sorted_and_shows_real_dates(todoist):
    todoist.replies[("GET", "tasks")] = {"results": [
        due("Later", date(2026, 11, 22)), due("Earlier", date(2026, 11, 16)), due("Outside", date(2026, 11, 23)),
    ], "next_cursor": None}
    reply = tools.list_tasks("s1", {"start_date": "2026-11-16", "end_date": "2026-11-22"})
    assert reply.index("Earlier") < reply.index("Later") and "Outside" not in reply
    assert "due: Mon 16 Nov 2026" in reply


def test_empty_range_and_bad_dates_are_friendly(todoist):
    todoist.replies[("GET", "tasks")] = {"results": [], "next_cursor": None}
    assert "No active tasks due from" in tools.list_tasks("s1", {"filter": "this week"})
    assert "year-month-day" in tools.list_tasks("s1", {"start_date": "16/11"})


def test_unreadable_due_date_still_creates_the_task(todoist):
    todoist.replies[("POST", "tasks")] = [todoist.http_error(400), {"id": "9", "content": "[DB] Report", "due": None}]
    reply = tools.add_task("s1", {"title": "Report", "course_name": "db", "due": "the day before the deadline"})
    assert "couldn't understand the due date 'the day before the deadline'" in reply
    assert "due_string" in todoist.calls[0][2] and "due_string" not in todoist.calls[1][2]


def test_break_down_keeps_going_when_one_date_is_unreadable(todoist):
    todoist.replies[("POST", "tasks")] = [{"id": "p", "content": "[DB] Proj"},
                                          {"id": "1", "content": "a"}, todoist.http_error(400), {"id": "2", "content": "b"},
                                          {"id": "3", "content": "c"}]
    steps = json.dumps([{"title": "Plan", "due": "2026-11-10"}, {"title": "Build", "due": "someday soon"}])
    reply = tools.break_down_project("s1", {"project_name": "Proj", "course_name": "db", "steps": steps})
    assert "with 2 subtasks" in reply and "- Plan (due: 2026-11-10)" in reply
    assert "- Build (no due date: I couldn't understand 'someday soon')" in reply


def test_other_todoist_errors_are_not_swallowed(todoist):
    todoist.replies[("POST", "tasks")] = todoist.http_error(401)  # a bad token fails both attempts: report it
    with pytest.raises(TodoistError, match="token looks invalid"):
        tools.add_task("s1", {"title": "x", "due": "tomorrow"})
