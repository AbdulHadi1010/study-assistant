# Kickoff Prompt for Claude Code

Copy everything below the line into Claude Code, started in an empty folder that contains these spec files.

---

You are building **Study Assistant**, a production-grade personal AI assistant for university students, built on Amazon Bedrock Agents. It will be used as the codebase for a live, online beginner workshop (LUMS Student Builder Group), so it must work first time on a fresh AWS account and be easy for first- and second-year students to follow.

Read these files in this folder before writing any code, in this order:

1. `CLAUDE.md`: project rules and conventions
2. `SPEC.md`: what the product does, features, data model, acceptance criteria
3. `TECH_STACK.md`: services, versions, libraries, and what is not allowed
4. `AGENT.md`: Bedrock Agent instructions, action groups, and the exact function definitions
5. `INSTRUCTIONS.md`: build order, repo layout, live-coding markers, scripts
6. `TESTING.md`: unit tests, integration tests, and the definition of done
7. `WORKSHOP.md`: how the repo will be used in the session (context for design decisions)

Then:

1. Create a short implementation plan and a task list covering every phase in `INSTRUCTIONS.md`.
2. Before writing AWS-specific code, verify anything that may have changed since your training data, using the AWS CLI and official docs:
   - current Bedrock model IDs / inference profile IDs that support Bedrock Agents in the chosen region (`aws bedrock list-foundation-models`, `aws bedrock list-inference-profiles`)
   - the Lambda event and response format for Bedrock Agent action groups defined with function details
   - quotas for parameters per function and functions per action group
   - the current Todoist API version, base URL, and endpoints
   Record what you verified, with links, in `docs/VERIFIED.md`. Where something differs from the spec, follow the real API and note the difference.
3. Build the complete, working **solution** first (phases 1 to 6), then generate the **starter** version from it (phase 7).
4. Run all unit tests until they pass. Do not deploy to AWS or spend money without asking me first; when I approve, deploy, run the end-to-end test script, and fix any failures.
5. Finish with a short summary: what was built, what was verified, test results, anything that deviates from the spec, and any open questions.

Ask me before: changing the architecture, adding a dependency not listed in `TECH_STACK.md`, or deploying to AWS. Otherwise make sensible decisions and note them in `docs/DECISIONS.md`.
