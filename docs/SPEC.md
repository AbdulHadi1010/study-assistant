# SPEC.md: Study Assistant

## 1. Product summary
A chat assistant that helps a university student manage their semester. The student talks to it in plain language. It:

- remembers their courses, credit hours, grading breakdown and marks (DynamoDB)
- answers grade questions: "What do I need in the OS final to get an A-?", "What will my GPA be?"
- manages their real to-do list in **Todoist** (the app they already use), so tasks appear on their phone. It does not create a separate to-do app.
- breaks big projects and exam prep into dated subtasks in Todoist

The assistant is the "brain"; Todoist is where tasks live; DynamoDB holds the academic profile.

## 2. Users and identity
- One student per deployment (each workshop attendee deploys their own stack in their own AWS account).
- The Streamlit app sends a `student_id` (from a sidebar text field, default `"me"`) as a Bedrock **session attribute**. Lambda reads it from the event and uses it as the DynamoDB partition key. This keeps the design multi-user-ready and is a teaching point.

## 3. Architecture

```
Student (browser)
   │
   ▼
Streamlit app (local)  ──boto3 invoke_agent (sessionId, sessionAttributes)──▶  Bedrock Agent (Amazon Nova)
                                                                                │  ReAct: reason → pick tool → observe
                                                                                ▼
                                                              Action groups (function details)
                                                                                │
                                                                                ▼
                                                               Lambda: study-assistant-tools (Python)
                                                                   │                       │
                                                                   ▼                       ▼
                                                    DynamoDB: courses table     Todoist API (token from
                                                                                 Secrets Manager)
```

Optional bonus: the Streamlit app sends the agent's reply to Amazon Polly and plays the audio.

## 4. Features

### 4.1 Academic profile (DynamoDB)
| Function | Purpose |
|---|---|
| `save_course` | Create or update a course: name, credit hours, grading breakdown (component → weight %). Weights must sum to 100. |
| `list_courses` | List saved courses with credits, breakdown, marks recorded so far, and current weighted %. |
| `record_marks` | Record marks for one component of a course (e.g., midterm 28/40). Overwrites that component's marks if already recorded. |
| `grade_needed` | Given a course and target letter grade, compute the % needed on the remaining (ungraded) components. |
| `calculate_gpa` | Compute semester GPA from saved courses. Optional projected grades per course override; otherwise use the grade implied by current marks; skip courses with no marks and no projection (say so). |

### 4.2 Tasks (Todoist)
| Function | Purpose |
|---|---|
| `add_task` | Create a Todoist task with title, natural-language due date ("next Friday"), priority, optional description, optional course (prefixed to the title as `[OS]`). |
| `list_tasks` | List active tasks using a Todoist filter: `today`, `overdue`, `7 days`, or a course name. Return title, due date, priority. |
| `complete_task` | Close a task by fuzzy title match. If several match, return the candidates and complete none. |
| `break_down_project` | Create a parent task and dated subtasks. The **agent** plans the steps and dates; the tool only creates them. |

### 4.3 Stretch features (implement in solution, list in README as "extend it yourself")
| Function | Purpose |
|---|---|
| `record_absence` | Increment absence count for a course; return absences used vs allowed (`max_absences` stored per course, default 6). |
| `daily_brief` | Combine today's and overdue Todoist tasks with courses at risk (projected grade below B- or absences at 80%+ of the limit). |

### 4.4 Frontend (Streamlit)
- Chat UI: `st.chat_input`, `st.chat_message`, history in `st.session_state`.
- A `sessionId` (uuid4) is generated once per browser session and reused so the agent keeps context. A "New conversation" button resets it.
- Sidebar: student ID field, "Show agent reasoning" toggle, "Speak replies (Polly)" toggle.
- When reasoning is on, show the agent's trace (rationale, tool called, parameters, tool output) in an expander under each reply.
- Clear error messages for common failures: missing config, no AWS credentials, model access not granted, throttling.

## 5. Data model

**Table:** created by CloudFormation, on-demand billing.
- Partition key `student_id` (S), sort key `course_name` (S, stored uppercase-normalised, e.g., `OS`, `CALCULUS`).
- Attributes:
  - `display_name` (S), as typed by the student
  - `credit_hours` (N)
  - `components` (M): `{ "<component>": { "weight": N, "obtained": N|null, "total": N|null } }`
  - `absences` (N, default 0), `max_absences` (N, default 6)
  - `updated_at` (S, ISO 8601)

Course name matching is case-insensitive and tolerant of small differences (e.g., "os" = "OS"). If no match, return the list of saved courses.

## 6. Grading rules
Put these in one config module (`lambda/grading.py`) so they are easy to change.

**Grade points (LUMS-style 4.0 scale):** A+ 4.00, A 4.00, A- 3.67, B+ 3.33, B 3.00, B- 2.67, C+ 2.33, C 2.00, C- 1.67, D 1.00, F 0.00.

**Default percentage thresholds (an assumption, since many courses grade relatively):** A 90, A- 85, B+ 80, B 75, B- 70, C+ 65, C 60, C- 55, D 50, F below 50. A+ is treated as A for thresholds. Tool responses that use thresholds must say the result is an estimate based on default cutoffs.

**`grade_needed` maths:**
- `earned = Σ (obtained/total × weight)` over graded components
- `remaining_weight = Σ weight` over ungraded components
- `needed_pct = (threshold − earned) / remaining_weight × 100`
- If `remaining_weight == 0`: report the final % and grade.
- If `needed_pct <= 0`: target already secured.
- If `needed_pct > 100`: not reachable; report the best achievable grade instead.

**GPA:** `Σ (grade_points × credits) / Σ credits`, rounded to 2 decimals.

## 7. Non-functional requirements
- **Cost:** everything on-demand or free tier; no always-on resources. One Secrets Manager secret (about $0.40/month, prorated). Cleanup deletes everything.
- **Security:** least-privilege IAM; Lambda invoke permission restricted to Bedrock agents in the same account; token never logged or returned.
- **Reliability:** Todoist calls use a 10-second timeout and return friendly errors on failure.
- **Observability:** Lambda logs each tool call (function name and parameter names, never values that could hold secrets) to CloudWatch.
- **Portability:** region configurable (default `us-east-1`); works on Windows, macOS, Linux.

## 8. Acceptance criteria (end-to-end, against the deployed agent)
1. "My courses are OS (3 credits: quizzes 15, assignments 15, midterm 30, final 40) and Calculus (4 credits: quizzes 20, midterm 30, final 50)." → both saved; `list_courses` shows them.
2. "I got 12/15 in OS quizzes, 13/15 in assignments and 24/30 in the midterm." → marks recorded.
3. "What do I need in the OS final to get an A-?" → correct % with the estimate caveat.
4. "Add my DB assignment due next Friday, high priority." → task appears in Todoist with the right due date.
5. "What's due this week?" → lists that task.
6. "I have a DB project due in 2 weeks, break it down for me." → parent + 4 to 6 dated subtasks in Todoist.
7. "I finished the DB assignment." → task closed in Todoist.
8. In one message: "I have a DB project due in 2 weeks and I'm worried about my OS grade" → agent uses `break_down_project` **and** `grade_needed`/`list_courses` in the same turn.
9. Follow-up "what about Calculus?" works without restating context (session memory).
10. Unknown course, Todoist outage or bad token → friendly message, no crash.
