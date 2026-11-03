"""Tests for app/agent_client.py: the Converse tool loop, with Bedrock and Lambda faked."""
import io
import json
import sys
from pathlib import Path

import boto3
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import agent_client  # noqa: E402
import handler  # noqa: E402

CONFIG = {"region": "us-east-1", "model_id": "us.amazon.nova-pro-v1:0", "lambda_function_name": "tools"}


def tool_use(name, tool_input, use_id="t1", text=""):
    content = ([{"text": text}] if text else []) + [{"toolUse": {"toolUseId": use_id, "name": name, "input": tool_input}}]
    return {"output": {"message": {"role": "assistant", "content": content}}, "stopReason": "tool_use"}


def answer(text):
    return {"output": {"message": {"role": "assistant", "content": [{"text": text}]}}, "stopReason": "end_turn"}


def as_stream_events(reply):
    """Turn a canned converse()-style reply into the events converse_stream() would send, in small pieces."""
    events = [{"messageStart": {"role": "assistant"}}]
    for index, block in enumerate(reply["output"]["message"]["content"]):
        if "text" in block:
            text = block["text"]
            for start in range(0, len(text), 3):  # three characters at a time, so tags get split across chunks
                events.append({"contentBlockDelta": {"contentBlockIndex": index, "delta": {"text": text[start:start + 3]}}})
        else:
            call = block["toolUse"]
            events.append({"contentBlockStart": {"contentBlockIndex": index,
                                                 "start": {"toolUse": {"toolUseId": call["toolUseId"], "name": call["name"]}}}})
            raw = json.dumps(call["input"]) if call["input"] else ""  # a tool with no parameters sends no JSON at all
            middle = len(raw) // 2
            for piece in (raw[:middle], raw[middle:]):
                events.append({"contentBlockDelta": {"contentBlockIndex": index, "delta": {"toolUse": {"input": piece}}}})
        events.append({"contentBlockStop": {"contentBlockIndex": index}})
    events.append({"messageStop": {"stopReason": reply["stopReason"]}})
    return events


class FakeBedrock:
    def __init__(self, replies):
        self.replies, self.requests = list(replies), []

    def converse_stream(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs)))  # snapshot: messages grow later
        return {"stream": iter(as_stream_events(self.replies.pop(0)))}


class FakeLambda:
    """Runs the real handler, so the loop is tested against the real tools."""

    def invoke(self, FunctionName, Payload):
        result = handler.lambda_handler(json.loads(Payload), None)
        return {"Payload": io.BytesIO(json.dumps(result).encode())}


@pytest.fixture
def fakes(monkeypatch, table):
    monkeypatch.setattr(agent_client, "load_config", lambda: CONFIG)
    agent_client.SESSIONS.clear()
    holder = {}

    def install(replies):
        holder["bedrock"] = FakeBedrock(replies)
        monkeypatch.setattr(boto3, "client", lambda service, **kw: holder["bedrock"] if service == "bedrock-runtime" else FakeLambda())
        return holder["bedrock"]

    return install


def test_tool_config_matches_functions_json():
    tools = agent_client.tool_config()["tools"]
    names = {t["toolSpec"]["name"] for t in tools}
    assert {"save_course", "grade_needed", "add_task", "break_down_project"} <= names
    save = next(t for t in tools if t["toolSpec"]["name"] == "save_course")["toolSpec"]["inputSchema"]["json"]
    assert save["required"] == ["course_name", "credit_hours", "grading_breakdown"]


def test_structured_parameters_use_real_json_schemas():
    tools = {t["toolSpec"]["name"]: t["toolSpec"]["inputSchema"]["json"]["properties"] for t in agent_client.tool_config()["tools"]}
    assert tools["break_down_project"]["steps"]["type"] == "array"
    assert tools["save_course"]["grading_breakdown"]["type"] == "object"
    assert tools["add_task"]["title"]["type"] == "string"


def test_system_prompt_has_todays_date():
    assert "Today's date is" in agent_client.system_prompt()


def test_plain_answer_without_tools(fakes):
    fakes([answer("Hi there!")])
    assert agent_client.ask_agent("hello", "s1", "me") == ("Hi there!", [])


def test_tool_round_then_answer(fakes):
    bedrock = fakes([tool_use("list_courses", {}, text="<thinking>Let me check.</thinking>"), answer("You have no courses yet.")])
    reply, steps = agent_client.ask_agent("what courses do I have?", "s1", "me", show_trace=True)
    assert reply == "You have no courses yet."  # the <thinking> part is not part of the answer...
    assert steps[0]["text"] == "Let me check."   # ...but it is in the reasoning trace, without the tags
    assert [s["kind"] for s in steps] == ["rationale", "tool_call", "tool_result"]
    assert steps[1]["function"] == "list_courses" and steps[1]["action_group"] == "AcademicTools"
    assert "No courses saved yet" in steps[2]["text"]
    sent_back = bedrock.requests[1]["messages"][-1]
    assert sent_back["role"] == "user" and "toolResult" in sent_back["content"][0]


def test_array_input_reaches_lambda_as_json_text(fakes):
    steps = [{"title": "Draft", "due": "Nov 5"}, {"title": "Review", "due": "Nov 8"}]
    bedrock = fakes([tool_use("break_down_project", {"project_name": "DB", "steps": steps}), answer("done")])
    event = agent_client.build_event("break_down_project", {"project_name": "DB", "steps": steps}, "me")
    assert json.loads(next(p["value"] for p in event["parameters"] if p["name"] == "steps")) == steps


def test_object_inputs_become_json_strings_and_student_id_is_used(fakes, table):
    fakes([tool_use("save_course", {"course_name": "OS", "credit_hours": 3, "grading_breakdown": {"final": 100}}),
           answer("Saved!")])
    agent_client.ask_agent("save OS", "s1", "alice")
    item = table.scan()["Items"][0]
    assert item["student_id"] == "alice" and item["credit_hours"] == 3


def test_session_memory_and_isolation(fakes):
    bedrock = fakes([answer("one"), answer("two"), answer("three")])
    agent_client.ask_agent("first", "s1", "me")
    agent_client.ask_agent("second", "s1", "me")
    assert len(bedrock.requests[1]["messages"]) == 3  # first, reply, second
    agent_client.ask_agent("other session", "s2", "me")
    assert len(bedrock.requests[2]["messages"]) == 1


def test_runaway_loop_is_stopped(fakes):
    fakes([tool_use("list_courses", {}, use_id=f"t{i}") for i in range(agent_client.MAX_TOOL_ROUNDS)])
    reply, _ = agent_client.ask_agent("loop", "s1", "me")
    assert "going in circles" in reply


def test_failed_call_does_not_corrupt_history(fakes):
    bedrock = fakes([tool_use("list_courses", {})])  # the second call finds no reply left: it fails mid-conversation
    with pytest.raises(IndexError):
        agent_client.ask_agent("hi", "s1", "me")
    assert "s1" not in agent_client.SESSIONS


def test_thinking_filter_hides_tags_even_when_split_across_chunks():
    text = "<thinking>private reasoning</thinking>\nHello <b>there</b>! 2 < 3"
    for size in (1, 2, 3, 7, len(text)):
        thinking_filter = agent_client.ThinkingFilter()
        shown = "".join(thinking_filter.feed(text[i:i + size]) for i in range(0, len(text), size)) + thinking_filter.flush()
        assert shown.strip() == "Hello <b>there</b>! 2 < 3", size


def test_thinking_filter_drops_an_unfinished_thinking_block():
    thinking_filter = agent_client.ThinkingFilter()
    assert thinking_filter.feed("Hi <thinking>never closed") + thinking_filter.flush() == "Hi "


def test_stream_agent_yields_words_then_steps_then_done(fakes):
    fakes([tool_use("list_courses", {}), answer("You have no courses yet.")])
    events = list(agent_client.stream_agent("what courses?", "s1", "me"))
    kinds = [e["type"] for e in events]
    assert kinds[0] == "working" and events[0]["tools"] == ["list_courses"]
    assert kinds.count("text") > 1  # streamed in several pieces, not one block
    assert "".join(e["text"] for e in events if e["type"] == "text") == "You have no courses yet."
    assert kinds[-1] == "done" and events[-1]["reply"] == "You have no courses yet."
    assert [e["step"]["kind"] for e in events if e["type"] == "step"] == ["tool_call", "tool_result"]


def test_text_from_two_rounds_is_separated_by_a_paragraph_break(fakes):
    fakes([tool_use("list_courses", {}, text="One moment."), answer("Done.")])
    reply, _ = agent_client.ask_agent("hi", "s1", "me")
    assert reply == "One moment.\n\nDone."


def test_repeated_identical_tool_call_runs_only_once(monkeypatch):
    calls = []
    monkeypatch.setattr(agent_client, "call_tool", lambda *args: calls.append(args) or "done")
    block = {"toolUse": {"toolUseId": "a", "name": "add_task", "input": {"title": "x"}}}
    repeat = {"toolUse": {"toolUseId": "b", "name": "add_task", "input": {"title": "x"}}}
    results = agent_client.run_tool_calls(None, {}, {"content": [block, repeat]}, "me", [])
    assert len(calls) == 1
    assert [r["toolResult"]["toolUseId"] for r in results] == ["a", "b"]  # the model still gets an answer for each
