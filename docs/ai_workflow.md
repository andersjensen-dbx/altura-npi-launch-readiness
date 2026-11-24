# How AI was used to build this (AI as a teammate)

## Tools
- **Claude Code** (Anthropic Opus) in the terminal was the primary pair-programmer and operator. It wrote code, ran it against the workspace, read the results and iterated.
- **Databricks AI Dev Kit skills** loaded into Claude Code: `databricks-core`, `databricks-pipelines`, `databricks-dabs`, `databricks-jobs`, `databricks-lakebase`, `databricks-apps` + `databricks-app-design`, `databricks-genie-agents`, `databricks-metric-views`, `databricks-synthetic-data-gen`, `databricks-setup-local`. These supply current API shapes, such as SDP SQL syntax, synced-table specs, AppKit plugin manifests and the Genie serialized-space format, so code was right first time far more often.
- **FE Vending Machine MCP** for the workspace lifecycle and a short-lived metastore grant (Lakebase catalog registration).
- **Databricks CLI / SDK / Databricks Connect (serverless)**. Notebooks run locally against serverless compute so their outputs are committed as evidence.
- **AI inside the product**: Databricks FMAPI (Claude Sonnet 5.5 agent, GPT-5.5 batch briefs, Claude Opus 5.5 as LLM judge), MLflow 3 (tracing, `genai.evaluate`, Prompt Registry), Genie.

## Workflow
1. **Framing with the AI**: I set the customer (Altura), the vertical and the FE Bar rubric. We narrowed "pilot-to-production scale-up" into four supply failure modes and picked material/supplier readiness × yield gap for OEM-specified tapes, because it has the clearest dollar story.
2. **Data contract first**: designed source-system-shaped extracts (SAP field names, MES JSON, PLM gates, EDI demand) with a *causal* outcome model. The ML then has real signal and the hero launch reads like a real escalation.
3. **Build → run → read → fix loop**: every artifact was executed immediately against fevm-3, with outputs inspected by the assistant. Examples of AI-caught issues fixed in the loop:
   - The risk score counted supplier capacity "by SOP" while the ramp chart included a supplier qualifying at SOP+4. This was caught by looking at the rendered app chart, and fixed by moving to one definition (capacity qualified by ramp peak) end to end.
   - A synced-table stream broke after governance DDL changed source nullability. Fixed by making governance idempotent and setting keys at table creation.
   - FMAPI Claude rejected JSON-schema structured output, so a GPT endpoint is used for batch briefs.
   - Automatic credential passthrough failed against ABAC-governed tables, so the agent moved to on-behalf-of-user auth (a better governance story).
   - **Testing the deployed app as a signed-in user** (Claude Code driving the presenter's own Chrome) found issues that local runs could not:
     - AppKit 0.76.1 `serving(...).asUser(req).invoke` executes outside the user context, so the agent silently ran as the app service principal and UC denied it. The route now forwards the user's token to the endpoint.
     - The served what-if tool failed (see decision 19), now blocked by a packaged-artifact release gate.
     - Charts vanished on hover because ECharts cannot parse oklch theme colors; tokens are converted to rgb.
     - UX polish from page-by-page review: example questions insert into the chat box, readable statuses and units, no duplicate proposals, a Withdraw action, write errors surfaced, laptop-width (1280px) layout, light/dark theme toggle.
   - The Genie benchmark went from 11/12 to 12/12 via instruction tuning and relaxing an over-specified benchmark; each run is logged in `evidence/genie_benchmarks.md`.
4. **Evaluation as a gate**: the agent ships only after `mlflow.genai.evaluate` passes on code scorers (tools used, simulation before recommendation, numbers grounded in tool output, guardrails) plus an LLM-judge executive-quality score.
5. **Human decisions kept human**: naming ("Mitigation Advisor"), what to build, permissions (identity creation was escalated, not worked around), and commit/push.

## Prompt patterns that worked
- *"Ground every number in a tool; never invent suppliers, dates, costs"* plus a code scorer that checks quoted risk % against tool outputs.
- *Constrain generation to an executable vocabulary*: briefs and the agent can only recommend playbook action types, and a quality gate validates action types and target materials.
- *Simulate before recommending*: the agent must call `simulate_mitigations` (real UC models) before proposing a package, and may try one improved package.
- *Executive altitude*: "lead with the bottom line (risk before → after, $ protected), then 2-4 owner-ready actions".
