"""Academic tools: courses, marks, grade maths and absences (DynamoDB).

These are the functions in the AcademicTools action group. Each takes the
student_id (the DynamoDB partition key) and the parameters dict from Bedrock
(all strings) and returns a short text answer for the agent to relay.
Tools never raise for bad input; they return a helpful message instead.
"""
import difflib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3

import grading

DEFAULT_MAX_ABSENCES = 6
AT_RISK_PERCENT = 70  # below B- counts as "at risk"
AT_RISK_ABSENCE_FRACTION = 0.8


# ---------- small helpers ----------

def get_table():
    """Open the courses table. Created per call so tests can mock DynamoDB."""
    return boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def fmt(number) -> str:
    """12.0 -> '12', 81.666 -> '81.7'."""
    text = f"{float(number):.1f}"
    return text[:-2] if text.endswith(".0") else text


def to_decimal(value) -> Decimal:
    """DynamoDB stores numbers as Decimal, not float."""
    return Decimal(str(value))


def normalise_name(name: str) -> str:
    """Sort keys are stored upper-case so 'os' and 'OS' are the same course."""
    return name.strip().upper()


def all_courses(student_id: str) -> list[dict]:
    from boto3.dynamodb.conditions import Key

    items = get_table().query(KeyConditionExpression=Key("student_id").eq(student_id))["Items"]
    return sorted(items, key=lambda item: item["course_name"])


def saved_courses_text(student_id: str) -> str:
    names = [c["display_name"] for c in all_courses(student_id)]
    return ", ".join(names) if names else "none yet"


def find_course(student_id: str, name: str) -> dict | None:
    """Exact (case-insensitive) match first, then a close match like 'operating sys' -> 'OS SYSTEMS'."""
    wanted = normalise_name(name)
    courses = all_courses(student_id)
    for course in courses:
        if course["course_name"] == wanted:
            return course
    keys = [c["course_name"] for c in courses]
    close = difflib.get_close_matches(wanted, keys, n=1, cutoff=0.75)
    if close:
        return next(c for c in courses if c["course_name"] == close[0])
    return None


def course_not_found(student_id: str, name: str) -> str:
    return f"I couldn't find a course called '{name}'. Your saved courses are: {saved_courses_text(student_id)}."


def parse_json(text: str, expected_type: type):
    """Parse a JSON string parameter. Returns None if invalid or the wrong type.

    Teaching point: Bedrock function parameters are primitives, so objects and
    arrays are passed as JSON *strings* and parsed here.
    """
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, expected_type) else None


def course_summary(course: dict) -> str:
    """One readable line (plus components) describing a course."""
    lines = [f"{course['display_name']} ({fmt(course['credit_hours'])} credits)"]
    for name, part in course["components"].items():
        if part.get("obtained") is None:
            lines.append(f"  - {name}: {fmt(part['weight'])}% of grade, not graded yet")
        else:
            lines.append(f"  - {name}: {fmt(part['weight'])}% of grade, got {fmt(part['obtained'])}/{fmt(part['total'])}")
    earned, graded_weight, _ = grading.progress(course["components"])
    if graded_weight:
        lines.append(f"  Earned so far: {fmt(earned)} of {fmt(graded_weight)} graded points "
                     f"({fmt(earned / graded_weight * 100)}% on graded work)")
    return "\n".join(lines)


# ---------- tools ----------

def save_course(student_id: str, params: dict) -> str:
    """Create or update a course. Weights must sum to 100 (+/- 0.5)."""
    # >>> LIVE: save_course | hint: parse JSON breakdown, check weights sum to 100, put_item
    name = params.get("course_name", "").strip()
    breakdown = parse_json(params.get("grading_breakdown", ""), dict)
    if not name:
        return "I need a course name to save it."
    try:
        credits = int(float(params.get("credit_hours", "")))
    except ValueError:
        return "I need the credit hours as a number (for example 3)."
    if not breakdown or not all(isinstance(w, (int, float)) and w > 0 for w in breakdown.values()):
        return ('I couldn\'t read the grading breakdown. Please give it like '
                '{"quizzes": 15, "midterm": 35, "final": 50} with positive weights.')
    total = sum(breakdown.values())
    if abs(total - 100) > 0.5:
        return f"The grading weights add up to {fmt(total)}, but they must add up to 100. Can you check them?"

    existing = find_course(student_id, name)
    old_components = existing["components"] if existing else {}
    components = {}
    for component, weight in breakdown.items():
        # Keep marks already recorded for components that still exist.
        old = old_components.get(component, {})
        components[component] = {"weight": to_decimal(weight), "obtained": old.get("obtained"), "total": old.get("total")}

    key = existing["course_name"] if existing else normalise_name(name)
    get_table().put_item(Item={
        "student_id": student_id,
        "course_name": key,
        "display_name": existing["display_name"] if existing else name,
        "credit_hours": credits,
        "components": components,
        "absences": existing["absences"] if existing else 0,
        "max_absences": existing["max_absences"] if existing else DEFAULT_MAX_ABSENCES,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    verb = "Updated" if existing else "Saved"
    return f"{verb} {name}: {credits} credits, grading {json.dumps(breakdown)}."
    # <<< LIVE: save_course


def list_courses(student_id: str, params: dict) -> str:
    """List every saved course with marks so far."""
    courses = all_courses(student_id)
    if not courses:
        return "No courses saved yet. Tell me your courses, credit hours and grading breakdown."
    return "\n".join(course_summary(c) for c in courses)


def record_marks(student_id: str, params: dict) -> str:
    """Record (or overwrite) the marks for one component of a course."""
    course = find_course(student_id, params.get("course_name", ""))
    if course is None:
        return course_not_found(student_id, params.get("course_name", ""))
    component = next((c for c in course["components"] if c.lower() == params.get("component", "").strip().lower()), None)
    if component is None:
        return (f"{course['display_name']} has no component called '{params.get('component', '')}'. "
                f"Its components are: {', '.join(course['components'])}.")
    try:
        obtained, total = float(params["obtained"]), float(params["total"])
    except (KeyError, ValueError):
        return "I need both the marks obtained and the total marks as numbers."
    if total <= 0 or obtained < 0 or obtained > total:
        return f"{fmt(obtained)}/{fmt(total)} doesn't look right: marks must be between 0 and the total."

    get_table().update_item(
        Key={"student_id": student_id, "course_name": course["course_name"]},
        UpdateExpression="SET components.#c.obtained = :o, components.#c.#t = :t, updated_at = :u",
        ExpressionAttributeNames={"#c": component, "#t": "total"},
        ExpressionAttributeValues={":o": to_decimal(obtained), ":t": to_decimal(total),
                                   ":u": datetime.now(timezone.utc).isoformat()},
    )
    return f"Recorded {component} for {course['display_name']}: {fmt(obtained)}/{fmt(total)}."


def grade_needed(student_id: str, params: dict) -> str:
    """Percentage needed on the remaining components for a target letter grade."""
    course = find_course(student_id, params.get("course_name", ""))
    if course is None:
        return course_not_found(student_id, params.get("course_name", ""))
    # >>> LIVE: grade_needed | hint: earned so far vs remaining weight
    result = grading.grade_needed(course["components"], params.get("target_grade", ""))
    name = course["display_name"]
    status = result["status"]
    if status == "bad_grade":
        return f"'{params.get('target_grade', '')}' isn't a grade I know. Use something like A-, B+ or C."
    if status == "complete":
        return (f"All of {name} is graded: final {fmt(result['final_percent'])}% = {result['final_grade']}. "
                + grading.ESTIMATE_NOTE)
    note = grading.ESTIMATE_NOTE
    if status == "secured":
        return (f"You've already secured {result['target']} in {name} "
                f"(you have {fmt(result['earned'])} points and {result['target']} needs {fmt(result['cutoff'])} in total). {note}")
    if status == "unreachable":
        return (f"{result['target']} isn't reachable in {name}: even 100% on the rest gives {fmt(result['best_percent'])}%, "
                f"which is a {result['best_grade']}. {note}")
    return (f"For {result['target']} in {name} you need {fmt(result['needed_percent'])}% on the remaining "
            f"{fmt(result['remaining_weight'])}% of the grade that is still ungraded. You already have "
            f"{fmt(result['earned'])} points and {result['target']} needs {fmt(result['cutoff'])} in total. {note}")
    # <<< LIVE: grade_needed


def calculate_gpa(student_id: str, params: dict) -> str:
    """Semester GPA, optionally with projected grades per course."""
    courses = all_courses(student_id)
    if not courses:
        return "No courses saved yet, so I can't calculate a GPA."
    projected = {}
    if params.get("projected_grades"):
        projected = parse_json(params["projected_grades"], dict)
        if projected is None:
            return 'I couldn\'t read the projected grades. Please give them like {"OS": "B+"}.'
    inputs = [{"name": c["display_name"], "credits": float(c["credit_hours"]), "components": c["components"]}
              for c in courses]
    result = grading.calculate_gpa(inputs, projected)
    if result["gpa"] is None:
        return "None of your courses have marks or projected grades yet, so I can't calculate a GPA."
    parts = ", ".join(f"{u['name']} {u['grade']}" for u in result["used"])
    text = f"Projected GPA: {result['gpa']:.2f} (based on {parts}). {grading.ESTIMATE_NOTE}"
    if result["skipped"]:
        text += f" Skipped (no marks or projection): {', '.join(result['skipped'])}."
    return text


def record_absence(student_id: str, params: dict) -> str:
    """Add missed classes to a course and report absences used vs allowed."""
    course = find_course(student_id, params.get("course_name", ""))
    if course is None:
        return course_not_found(student_id, params.get("course_name", ""))
    try:
        count = int(float(params.get("count") or 1))
    except ValueError:
        count = 1
    used = int(course["absences"]) + max(count, 1)
    allowed = int(course["max_absences"])
    get_table().update_item(
        Key={"student_id": student_id, "course_name": course["course_name"]},
        UpdateExpression="SET absences = :a, updated_at = :u",
        ExpressionAttributeValues={":a": used, ":u": datetime.now(timezone.utc).isoformat()},
    )
    warning = " You're at or over the limit!" if used >= allowed else (" Careful, you're close to the limit." if used >= allowed * AT_RISK_ABSENCE_FRACTION else "")
    return f"{course['display_name']}: {used} of {allowed} allowed absences used.{warning}"


def courses_at_risk(student_id: str) -> list[str]:
    """Courses with a projected grade below B- or absences at 80%+ of the limit (used by daily_brief)."""
    risky = []
    for course in all_courses(student_id):
        percent = grading.current_percent(course["components"])
        low_grade = percent is not None and percent < AT_RISK_PERCENT
        many_absences = float(course["absences"]) >= float(course["max_absences"]) * AT_RISK_ABSENCE_FRACTION
        if low_grade or many_absences:
            reasons = []
            if low_grade:
                reasons.append(f"{fmt(percent)}% on graded work")
            if many_absences:
                reasons.append(f"{int(course['absences'])}/{int(course['max_absences'])} absences")
            risky.append(f"{course['display_name']} ({', '.join(reasons)})")
    return risky
