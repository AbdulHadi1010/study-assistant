"""Checks agent/functions.json against Bedrock's limits and against the Lambda routes."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))

import agent_config  # noqa: E402
import handler  # noqa: E402

GROUPS = json.loads((ROOT / "agent" / "functions.json").read_text(encoding="utf-8"))["action_groups"]
ALLOWED_TYPES = {"string", "number", "integer", "boolean", "array"}  # ParameterDetail types
MAX_PARAMETERS = 5


def all_functions():
    return [f for g in GROUPS for f in g["functions"]]


def test_every_function_has_a_route():
    assert {f["name"] for f in all_functions()} == set(handler.build_routes())


def test_limits_and_types():
    for function in all_functions():
        assert len(function["parameters"]) <= MAX_PARAMETERS, function["name"]
        for name, parameter in function["parameters"].items():
            assert parameter["type"] in ALLOWED_TYPES
            assert 1 <= len(parameter["description"]) <= 500, f"{function['name']}.{name}"


def test_instruction_length():
    assert len(agent_config.INSTRUCTION) < 20000
