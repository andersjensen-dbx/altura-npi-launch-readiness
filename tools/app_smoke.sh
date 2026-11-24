#!/usr/bin/env bash
# Smoke-test the Control Tower API (same server code as the deployed app) against live Lakebase / Jobs / Model Serving.
# Usage: tools/app_smoke.sh [base_url]  (default: local dev server on :8000)
set -euo pipefail
B="${1:-http://localhost:8000}"
echo "# App API smoke test ($(date -u '+%Y-%m-%d %H:%M UTC'))"
echo; echo "Base URL: \`$B\` · server code: \`npi-control-tower/server/routes/npi-routes.ts\`"
echo; echo "## GET /api/portfolio (Lakebase serving.launch_risk_scores)"; echo '```'
curl -s "$B/api/portfolio" | jq -r '"launches: \(.launches|length)", (.launches[:5][] | "\(.product_code)\t\(.oem_customer)\t\(.risk_tier)\t risk=\(.risk_score)\t revenue_at_risk=\(.revenue_at_risk_usd)\t bottleneck=\(.binding_component_desc)")'
echo '```'; echo; echo "## GET /api/launches/NPI-2027-014 (scores + components + ramp curve + brief + actions + history)"; echo '```'
curl -s "$B/api/launches/NPI-2027-014" | jq -r '"product: \(.score.product_name)", "risk: \(.score.risk_score) (\(.score.risk_tier))  predicted_yield: \(.score.predicted_yield_pct)", "components: \(.components|length)  curve_weeks: \(.curve|length)  actions: \(.actions|length)  history_points: \(.history|length)", "brief: \(.brief.headline)", (.components[:3][] | "  \(.material_desc): \(.readiness_status) coverage@pred=\(.coverage_at_predicted_yield)")'
echo '```'; echo; echo "## GET /api/actions (Lakebase ops.mitigation_actions)"; echo '```'
curl -s "$B/api/actions" | jq -r '"actions: \(.actions|length)", (.actions[:4][] | "  \(.product_code)\t\(.action_type)\t\(.status)\t\(.source)")'
echo '```'; echo; echo "## GET /api/jobs/default/runs (Lakeflow Job: rescore-on-action)"; echo '```'
curl -s "$B/api/jobs/default/runs?limit=3" | jq -r '.runs[] | "run \(.run_id)  \(.trigger // "")  \(.state.result_state // .state.life_cycle_state)"'
echo '```'; echo; echo "## POST /api/advisor (Model Serving: npi-mitigation-advisor)"; echo '```'
curl -s -X POST "$B/api/advisor" -H 'Content-Type: application/json' -d '{"question":"In two sentences, why is AFT-7200 at risk?","npi_id":"NPI-2027-014"}' | jq -r '"tools: \(.tools|join(", "))", "answer: \(.answer)"'
echo '```'
