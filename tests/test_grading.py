"""Unit tests for lambda/grading.py (pure maths, no AWS)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambda"))

import grading  # noqa: E402

OS = {
    "quizzes": {"weight": 15, "obtained": 12, "total": 15},
    "assignments": {"weight": 15, "obtained": 13, "total": 15},
    "midterm": {"weight": 30, "obtained": 24, "total": 30},
    "final": {"weight": 40, "obtained": None, "total": None},
}


def test_grade_points_table():
    expected = {"A+": 4.0, "A": 4.0, "A-": 3.67, "B+": 3.33, "B": 3.0, "B-": 2.67,
                "C+": 2.33, "C": 2.0, "C-": 1.67, "D": 1.0, "F": 0.0}
    assert grading.GRADE_POINTS == expected


def test_percent_to_grade_boundaries():
    assert grading.percent_to_grade(85.0) == "A-"
    assert grading.percent_to_grade(84.99) == "B+"
    assert grading.percent_to_grade(90) == "A"
    assert grading.percent_to_grade(50) == "D"
    assert grading.percent_to_grade(49.99) == "F"


def test_normalize_grade():
    assert grading.normalize_grade(" a- ") == "A-"
    assert grading.normalize_grade("B plus") == "B+"
    assert grading.normalize_grade("Z") is None


def test_worked_example_needs_90_on_final():
    result = grading.grade_needed(OS, "A-")
    assert result["status"] == "needed"
    assert result["needed_percent"] == 90.0


def test_target_already_secured():
    assert grading.grade_needed(OS, "F")["status"] == "secured"


def test_unreachable_reports_best_grade():
    result = grading.grade_needed(OS, "A+")  # needs 90 total: 49 + 40 = 89 max
    assert result["status"] == "unreachable"
    assert result["best_grade"] == "A-"  # 89% is still an A-


def test_all_graded_reports_final():
    done = {**OS, "final": {"weight": 40, "obtained": 36, "total": 40}}
    result = grading.grade_needed(done, "A")
    assert result["status"] == "complete"
    assert result["final_percent"] == 85.0 and result["final_grade"] == "A-"


def test_gpa_weighted_and_skips_ungraded():
    courses = [
        {"name": "OS", "credits": 3, "components": OS},  # 49/60 = 81.7% -> B+
        {"name": "CALCULUS", "credits": 4, "components": {"final": {"weight": 100, "obtained": None, "total": None}}},
        {"name": "DB", "credits": 3, "components": {"final": {"weight": 100, "obtained": None, "total": None}}},
    ]
    result = grading.calculate_gpa(courses, {"calculus": "A"})
    assert result["skipped"] == ["DB"]
    assert result["gpa"] == round((3.33 * 3 + 4.0 * 4) / 7, 2)
