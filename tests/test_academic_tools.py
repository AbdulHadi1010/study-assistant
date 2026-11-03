"""Tests for academic_tools.py using moto's fake DynamoDB."""
import json

import academic_tools as tools

OS_BREAKDOWN = json.dumps({"quizzes": 15, "assignments": 15, "midterm": 30, "final": 40})


def save_os(student="s1"):
    return tools.save_course(student, {"course_name": "OS", "credit_hours": "3", "grading_breakdown": OS_BREAKDOWN})


def test_save_and_list(table):
    assert "Saved OS" in save_os()
    text = tools.list_courses("s1", {})
    assert "OS (3 credits)" in text and "final: 40% of grade, not graded yet" in text


def test_weights_must_sum_to_100(table):
    reply = tools.save_course("s1", {"course_name": "OS", "credit_hours": "3", "grading_breakdown": '{"a": 50, "b": 40}'})
    assert "90" in reply and "100" in reply
    assert tools.list_courses("s1", {}).startswith("No courses")


def test_weights_tolerance(table):
    reply = tools.save_course("s1", {"course_name": "X", "credit_hours": "3", "grading_breakdown": '{"a": 33.4, "b": 33.3, "c": 33.3}'})
    assert reply.startswith("Saved")


def test_invalid_json_is_friendly(table):
    reply = tools.save_course("s1", {"course_name": "OS", "credit_hours": "3", "grading_breakdown": "not json"})
    assert "couldn't read the grading breakdown" in reply


def test_saving_twice_updates_and_keeps_marks(table):
    save_os()
    tools.record_marks("s1", {"course_name": "OS", "component": "midterm", "obtained": "24", "total": "30"})
    reply = tools.save_course("s1", {"course_name": "os", "credit_hours": "4", "grading_breakdown": OS_BREAKDOWN})
    assert reply.startswith("Updated")
    assert len(table.scan()["Items"]) == 1
    assert "got 24/30" in tools.list_courses("s1", {}) and "4 credits" in tools.list_courses("s1", {})


def test_record_marks_validation(table):
    save_os()
    assert "no component called 'project'" in tools.record_marks(
        "s1", {"course_name": "OS", "component": "project", "obtained": "1", "total": "2"})
    assert "doesn't look right" in tools.record_marks(
        "s1", {"course_name": "OS", "component": "quizzes", "obtained": "20", "total": "15"})


def test_record_marks_overwrites(table):
    save_os()
    for obtained in ("10", "12"):
        tools.record_marks("s1", {"course_name": "OS", "component": "Quizzes", "obtained": obtained, "total": "15"})
    assert "got 12/15" in tools.list_courses("s1", {})


def test_unknown_course_lists_saved_courses(table):
    save_os()
    reply = tools.grade_needed("s1", {"course_name": "Chemistry", "target_grade": "A"})
    assert "couldn't find a course called 'Chemistry'" in reply and "OS" in reply


def test_close_match_is_tolerated(table):
    tools.save_course("s1", {"course_name": "Calculus", "credit_hours": "4", "grading_breakdown": '{"final": 100}'})
    assert "Calculus" in tools.grade_needed("s1", {"course_name": "calculs", "target_grade": "B"})


def test_grade_needed_worked_example(table):
    save_os()
    for comp, got, total in (("quizzes", "12", "15"), ("assignments", "13", "15"), ("midterm", "24", "30")):
        tools.record_marks("s1", {"course_name": "OS", "component": comp, "obtained": got, "total": total})
    reply = tools.grade_needed("s1", {"course_name": "OS", "target_grade": "A-"})
    assert "90%" in reply and "estimate" in reply


def test_gpa_with_projection_and_skip(table):
    save_os()
    tools.save_course("s1", {"course_name": "DB", "credit_hours": "3", "grading_breakdown": '{"final": 100}'})
    reply = tools.calculate_gpa("s1", {"projected_grades": '{"OS": "A"}'})
    assert "4.00" in reply and "Skipped" in reply and "DB" in reply


def test_data_isolated_by_student(table):
    save_os("alice")
    assert tools.list_courses("bob", {}).startswith("No courses")


def test_record_absence(table):
    save_os()
    assert "1 of 6" in tools.record_absence("s1", {"course_name": "OS"})
    assert "5 of 6" in tools.record_absence("s1", {"course_name": "OS", "count": "4"})
    assert "at risk" not in tools.record_absence("s1", {"course_name": "OS"})
    assert tools.courses_at_risk("s1")
