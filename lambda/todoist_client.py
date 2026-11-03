"""Tiny Todoist API v1 client built on urllib (no `requests` in Lambda).

Sits between task_tools.py and the internet. The API token lives in AWS Secrets
Manager (never in code or env vars) and is fetched once, then cached for the
life of the warm Lambda. Every failure becomes a TodoistError with a friendly
message that the agent can relay to the student.
"""
import json
import logging
import os
import socket
import urllib.error
import urllib.parse
import urllib.request

import boto3

logger = logging.getLogger(__name__)

BASE_URL = "https://api.todoist.com/api/v1"
TIMEOUT_SECONDS = 10
PAGE_SIZE = 200

_cached_token = None  # fetched once from Secrets Manager


class TodoistError(Exception):
    """An error whose message is safe and helpful to show the student."""


def get_token() -> str:
    global _cached_token
    if _cached_token is None:
        secret = boto3.client("secretsmanager").get_secret_value(SecretId=os.environ["TODOIST_SECRET_ARN"])
        _cached_token = secret["SecretString"].strip()
    return _cached_token


def request(method: str, path: str, body: dict | None = None, query: dict | None = None):
    """Call Todoist and return the parsed JSON (or None for an empty response)."""
    url = f"{BASE_URL}/{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query, quote_via=urllib.parse.quote)
    headers = {"Authorization": f"Bearer {get_token()}"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        raise TodoistError(explain_http_error(error.code)) from None
    except (socket.timeout, TimeoutError):
        raise TodoistError("Todoist took too long to respond. Please try again in a moment.") from None
    except urllib.error.URLError as error:
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            raise TodoistError("Todoist took too long to respond. Please try again in a moment.") from None
        raise TodoistError("I couldn't reach Todoist right now. Please try again in a moment.") from None
    return json.loads(raw) if raw else None


def explain_http_error(status: int) -> str:
    if status in (401, 403):
        return "Your Todoist token looks invalid or expired. Please check the token stored for this app."
    if status == 404:
        return "Todoist couldn't find that item. It may have been deleted already."
    if status == 429:
        return "Todoist is rate-limiting requests. Please wait a minute and try again."
    if status >= 500:
        return "Todoist seems to be having problems right now. Please try again later."
    return f"Todoist rejected the request (HTTP {status})."


def get_all(path: str, query: dict | None = None) -> list[dict]:
    """Follow Todoist's cursor pagination: responses hold 'results' and 'next_cursor'."""
    query = dict(query or {}, limit=PAGE_SIZE)
    tasks = []
    while True:
        page = request("GET", path, query=query)
        tasks.extend(page.get("results", []))
        cursor = page.get("next_cursor")
        if not cursor:
            return tasks
        query["cursor"] = cursor


def create_task(content: str, **fields) -> dict:
    """POST /tasks. Extra fields: description, due_string, priority, parent_id."""
    payload = {"content": content, **{k: v for k, v in fields.items() if v not in (None, "")}}
    return request("POST", "tasks", body=payload)


def filter_tasks(query: str) -> list[dict]:
    """GET /tasks/filter?query=... using Todoist's filter language."""
    return get_all("tasks/filter", {"query": query})


def all_active_tasks() -> list[dict]:
    return get_all("tasks")


def close_task(task_id: str) -> None:
    request("POST", f"tasks/{task_id}/close")
