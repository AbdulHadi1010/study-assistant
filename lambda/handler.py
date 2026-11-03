"""Lambda entry point for the Bedrock Agent action groups.

Bedrock invokes this one function for every tool call, in both action groups.
We read which function the model chose, run the matching Python function, and
return the result as text. Any error becomes a friendly message instead of a
crash, so the agent can always explain what happened to the student.
"""
import logging

import academic_tools
import bedrock_io
import task_tools
from todoist_client import TodoistError

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def build_routes() -> dict:
    """Map the function name the model picked to the Python function that runs it."""
    # TODO (live): routes
    # Hint: dict of function name -> callable(student_id, params)
    raise NotImplementedError("routes is filled in during the workshop: git checkout origin/solution -- lambda/handler.py")


def run_tool(event: dict) -> str:
    function_name = event.get("function", "")
    params = bedrock_io.get_parameters(event)
    # Log names only: parameter values could contain personal data.
    logger.info("tool=%s params=%s", function_name, sorted(params))

    tool = build_routes().get(function_name)
    if tool is None:
        return f"I don't have a tool called '{function_name}'."
    try:
        return tool(bedrock_io.get_student_id(event), params)
    except TodoistError as error:
        return str(error)
    except Exception:  # noqa: BLE001 - tools must never crash the agent
        logger.exception("Tool %s failed", function_name)
        return "Sorry, something went wrong while running that tool. Please try again."


def lambda_handler(event, context):
    return bedrock_io.build_response(event, run_tool(event))
