"""End-to-end test: run the acceptance conversation against the deployed agent.

Sends the 10 steps from SPEC.md section 8 in ONE session as student "e2e-test",
prints each reply and the tools the agent called, checks the expected tool was
used (and Todoist/DynamoDB state where relevant), then removes everything it
created. Costs a few cents. Exit code 0 only if every step passes.
"""
import sys
import uuid

import boto3

from common import ROOT, load_config

sys.path.insert(0, str(ROOT / "app"))
import agent_client  # noqa: E402
import todoist_client  # noqa: E402

STUDENT_ID = "e2e-test"


def todoist_titles() -> list[str]:
    return [t["content"].lower() for t in todoist_client.all_active_tasks()]


def has_task(*words: str) -> bool:
    return any(all(w in title for w in words) for title in todoist_titles())


def subtask_count() -> int:
    return sum(1 for t in todoist_client.all_active_tasks() if t.get("parent_id"))


# (message, tools of which at least one must be called (empty = any), extra check or None, description of the check)
STEPS = [
    ("My courses are OS (3 credits: quizzes 15, assignments 15, midterm 30, final 40) and Calculus "
     "(4 credits: quizzes 20, midterm 30, final 50).", {"save_course"}, None, ""),
    ("I got 12/15 in OS quizzes, 13/15 in assignments and 24/30 in the midterm.", {"record_marks"}, None, ""),
    ("What do I need in the OS final to get an A-?", {"grade_needed"}, lambda reply: "90" in reply, "reply mentions 90%"),
    ("Add my DB assignment due next Friday, high priority.", {"add_task"}, lambda reply: has_task("db", "assignment"), "task exists in Todoist"),
    ("What's due this week?", {"list_tasks"}, None, ""),
    ("I have a DB project due in 2 weeks, break it down for me.", {"break_down_project"}, lambda reply: subtask_count() >= 4, "4+ subtasks in Todoist"),
    ("I finished the DB assignment.", {"complete_task"}, lambda reply: not has_task("db", "assignment"), "task closed in Todoist"),
    # The project already exists from step 6, so the agent rightly does not create it again; it must check the grade.
    ("I have a DB project due in 2 weeks and I'm worried about my OS grade.", {"grade_needed", "list_courses"}, None, ""),
    ("What about Calculus?", {"grade_needed", "list_courses", "calculate_gpa"}, None, ""),
    # No tool is required here: earlier turns already showed the saved courses, so the agent may answer from
    # the conversation. What matters is a friendly reply that names the unknown course (and no crash).
    ("What do I need in Chemistry to get an A?", set(),
     lambda reply: "chemistry" in reply.lower() and "<thinking>" not in reply and "traceback" not in reply.lower(),
     "friendly reply about Chemistry, no crash"),
]


def run_step(number: int, session_id: str, step: tuple) -> bool:
    message, expected, check, check_name = step
    print(f"\n--- Step {number}: {message}")
    try:
        reply, trace = agent_client.ask_agent(message, session_id, STUDENT_ID, show_trace=True)
    except Exception as error:  # noqa: BLE001
        print("FAIL:", agent_client.friendly_error(error))
        return False
    called = [s["function"] for s in trace if s["kind"] == "tool_call"]
    print(f"Agent: {reply}\nTools called: {called or 'none'}")
    ok = not expected or bool(expected & set(called))  # an empty set means "any tool use is fine"
    if not ok:
        print(f"FAIL: expected one of {sorted(expected)}")
    if ok and check and not check(reply):
        print(f"FAIL: {check_name}")
        ok = False
    print("PASS" if ok else "FAILED")
    return ok


def clean_up(config: dict, tasks_before: set) -> None:
    print("\nCleaning up test data ...")
    for task in todoist_client.all_active_tasks():
        if task["id"] not in tasks_before:
            todoist_client.request("DELETE", f"tasks/{task['id']}")
    table = boto3.resource("dynamodb", region_name=config["region"]).Table(config["table_name"])
    from boto3.dynamodb.conditions import Key
    for item in table.query(KeyConditionExpression=Key("student_id").eq(STUDENT_ID))["Items"]:
        table.delete_item(Key={"student_id": STUDENT_ID, "course_name": item["course_name"]})


def main() -> None:
    config = load_config()
    secret = boto3.client("secretsmanager", region_name=config["region"]).get_secret_value(SecretId=config["todoist_secret_arn"])
    todoist_client._cached_token = secret["SecretString"].strip()
    tasks_before = {t["id"] for t in todoist_client.all_active_tasks()}
    session_id = str(uuid.uuid4())
    try:
        results = [run_step(i, session_id, step) for i, step in enumerate(STEPS, start=1)]
    finally:
        clean_up(config, tasks_before)
    print(f"\n{sum(results)}/{len(results)} steps passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
