# Verified facts

Checked on 2026-11-02 against official docs. **The AWS CLI on the build machine had no valid credentials** (`InvalidClientTokenId`), so nothing could be checked against a live account. Items marked ⚠️ are *not* verified and must be confirmed during the first approved deploy.

## Bedrock Agents: Lambda contract (function details) ✅
Source: https://docs.aws.amazon.com/bedrock/latest/userguide/agents-lambda.html

**Input event**: `messageVersion` ("1.0" is the only supported value), `agent` {name, id, alias, version}, `inputText`, `sessionId`, `actionGroup`, `function`, `parameters` (list of `{name, type, value}`), `sessionAttributes`, `promptSessionAttributes` (string-to-string maps). Saved as `tests/events/sample_event.json`. `apiPath`/`httpMethod`/`requestBody` appear only in OpenAPI-style groups.

**Response**: `{"messageVersion": "1.0", "response": {"actionGroup", "function", "functionResponse": {"responseBody": {"TEXT": {"body": "<string>"}}, optional "responseState": "FAILURE" | "REPROMPT"}}, "sessionAttributes", "promptSessionAttributes"}`. Only `TEXT` is supported as a content type. Implemented in `lambda/bedrock_io.py`.

*Difference from the spec:* none. (We never set `responseState`: errors are returned as normal text, as the spec requires.)

## Function-details parameter types ✅
Source: https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent_ParameterDetail.html
`type` is one of `string | number | integer | boolean | array`; `description` 1-500 characters; `required` boolean. `tests/test_agent_definition.py` enforces this.

## Quotas ✅ / ⚠️
Source: https://docs.aws.amazon.com/general/latest/gr/bedrock.html
- Characters in agent instructions: 20,000 (not adjustable) ✅ (our instruction is about 1,500)
- Action groups per agent: 20; enabled action groups per agent: 15 ✅ (we use 3 including `AMAZON.UserInput`)
- Parameters per function: 5 ⚠️ (reported by a summarising reader, not seen verbatim; we keep every function at 5 or fewer)
- Functions per action group: ⚠️ not found. We use at most 6 per group.

## Todoist API ✅ (SDK source) / ⚠️ (live behaviour)
Sources: https://developer.todoist.com/api/v1/ (base URL, Bearer auth), Doist's official Python SDK https://github.com/Doist/todoist-api-python (`_core/endpoints.py`, `api.py`, `models.py`), filter help https://www.todoist.com/help/articles/introduction-to-filters-V98wIH
- **Base URL `https://api.todoist.com/api/v1`**, `Authorization: Bearer <token>`. The old REST v2 (`/rest/v2`) is deprecated and reported to return HTTP 410 (third-party reports; not tested).
- Create: `POST /tasks` with `content`, `description`, `due_string`, `priority` (1-4, **4 = very urgent**), `parent_id`.
- List by filter: `GET /tasks/filter?query=...`; list all active: `GET /tasks`. Both paginated: `{"results": [...], "next_cursor": ...}`, next page via `cursor=` query param.
- Close: `POST /tasks/{id}/close`. Delete (used by the e2e cleanup): `DELETE /tasks/{id}` ⚠️ (standard, not seen in the SDK excerpts).
- Task fields: `id` (string), `content`, `priority`, `parent_id`, `due {date, string, ...}`. Completed state is not a `checked` field in the SDK model.
- Filters: `today`, `overdue`, `7 days`, `search: text` are valid filter-language terms. ⚠️ `search: [OS]` with square brackets (used for per-course listing) is untested against the live API.

## Model / inference profile ⚠️
- `amazon.nova-pro-v1:0` is a listed Bedrock model ID (https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html); AWS states Agents work with Bedrock models in general (https://docs.aws.amazon.com/bedrock/latest/userguide/models-features.html).
- ⚠️ The cross-region profile ID `us.amazon.nova-pro-v1:0` and its Agents support in `us-east-1` could **not** be confirmed (`aws bedrock list-inference-profiles` needs credentials). It is the default in `config.example.json`. To confirm:
  `aws bedrock list-inference-profiles --region us-east-1 --query "inferenceProfileSummaries[?contains(inferenceProfileId,'nova')].inferenceProfileId"`
- ⚠️ A newer Nova generation may be available; not checked.

## Lambda runtime ⚠️
`python3.12` is used (spec default). Whether a newer runtime is available was not checked.

## Not yet verified (needs a deployed account)
- IAM permissions on the agent role (InvokeModel on the foundation model + inference profile ARNs) are sufficient for the profile.
- Trace event field names in `app/agent_client.py` (`orchestrationTrace.rationale`, `invocationInput.actionGroupInvocationInput`, `observation.actionGroupInvocationOutput`) follow the `InvokeAgent` API reference from memory.
- `CAPABILITY_NAMED_IAM` change-set deployment and the template itself (`cfn-lint`/`validate-template` not run).
- Deleting a Secrets Manager secret that is already pending deletion with `ForceDeleteWithoutRecovery`.

## ❗ Bedrock Agents Classic is closed to new accounts (found 2026-11-03 on first deploy)
Source: https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html
Since 2026-07-30, `CreateAgent` (and `InvokeInlineAgent`) return `AccessDeniedException` ("Bedrock Agents is in Maintenance Mode...") for any AWS account with no Bedrock Agents activity in the past 12 months. There is no exception process. All other agent APIs (Update/Get/Delete/Prepare/InvokeAgent, action groups, aliases) still work for everyone. AWS recommends Amazon Bedrock AgentCore. Confirmed live: `setup_agent.py` was refused on a fresh account in us-east-1. The CloudFormation stack, Lambda code and Todoist token check all worked.

## Converse API tool use (live, 2026-11-03)
- `us.amazon.nova-pro-v1:0` exists as an inference profile in us-east-1 (`aws bedrock list-inference-profiles`). Nova Pro answered `converse` calls with tools from this account.
- Nova returned `ModelErrorException` ("invalid sequence as part of ToolUse") when a tool parameter was a JSON-encoded string (`steps`). Fixed with real JSON schemas (decision 18).
- The Bedrock Agents sections above (function-details contract, quotas, trace field names) now apply only if someone runs the Lambda behind a Classic agent in an eligible account.

## Streaming, Polly and Todoist behaviour (live, 2026-11-03)
- `bedrock-runtime` `converse_stream` with Nova Pro: events arrive as `contentBlockStart` (tool use only), `contentBlockDelta` (`text`, or `toolUse.input` as partial JSON text), `contentBlockStop`, `messageStop` (`stopReason`). A tool with no parameters sends no input JSON at all. Replies streamed in 60+ chunks; first words about 2-6 s after sending (longer when tools run first).
- Nova often writes `<thinking>...</thinking>` before calling a tool; tags can be split across stream chunks.
- Polly in us-east-1: voices Ruth, Matthew, Danielle, Joanna and Stephen all accept `Engine="generative"` and `"neural"`. Latency for one ~80 character sentence: generative 1.1-2.4 s, neural 0.35-0.6 s; each sentence plays for about 5 s.
- Streamlit 1.66.1: `st.write_stream` and `st.iframe` exist; `st.components.v1.html` logs "will be removed after 2026-06-01". Helper iframes run with `allow-same-origin allow-scripts` and `allow="autoplay"`, so a script can reach `window.parent` and `new window.parent.Audio(...).play()` worked after the student pressed Enter in the chat (checked in the built-in browser: queue created, clip playing, `currentTime` advancing). Whether the audio is *audible* was not checked by ear.
- Todoist API v1: `POST /tasks` returns HTTP 400 when `due_string` cannot be parsed (e.g. "the day before the deadline", "the Friday after next"), and also for the parent task when it is given that string. Plain phrases ("next Friday") and `YYYY-MM-DD` work. Todoist reads "next Friday" on Tue 2026-11-03 as Fri 2026-11-13.
- Still unverified: Todoist's own `search: [OS]` filter syntax (used for course filters); behaviour on Streamlit versions older than 1.66 (the code falls back to `components.html`).
