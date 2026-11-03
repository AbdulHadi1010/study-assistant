"""Tests for handler.py: routing and the Bedrock response format."""
import copy
import json
from pathlib import Path

import academic_tools
import handler

EVENT = json.loads((Path(__file__).parent / "events" / "sample_event.json").read_text())


def make_event(**changes):
    event = copy.deepcopy(EVENT)
    event.update(changes)
    return event


def body_of(response):
    return response["response"]["functionResponse"]["responseBody"]["TEXT"]["body"]


def test_response_format_echoes_fields(table):
    event = make_event(sessionAttributes={"student_id": "me", "other": "x"})
    response = handler.lambda_handler(event, None)
    assert response["messageVersion"] == "1.0"
    assert response["response"]["actionGroup"] == "AcademicTools"
    assert response["response"]["function"] == "grade_needed"
    assert response["sessionAttributes"] == {"student_id": "me", "other": "x"}
    assert "couldn't find a course" in body_of(response)  # empty table, but a valid reply


def test_routes_to_correct_function(table):
    event = make_event(function="list_courses", parameters=[])
    assert "No courses saved yet" in body_of(handler.lambda_handler(event, None))


def test_student_id_from_session_and_default(table):
    save = make_event(function="save_course", sessionAttributes={"student_id": "alice"}, parameters=[
        {"name": "course_name", "type": "string", "value": "OS"},
        {"name": "credit_hours", "type": "integer", "value": "3"},
        {"name": "grading_breakdown", "type": "string", "value": '{"final": 100}'}])
    handler.lambda_handler(save, None)
    assert table.scan()["Items"][0]["student_id"] == "alice"
    no_attrs = make_event(function="list_courses", parameters=[])
    del no_attrs["sessionAttributes"]
    assert "No courses" in body_of(handler.lambda_handler(no_attrs, None))  # defaulted to "me"


def test_unknown_function_is_friendly(table):
    response = handler.lambda_handler(make_event(function="fly_to_moon"), None)
    assert "don't have a tool called 'fly_to_moon'" in body_of(response)


def test_exception_still_returns_valid_response(table, monkeypatch):
    def boom(student_id, params):
        raise RuntimeError("kaboom secret detail")

    monkeypatch.setattr(academic_tools, "list_courses", boom)
    response = handler.lambda_handler(make_event(function="list_courses", parameters=[]), None)
    assert response["messageVersion"] == "1.0"
    assert "something went wrong" in body_of(response) and "kaboom" not in body_of(response)
