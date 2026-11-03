"""The agent loop: Amazon Nova (Bedrock Converse API) + our Lambda tools.

An "agent" is just a loop: ask the model, and if it wants a tool, run the tool,
give the result back, and ask again until it answers in plain text (ReAct:
reason -> act -> observe). stream_agent() is that loop, and it streams the answer
word by word as the model writes it (ask_agent() collects it all at once). Tools run by invoking the
same Lambda function (with a Bedrock-Agents-style event, so the Lambda would
also work behind a Bedrock Agent). Reasoning, tool calls and tool results are
collected as simple "steps" so the UI and the e2e test can show them.
"""
import json
import sys
from datetime import date
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
FUNCTIONS_PATH = ROOT / "agent" / "functions.json"
MAX_TOOL_ROUNDS = 8     # safety stop so a confused model can't loop (and bill) forever
MODEL_SETTINGS = {"maxTokens": 1500, "temperature": 0}  # temperature 0: most reliable tool calls

# Conversation memory: session_id -> list of Converse messages. The model itself
# remembers nothing between calls; we resend the history every time.
SESSIONS: dict[str, list[dict]] = {}


sys.path.insert(0, str(ROOT / "agent"))  # agent_config.py holds the instructions
import agent_config  # noqa: E402


class ConfigError(Exception):
    """config.json is missing or incomplete."""


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise ConfigError("config.json not found. Run `python scripts/deploy_stack.py` first.")
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not config.get("lambda_function_name"):
        raise ConfigError("The tools aren't deployed yet. Run `python scripts/deploy_stack.py` first.")
    return config


def action_groups() -> list[dict]:
    return json.loads(FUNCTIONS_PATH.read_text(encoding="utf-8"))["action_groups"]


def system_prompt() -> str:
    """The agent instructions, plus today's date (the model can't know it, and 'next Friday' needs it)."""
    return agent_config.INSTRUCTION + f"\nToday's date is {date.today():%A, %d %B %Y}."


def tool_config() -> dict:
    """Describe our tools to the model. The descriptions here are all the model knows about them."""
    tools = []
    for group in action_groups():
        for function in group["functions"]:
            # Bedrock Agents only allow primitive types, so functions.json declares objects/arrays as JSON
            # *strings*. Converse accepts real JSON schemas, which models fill in far more reliably, so we use
            # the optional "json_schema" when present. Either way the Lambda receives JSON text.
            properties = {name: {**p.get("json_schema", {"type": p["type"]}), "description": p["description"]}
                          for name, p in function["parameters"].items()}
            schema = {"type": "object", "properties": properties}
            required = [name for name, p in function["parameters"].items() if p.get("required")]
            if required:
                schema["required"] = required
            tools.append({"toolSpec": {"name": function["name"], "description": function["description"],
                                       "inputSchema": {"json": schema}}})
    return {"tools": tools}


def group_of(function_name: str) -> str:
    for group in action_groups():
        if any(f["name"] == function_name for f in group["functions"]):
            return group["name"]
    return ""


def build_event(function_name: str, tool_input: dict, student_id: str) -> dict:
    """Make the same event Bedrock Agents would send, so lambda/handler.py needs no changes.

    Teaching point: every value is a string, so objects the model sends for
    JSON-string parameters are converted back to JSON text.
    """
    parameters = [{"name": name, "type": "string",
                   "value": json.dumps(value) if isinstance(value, (dict, list)) else str(value)}
                  for name, value in tool_input.items()]
    return {"messageVersion": "1.0", "actionGroup": group_of(function_name), "function": function_name,
            "parameters": parameters, "sessionAttributes": {"student_id": student_id}, "promptSessionAttributes": {}}


def call_tool(lambda_client, config: dict, function_name: str, tool_input: dict, student_id: str) -> str:
    """Invoke the Lambda and return the tool's text answer."""
    response = lambda_client.invoke(FunctionName=config["lambda_function_name"],
                                    Payload=json.dumps(build_event(function_name, tool_input, student_id)).encode())
    payload = json.loads(response["Payload"].read())
    if response.get("FunctionError"):
        return "The tool crashed unexpectedly. Please try again."
    return payload["response"]["functionResponse"]["responseBody"]["TEXT"]["body"]


def run_tool_calls(lambda_client, config: dict, assistant_message: dict, student_id: str, steps: list) -> list[dict]:
    """Run every tool the model asked for and return the toolResult blocks to send back."""
    results = []
    already_run = {}  # (tool, arguments) -> output: some models repeat a call, which would duplicate Todoist tasks
    for block in assistant_message["content"]:
        if "text" in block and block["text"].strip():
            steps.append({"kind": "rationale", "text": strip_thinking_tags(block["text"])})
        if "toolUse" not in block:
            continue
        call = block["toolUse"]
        steps.append({"kind": "tool_call", "action_group": group_of(call["name"]), "function": call["name"],
                      "parameters": call["input"]})
        key = (call["name"], json.dumps(call["input"], sort_keys=True))
        if key not in already_run:
            already_run[key] = call_tool(lambda_client, config, call["name"], call["input"], student_id)
        output = already_run[key]
        steps.append({"kind": "tool_result", "text": output})
        results.append({"toolResult": {"toolUseId": call["toolUseId"], "content": [{"text": output}]}})
    return results


def strip_thinking_tags(text: str) -> str:
    """Keep the words inside <thinking>...</thinking> but drop the tags (used for the reasoning trace)."""
    return text.replace("<thinking>", "").replace("</thinking>", "").strip()


class ThinkingFilter:
    """Hide <thinking>...</thinking> from streamed text.

    Nova sometimes writes its private reasoning inside <thinking> tags before calling a tool; students
    should not see it in the answer. Text arrives in small chunks and a tag can be split across two
    chunks ("<thin" + "king>"), so we hold back any ending that might be the start of a tag.
    """
    OPEN, CLOSE = "<thinking>", "</thinking>"

    def __init__(self):
        self.pending = ""    # received but not yet released
        self.hidden = False  # True while we are inside a <thinking> block

    def feed(self, chunk: str) -> str:
        """Take the next chunk; return the part that is safe to show."""
        self.pending += chunk
        visible = ""
        while True:
            tag = self.CLOSE if self.hidden else self.OPEN
            position = self.pending.find(tag)
            if position == -1:
                break
            if not self.hidden:
                visible += self.pending[:position]
            self.pending = self.pending[position + len(tag):]
            self.hidden = not self.hidden
        held = next((n for n in range(min(len(tag) - 1, len(self.pending)), 0, -1) if self.pending.endswith(tag[:n])), 0)
        release, self.pending = self.pending[:len(self.pending) - held], self.pending[len(self.pending) - held:]
        return visible if self.hidden else visible + release

    def flush(self) -> str:
        """Call at the end of the message: release whatever is still held back."""
        rest, self.pending = self.pending, ""
        return "" if self.hidden else rest


def read_stream(response):
    """Read Bedrock's converse_stream events. Yields ("text", chunk) for every piece of text as it
    arrives, then finally ("message", (assistant_message, stop_reason)) in the same shape converse() returns.

    Text arrives word by word. A tool request arrives as pieces of JSON text (its input), which we glue
    together and parse once the model has finished the message.
    """
    blocks, stop_reason = {}, "end_turn"
    for event in response["stream"]:
        if "contentBlockStart" in event:
            tool = event["contentBlockStart"]["start"].get("toolUse")
            if tool:
                blocks[event["contentBlockStart"]["contentBlockIndex"]] = {"toolUse": {**tool, "input": ""}}
        elif "contentBlockDelta" in event:
            index, delta = event["contentBlockDelta"]["contentBlockIndex"], event["contentBlockDelta"]["delta"]
            if "text" in delta:
                blocks.setdefault(index, {"text": ""})["text"] += delta["text"]
                yield "text", delta["text"]
            elif "toolUse" in delta:
                blocks[index]["toolUse"]["input"] += delta["toolUse"]["input"]
        elif "messageStop" in event:
            stop_reason = event["messageStop"]["stopReason"]
    content = []
    for index in sorted(blocks):
        block = blocks[index]
        if "toolUse" in block:
            block["toolUse"]["input"] = json.loads(block["toolUse"]["input"] or "{}")
        if "toolUse" in block or block["text"].strip():  # Converse rejects empty text blocks in the history
            content.append(block)
    yield "message", ({"role": "assistant", "content": content}, stop_reason)


def stream_agent(message: str, session_id: str, student_id: str):
    """The agent loop as a generator: yields events while the answer is still being written.

    {"type": "text", "text": "..."}            words of the answer, as they arrive
    {"type": "working", "tools": ["list_tasks"]}  the model asked for tools; we are running them
    {"type": "step", "step": {...}}            one reasoning / tool call / tool result (for the trace)
    {"type": "done", "reply": "...", "steps": [...]}   always the last event

    The same session_id keeps the conversation going; student_id selects whose
    courses the Lambda reads and writes (the DynamoDB partition key).
    """
    config = load_config()
    bedrock = boto3.client("bedrock-runtime", region_name=config["region"])
    lambda_client = boto3.client("lambda", region_name=config["region"])
    messages = list(SESSIONS.get(session_id, [])) + [{"role": "user", "content": [{"text": message}]}]
    steps: list[dict] = []
    visible: list[str] = []  # everything the student has seen so far
    # >>> LIVE: ask_agent | hint: call bedrock.converse_stream in a loop; run toolUse blocks; stop when the model answers
    for _ in range(MAX_TOOL_ROUNDS):
        response = bedrock.converse_stream(modelId=config["model_id"], system=[{"text": system_prompt()}],
                                           messages=messages, toolConfig=tool_config(), inferenceConfig=MODEL_SETTINGS)
        thinking_filter, round_text = ThinkingFilter(), []
        for kind, value in read_stream(response):
            if kind == "text":
                piece = thinking_filter.feed(value)
            else:
                assistant, stop_reason = value
                piece = thinking_filter.flush()
            if piece and not (round_text or visible):
                piece = piece.lstrip()                 # nothing shown yet: drop leading blank space
            elif piece and not round_text:
                piece = "\n\n" + piece.lstrip()        # a later round that also has text: start a new paragraph
            if piece:
                round_text.append(piece)
                yield {"type": "text", "text": piece}
        visible.extend(round_text)
        messages.append(assistant)
        if stop_reason != "tool_use":
            break  # no more tools needed: what we just streamed is the final answer
        first_new_step = len(steps)
        yield {"type": "working", "tools": [b["toolUse"]["name"] for b in assistant["content"] if "toolUse" in b]}
        results = run_tool_calls(lambda_client, config, assistant, student_id, steps)
        messages.append({"role": "user", "content": results})  # the "observe" step
        for step in steps[first_new_step:]:
            yield {"type": "step", "step": step}
    else:
        stuck = "I got stuck going in circles on that. Could you rephrase or break it into smaller requests?"
        messages.append({"role": "assistant", "content": [{"text": stuck}]})
        visible.append(stuck)
        yield {"type": "text", "text": stuck}
    # <<< LIVE: ask_agent
    SESSIONS[session_id] = messages  # only saved on success, so a failed call can't corrupt the history
    yield {"type": "done", "reply": "".join(visible).strip(), "steps": steps}


def ask_agent(message: str, session_id: str, student_id: str, show_trace: bool = False) -> tuple[str, list[dict]]:
    """Run the whole loop and return (reply_text, trace_steps). Use stream_agent() to show words as they arrive."""
    reply, steps = "", []
    for event in stream_agent(message, session_id, student_id):
        if event["type"] == "done":
            reply, steps = event["reply"], event["steps"]
    return reply, steps if show_trace else []


def friendly_error(error: Exception) -> str:
    """Translate common failures into advice a student can act on."""
    if isinstance(error, ConfigError):
        return str(error)
    if isinstance(error, NoCredentialsError):
        return "No AWS credentials found. Run `aws configure` and try again."
    if isinstance(error, ClientError):
        code = error.response["Error"]["Code"]
        message = error.response["Error"]["Message"]
        if code in ("AccessDeniedException", "AccessDenied"):
            return (f"Access denied: {message}\n\nCheck that your IAM user may call Bedrock and invoke the Lambda, "
                    "and that model access is granted in the Bedrock console for this region.")
        if code in ("ThrottlingException", "ServiceQuotaExceededException", "TooManyRequestsException"):
            return "AWS is throttling requests. Wait a few seconds and try again."
        if code == "ResourceNotFoundException":
            return "The Lambda function wasn't found. Run `python scripts/deploy_stack.py` again."
        return f"AWS error ({code}): {message}"
    return f"Something went wrong: {error}"
