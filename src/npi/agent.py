"""
Launch Mitigation Advisor - a tool-calling agent (MLflow ResponsesAgent) served on Databricks Model Serving.

It answers "why is this launch at risk and what should we do?" for NPI launch managers and supply-chain
leaders. It is grounded exclusively in governed lakehouse data and the production ML models:

  get_launch_risk(npi_or_product)      -> score, tier, drivers, $ at risk          (gold_launch_risk_scores)
  get_component_readiness(npi_id)      -> BOM supply coverage / PPAP / gaps          (gold_component_readiness)
  get_mitigation_playbook()            -> executable action types + modeled effects (silver_mitigation_playbook)
  simulate_mitigations(npi_id, actions)-> WHAT-IF: re-scores the launch with the UC champion models
                                          (same feature code as the production scoring job)
  ask_genie(question)                  -> ad-hoc governed analytics via the Genie Agent

The last simulation is returned in `custom_outputs` so the app can offer one-click "commit to Lakebase".
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any, Generator

import mlflow
import pandas as pd
from mlflow.entities import SpanType
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import (ResponsesAgentRequest, ResponsesAgentResponse,
                                    ResponsesAgentStreamEvent)

try:                                    # packaged via code_paths when served
    from npi import features as F
except ImportError:                     # local dev
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from npi import features as F

CATALOG = os.environ.get("NPI_CATALOG", "andersjensen_fevm_3_catalog")
SCHEMA = os.environ.get("NPI_SCHEMA", "npi_launch_readiness")
FQ = f"{CATALOG}.{SCHEMA}"
WAREHOUSE_ID = os.environ.get("NPI_WAREHOUSE_ID", "ab67079061fe959d")
LLM_ENDPOINT = os.environ.get("NPI_LLM_ENDPOINT", "databricks-claude-sonnet-5-5")
GENIE_SPACE_ID = os.environ.get("NPI_GENIE_SPACE_ID", "")

SYSTEM_PROMPT = """You are the Launch Mitigation Advisor for Altura Bonding & Tapes supply chain.
Users are NPI launch managers, buyers and supply-chain leaders scaling new tapes from pilot to production for OEM programs.

How you work:
1. Always ground answers in tools. Never invent numbers, suppliers, dates or costs.
2. For "why is X at risk" questions: call get_launch_risk, then get_component_readiness.
3. For "what should we do": call get_mitigation_playbook, choose 2-4 actions that target the actual drivers
   (e.g. coverage shortfall -> DUAL_SOURCE_EXPEDITE or CAPACITY_RESERVATION on that material; material gap -> PULL_AHEAD_BUY
   or DUAL_SOURCE_EXPEDITE; yield gap -> YIELD_SPRINT; line utilization -> LINE_REALLOCATION), then ALWAYS call
   simulate_mitigations to quantify the risk reduction before recommending. If the first package leaves risk HIGH,
   try one improved package (max 2 simulations).
4. Use ask_genie only for portfolio / historical analytics questions the other tools cannot answer.
5. Answer like a senior supply-chain advisor: lead with the bottom line (risk before -> after, $ protected),
   then the 2-4 actions with owner-ready one-line rationale, then key assumptions. Keep it under ~220 words; use $M with one decimal.
   Off-topic requests (not about Altura NPI launches / supply readiness): politely decline in one sentence and offer what you can do.
6. Recommendations are proposals: a human commits them in the Control Tower (they are written to Lakebase). You cannot approve or commit actions yourself."""

TOOLS = [
    {"type": "function", "function": {"name": "get_launch_risk", "description": "Risk score, tier, top drivers, revenue and OEM platform value at risk for one active launch. Accepts an NPI id (e.g. NPI-2027-014) or product code (e.g. AFT-7200). Pass 'TOP' to list the 10 highest revenue-at-risk launches.",
     "parameters": {"type": "object", "properties": {"launch": {"type": "string"}}, "required": ["launch"]}}},
    {"type": "function", "function": {"name": "get_component_readiness", "description": "BOM component supply readiness for one launch at predicted production yield: coverage, weekly shortfall, PPAP status/sources, material gap, RED/AMBER/GREEN.",
     "parameters": {"type": "object", "properties": {"npi_id": {"type": "string"}}, "required": ["npi_id"]}}},
    {"type": "function", "function": {"name": "get_mitigation_playbook", "description": "Executable mitigation action types with modeled effect and typical cost.",
     "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "simulate_mitigations", "description": "What-if: re-score a launch with the production ML models if the given mitigation actions were committed (on top of already-committed actions). Returns risk before/after and driver changes.",
     "parameters": {"type": "object", "properties": {
         "npi_id": {"type": "string"},
         "actions": {"type": "array", "items": {"type": "object", "properties": {
             "action_type": {"type": "string", "enum": ["DUAL_SOURCE_EXPEDITE", "CAPACITY_RESERVATION", "PULL_AHEAD_BUY", "YIELD_SPRINT", "LINE_REALLOCATION", "PHASED_RAMP_WITH_OEM"]},
             "material_id": {"type": ["string", "null"], "description": "Target BOM material for component-level actions; null for launch-level actions"}},
             "required": ["action_type", "material_id"]}}},
         "required": ["npi_id", "actions"]}}},
    {"type": "function", "function": {"name": "ask_genie", "description": "Ask the governed Genie Agent an analytics question about the NPI portfolio or launch history (2020-2026 outcomes).",
     "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}}},
]


def _typed(df: pd.DataFrame) -> pd.DataFrame:
    for c in df.columns:
        vals = set(df[c].dropna().astype(str).str.lower().unique())
        if vals and vals <= {"true", "false"}:
            df[c] = df[c].map(lambda v: None if v is None else str(v).lower() == "true")
            continue
        conv = pd.to_numeric(df[c], errors="coerce")
        if conv.notna().sum() == df[c].notna().sum() and df[c].notna().any():
            df[c] = conv
    return df


class LaunchMitigationAdvisor(ResponsesAgent):
    def __init__(self):
        self._w = None
        self.ymodel = None
        self.rmodel = None
        self.last_simulation: dict | None = None

    # ------------------------------------------------------------------ infra
    @property
    def w(self):
        if self._w is None:
            self._w = self._client_for_request()
        return self._w

    @staticmethod
    def _client_for_request():
        """On-behalf-of-user auth: inside Model Serving the client carries the *calling user's* identity,
        so Unity Catalog permissions, ABAC masks and row filters apply to every tool call. Outside serving
        ModelServingUserCredentials falls back to default auth (local dev / evaluation)."""
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.credentials_provider import ModelServingUserCredentials
        return WorkspaceClient(credentials_strategy=ModelServingUserCredentials())

    def load_context(self, context):
        import mlflow.sklearn
        self.ymodel = mlflow.sklearn.load_model(context.artifacts["yield_model"])
        self.rmodel = mlflow.sklearn.load_model(context.artifacts["risk_model"])

    def _models(self):
        if self.ymodel is None:
            import mlflow.sklearn
            mlflow.set_registry_uri("databricks-uc")
            self.ymodel = mlflow.sklearn.load_model(f"models:/{FQ}.npi_yield_gap_model@champion")
            self.rmodel = mlflow.sklearn.load_model(f"models:/{FQ}.npi_launch_risk_model@champion")
        return self.ymodel, self.rmodel

    def _sql(self, q: str) -> pd.DataFrame:
        from databricks.sdk.service.sql import Disposition, Format
        r = self.w.statement_execution.execute_statement(statement=q, warehouse_id=WAREHOUSE_ID, wait_timeout="50s",
                                                         format=Format.JSON_ARRAY, disposition=Disposition.INLINE)
        if r.status.error:
            raise RuntimeError(r.status.error.message)
        cols = [c.name for c in r.manifest.schema.columns]
        return _typed(pd.DataFrame((r.result.data_array if r.result else None) or [], columns=cols))

    # ------------------------------------------------------------------ tools
    @mlflow.trace(span_type=SpanType.TOOL)
    def get_launch_risk(self, launch: str) -> dict:
        if launch.strip().upper() == "TOP":
            d = self._sql(f"SELECT npi_id, product_code, oem_customer, sop_date, risk_tier, round(risk_score,3) risk_score, "
                          f"revenue_at_risk_usd, binding_component_desc FROM {FQ}.gold_launch_risk_scores ORDER BY revenue_at_risk_usd DESC LIMIT 10")
            return {"top_launches": d.to_dict("records")}
        key = launch.strip().replace("'", "")
        d = self._sql(f"SELECT * FROM {FQ}.gold_launch_risk_scores WHERE npi_id = '{key}' OR product_code = '{key}' LIMIT 1")
        if d.empty:
            return {"error": f"No active launch found for '{launch}'"}
        r = d.iloc[0].to_dict()
        r["top_drivers"] = json.loads(r.pop("top_drivers_json") or "[]")
        b = self._sql(f"SELECT headline FROM {FQ}.gold_launch_briefs WHERE npi_id = '{r['npi_id']}'")
        r["brief_headline"] = None if b.empty else b.iloc[0, 0]
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}

    @mlflow.trace(span_type=SpanType.TOOL)
    def get_component_readiness(self, npi_id: str) -> dict:
        d = self._sql(f"""SELECT material_id, material_desc, material_category, uom, is_novel_material, lead_time_weeks, sources,
                                 n_sources_qualified_by_peak, latest_pending_qualification_date, round(coverage_at_pilot_yield,3) coverage_at_pilot_yield,
                                 round(coverage_at_predicted_yield,3) coverage_at_predicted_yield, weekly_shortfall_at_peak, material_gap_weeks, readiness_status
                          FROM {FQ}.gold_component_readiness WHERE npi_id = '{npi_id.replace("'", "")}' ORDER BY coverage_at_predicted_yield""")
        return {"npi_id": npi_id, "components": d.to_dict("records")}

    @mlflow.trace(span_type=SpanType.TOOL)
    def get_mitigation_playbook(self) -> dict:
        return {"playbook": self._sql(f"SELECT * FROM {FQ}.silver_mitigation_playbook").to_dict("records")}

    @mlflow.trace(span_type=SpanType.TOOL)
    def simulate_mitigations(self, npi_id: str, actions: list[dict]) -> dict:
        ym, rm = self._models()
        nid = npi_id.replace("'", "")
        pf = self._sql(f"SELECT * FROM {FQ}.gold_launch_portfolio WHERE npi_id = '{nid}' AND launch_status = 'ACTIVE'")
        if pf.empty:
            return {"error": f"{npi_id} is not an active launch"}
        comp = self._sql(f"SELECT * FROM {FQ}.gold_launch_component_supply WHERE npi_id = '{nid}'")
        committed = self._sql(f"SELECT npi_id, material_id, action_type, status FROM {FQ}.v_mitigation_actions_current "
                              f"WHERE npi_id = '{nid}' AND status IN ('APPROVED','IN_PROGRESS','DONE')")
        play = self._sql(f"SELECT action_type, effect_json FROM {FQ}.silver_mitigation_playbook").set_index("action_type").effect_json
        committed["effect_json"] = committed.action_type.map(play)
        prop = pd.DataFrame([{"npi_id": nid, "material_id": a.get("material_id") or None, "action_type": a["action_type"],
                              "status": "APPROVED", "effect_json": play.get(a["action_type"], "{}")} for a in actions])
        pf = pf.reset_index(drop=True)
        gap = pd.Series(ym.predict(F.yield_matrix(pf)), index=pf.index).clip(lower=0)
        base_y, _ = F.blend_trial_yield(pf, pf.pilot_yield_pct - gap)

        def run(acts):
            p2, c2 = F.apply_actions(pf, comp, acts if len(acts) else None)
            py = (base_y + p2.yield_gain_pts).clip(upper=p2.pilot_yield_pct)
            cr = F.component_risk(p2, c2, py)
            lf = F.launch_features(p2, cr, py)
            return float(rm.predict_proba(lf[F.RISK_FEATURES])[:, 1][0]), lf.iloc[0], cr

        before, fb, _ = run(committed)
        after, fa, cra = run(pd.concat([committed, prop], ignore_index=True))
        rev = float(pf.year1_revenue_usd.iloc[0])
        tier = lambda p: "HIGH" if p >= 0.6 else "MEDIUM" if p >= 0.25 else "LOW"
        out = {"npi_id": nid, "risk_before": round(before, 3), "risk_after": round(after, 3),
               "tier_before": tier(before), "tier_after": tier(after),
               "revenue_at_risk_before_usd": round(before * rev), "revenue_at_risk_after_usd": round(after * rev),
               "drivers_before": {k: round(float(fb[k]), 2) for k in ["min_coverage_at_predicted_yield", "worst_material_gap_weeks", "predicted_yield_gap_pts", "n_single_source_components"]},
               "drivers_after": {k: round(float(fa[k]), 2) for k in ["min_coverage_at_predicted_yield", "worst_material_gap_weeks", "predicted_yield_gap_pts", "n_single_source_components"]},
               "new_binding_component": cra.sort_values("coverage_at_predicted_yield").iloc[0].material_desc,
               "proposed_actions": actions, "already_committed_actions": int(len(committed))}
        self.last_simulation = out
        return out

    @mlflow.trace(span_type=SpanType.TOOL)
    def ask_genie(self, question: str) -> dict:
        if not GENIE_SPACE_ID:
            return {"error": "Genie space not configured"}
        m = self.w.genie.start_conversation_and_wait(GENIE_SPACE_ID, question)
        out = {"answer": None, "sql": None, "rows": None}
        for att in m.attachments or []:
            if att.text:
                out["answer"] = att.text.content
            if att.query:
                out["sql"] = att.query.query
                qr = self.w.genie.get_message_attachment_query_result(GENIE_SPACE_ID, m.conversation_id, m.message_id, att.attachment_id)
                cols = [c.name for c in qr.statement_response.manifest.schema.columns]
                out["rows"] = [dict(zip(cols, r)) for r in (qr.statement_response.result.data_array or [])[:20]]
        return out

    # ------------------------------------------------------------------ agent loop
    @mlflow.trace(span_type=SpanType.CHAT_MODEL, name="llm")
    def _llm(self, msgs: list[dict]) -> dict:
        """OpenAI-compatible chat completion against a Databricks Foundation Model endpoint (no extra SDKs)."""
        r = self.w.api_client.do("POST", f"/serving-endpoints/{LLM_ENDPOINT}/invocations",
                                 body={"messages": msgs, "tools": TOOLS, "max_tokens": 2500})
        return r["choices"][0]["message"]

    def _call_tool(self, name: str, args: dict) -> str:
        try:
            res = getattr(self, name)(**args)
        except Exception as e:  # surface tool errors to the LLM instead of failing the request
            res = {"error": f"{type(e).__name__}: {e}"}
        return json.dumps(res, default=str)

    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        outputs = [e.item for e in self.predict_stream(request) if e.type == "response.output_item.done"]
        return ResponsesAgentResponse(output=outputs, custom_outputs={"simulation": self.last_simulation})

    def predict_stream(self, request: ResponsesAgentRequest) -> Generator[ResponsesAgentStreamEvent, None, None]:
        self.last_simulation = None
        self._w = self._client_for_request()   # fresh per request: never reuse one user's identity for another
        msgs: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}] + self.prep_msgs_for_cc_llm(
            [i.model_dump() if hasattr(i, "model_dump") else i for i in request.input])
        for _ in range(10):
            msg = self._llm(msgs)
            calls = msg.get("tool_calls") or []
            if calls:
                msgs.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
                for tc in calls:
                    fn = tc["function"]
                    args = json.loads(fn.get("arguments") or "{}")
                    yield ResponsesAgentStreamEvent(type="response.output_item.done", item=self.create_function_call_item(
                        id=str(uuid.uuid4()), call_id=tc["id"], name=fn["name"], arguments=fn.get("arguments") or "{}"))
                    result = self._call_tool(fn["name"], args)
                    msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                    yield ResponsesAgentStreamEvent(type="response.output_item.done", item=self.create_function_call_output_item(
                        call_id=tc["id"], output=result))
                continue
            text = msg.get("content") or ""
            if isinstance(text, list):   # content blocks
                text = "".join(b.get("text", "") for b in text if isinstance(b, dict))
            yield ResponsesAgentStreamEvent(type="response.output_item.done",
                                            item=self.create_text_output_item(text=text, id=str(uuid.uuid4())))
            return
        yield ResponsesAgentStreamEvent(type="response.output_item.done", item=self.create_text_output_item(
            text="I could not complete the analysis within the tool-call budget.", id=str(uuid.uuid4())))


AGENT = LaunchMitigationAdvisor()
mlflow.models.set_model(AGENT)
