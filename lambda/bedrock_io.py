"""Read Bedrock Agent events and build responses.

Sits between Bedrock and our tools: Bedrock sends a JSON event (which function
the model chose, plus its parameters as strings); we must answer in a very
specific JSON shape. Keeping that format in one file means the tools only ever
deal with plain Python dicts and strings.
"""

DEFAULT_STUDENT_ID = "me"


def get_parameters(event: dict) -> dict:
    """Turn Bedrock's [{name, type, value}, ...] list into {name: value}.

    All values arrive as strings, whatever type the schema declared.
    """
    return {p["name"]: p.get("value", "") for p in event.get("parameters", [])}


def get_student_id(event: dict) -> str:
    """The Streamlit app sends student_id as a session attribute."""
    attributes = event.get("sessionAttributes") or {}
    return attributes.get("student_id") or DEFAULT_STUDENT_ID


def build_response(event: dict, text: str) -> dict:
    """Wrap text in the function-details response format (messageVersion 1.0).

    Only the TEXT content type is supported by Bedrock. Session attributes are
    passed back unchanged so the agent keeps them for the rest of the session.
    """
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", ""),
            "function": event.get("function", ""),
            "functionResponse": {"responseBody": {"TEXT": {"body": text}}},
        },
        "sessionAttributes": event.get("sessionAttributes") or {},
        "promptSessionAttributes": event.get("promptSessionAttributes") or {},
    }
