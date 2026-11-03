"""Grading rules and maths for the Study Assistant.

Pure Python: no AWS, no network. Everything a student might want to change
(grade points, percentage cutoffs) lives in the two tables at the top.
The Lambda tools in academic_tools.py call these functions and turn the
results into text for the agent.
"""

# LUMS-style 4.0 scale.
GRADE_POINTS = {
    "A+": 4.00, "A": 4.00, "A-": 3.67,
    "B+": 3.33, "B": 3.00, "B-": 2.67,
    "C+": 2.33, "C": 2.00, "C-": 1.67,
    "D": 1.00, "F": 0.00,
}

# Default cutoffs (an assumption: many courses grade relatively).
# Ordered best to worst; A+ is treated as A.
THRESHOLDS = [
    ("A", 90), ("A-", 85), ("B+", 80), ("B", 75), ("B-", 70),
    ("C+", 65), ("C", 60), ("C-", 55), ("D", 50),
]

ESTIMATE_NOTE = "This is an estimate based on default grade cutoffs; your instructor's cutoffs may differ."


def normalize_grade(text: str) -> str | None:
    """Turn 'a-', ' B plus ' or 'A minus' into 'A-', 'B+'. Returns None if unknown."""
    cleaned = str(text).strip().upper().replace(" PLUS", "+").replace(" MINUS", "-").replace(" ", "")
    return cleaned if cleaned in GRADE_POINTS else None


def percent_to_grade(percent: float) -> str:
    """Map a percentage to a letter grade using THRESHOLDS."""
    for grade, cutoff in THRESHOLDS:
        if percent >= cutoff:
            return grade
    return "F"


def threshold_for(grade: str) -> float:
    """Minimum percentage for a letter grade. A+ uses the A cutoff; F is 0."""
    if grade == "A+":
        grade = "A"
    for letter, cutoff in THRESHOLDS:
        if letter == grade:
            return cutoff
    return 0


def progress(components: dict) -> tuple[float, float, float]:
    """Return (earned, graded_weight, remaining_weight) for a course.

    earned = sum(obtained / total * weight) over graded components.
    """
    earned = graded_weight = remaining_weight = 0.0
    for part in components.values():
        weight = float(part["weight"])
        if part.get("obtained") is None or part.get("total") in (None, 0):
            remaining_weight += weight
        else:
            earned += float(part["obtained"]) / float(part["total"]) * weight
            graded_weight += weight
    return earned, graded_weight, remaining_weight


def current_percent(components: dict) -> float | None:
    """Performance on the graded work so far (0-100), or None if nothing is graded."""
    earned, graded_weight, _ = progress(components)
    if graded_weight == 0:
        return None
    return earned / graded_weight * 100


def grade_needed(components: dict, target_grade: str) -> dict:
    """Work out what is needed on the remaining components for target_grade.

    Returns a dict with a 'status': 'complete', 'secured', 'needed' or 'unreachable'.
    """
    target = normalize_grade(target_grade)
    if target is None:
        return {"status": "bad_grade"}
    cutoff = threshold_for(target)
    earned, _, remaining = progress(components)

    if remaining == 0:
        return {"status": "complete", "final_percent": earned, "final_grade": percent_to_grade(earned)}

    needed = (cutoff - earned) / remaining * 100
    base = {"target": target, "cutoff": cutoff, "earned": earned, "remaining_weight": remaining}
    if needed <= 0:
        return {**base, "status": "secured"}
    if needed > 100:
        best = earned + remaining  # everything left scored 100%
        return {**base, "status": "unreachable", "best_percent": best, "best_grade": percent_to_grade(best)}
    return {**base, "status": "needed", "needed_percent": needed}


def calculate_gpa(courses: list[dict], projected: dict | None = None) -> dict:
    """Semester GPA = sum(points * credits) / sum(credits).

    courses: [{"name", "credits", "components"}]. projected: {"OS": "B+"} overrides.
    Courses with no marks and no projection are skipped and reported.
    """
    projected = {k.strip().upper(): v for k, v in (projected or {}).items()}
    total_points = total_credits = 0.0
    used, skipped = [], []
    for course in courses:
        grade = normalize_grade(projected.get(course["name"].upper(), ""))
        if grade is None:
            percent = current_percent(course["components"])
            grade = percent_to_grade(percent) if percent is not None else None
        if grade is None:
            skipped.append(course["name"])
            continue
        total_points += GRADE_POINTS[grade] * course["credits"]
        total_credits += course["credits"]
        used.append({"name": course["name"], "grade": grade, "credits": course["credits"]})
    gpa = round(total_points / total_credits, 2) if total_credits else None
    return {"gpa": gpa, "used": used, "skipped": skipped}
