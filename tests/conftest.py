"""Shared test fixtures: put lambda/ on the import path, mock DynamoDB, fake Todoist HTTP."""
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lambda"))

import todoist_client  # noqa: E402

TEST_TOKEN = "test-token-123"


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """Fake credentials and region so nothing can touch a real account."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("TABLE_NAME", "test-courses")
    monkeypatch.setattr(todoist_client, "_cached_token", TEST_TOKEN)


@pytest.fixture
def table():
    with mock_aws():
        db = boto3.resource("dynamodb")
        db.create_table(
            TableName="test-courses",
            KeySchema=[{"AttributeName": "student_id", "KeyType": "HASH"},
                       {"AttributeName": "course_name", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "student_id", "AttributeType": "S"},
                                  {"AttributeName": "course_name", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield db.Table("test-courses")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeTodoist:
    """Replaces urllib.request.urlopen. Records calls and returns scripted replies."""

    def __init__(self):
        self.calls = []        # list of (method, path_with_query, body_dict)
        self.replies = {}      # (method, path_prefix) -> JSON-able reply, or an Exception to raise
        self.next_id = 1

    def __call__(self, request, timeout=None):
        method = request.get_method()
        path = request.full_url.split("/api/v1/")[1]
        body = json.loads(request.data) if request.data else None
        self.calls.append((method, path, body))
        assert request.headers["Authorization"] == f"Bearer {TEST_TOKEN}"
        for (m, prefix), reply in self.replies.items():
            if m == method and path.startswith(prefix):
                if isinstance(reply, list):  # a list means "one reply per call, in order"
                    reply = reply.pop(0)
                if isinstance(reply, Exception):
                    raise reply
                return FakeResponse(json.dumps(reply).encode() if reply is not None else b"")
        if method == "POST" and path == "tasks":  # default: echo the created task
            task = {"id": f"id{self.next_id}", "content": body["content"], "priority": body.get("priority", 1),
                    "due": {"date": "2026-11-13", "string": body["due_string"]} if body.get("due_string") else None}
            self.next_id += 1
            return FakeResponse(json.dumps(task).encode())
        return FakeResponse(b"")

    def http_error(self, code):
        return urllib.error.HTTPError("https://x", code, "err", {}, None)


@pytest.fixture
def todoist(monkeypatch):
    fake = FakeTodoist()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return fake
