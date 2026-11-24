/**
 * NPI Launch Readiness Control Tower - API routes.
 *
 * Reads:  Lakebase `serving.*`  (Lakebase synced tables, fed from Unity Catalog gold tables after every scoring run)
 * Writes: Lakebase `ops.*`      (native OLTP: mitigation actions + gate sign-offs; flows back to UC via Lakehouse Sync)
 * AI:     Model Serving endpoint `npi-mitigation-advisor` (tool-calling agent, invoked on behalf of the user)
 */
import { z } from 'zod';
import type { Application, Request } from 'express';

type Row = Record<string, unknown>;
export interface NpiAppKit {
  lakebase: { query(text: string, params?: unknown[]): Promise<{ rows: Row[] }> };
  server: { extend(fn: (app: Application) => void): void };
  serving: (alias?: string) => {
    invoke: (body: Record<string, unknown>) => Promise<unknown>;
    asUser: (req: Request) => { invoke: (body: Record<string, unknown>) => Promise<unknown> };
  };
}

const ACTION_TYPES = [
  'DUAL_SOURCE_EXPEDITE',
  'CAPACITY_RESERVATION',
  'PULL_AHEAD_BUY',
  'YIELD_SPRINT',
  'LINE_REALLOCATION',
  'PHASED_RAMP_WITH_OEM',
] as const;
const STATUSES = ['PROPOSED', 'APPROVED', 'IN_PROGRESS', 'DONE', 'REJECTED'] as const;

const CreateAction = z.object({
  npi_id: z.string().min(1),
  material_id: z.string().nullable().optional(),
  action_type: z.enum(ACTION_TYPES),
  title: z.string().min(3).max(300),
  rationale: z.string().max(4000).optional(),
  status: z.enum(STATUSES).default('PROPOSED'),
  owner: z.string().max(200).optional(),
  due_date: z.string().optional(),
  source: z.enum(['MANUAL', 'AI_ADVISOR']).default('MANUAL'),
  expected_risk_reduction: z.number().min(-1).max(1).optional(),
});
const UpdateAction = z.object({ status: z.enum(STATUSES).optional(), owner: z.string().max(200).optional() });
const AdvisorBody = z.object({ question: z.string().min(2).max(2000), npi_id: z.string().optional() });

const userOf = (req: Request) =>
  req.header('x-forwarded-email') ?? req.header('x-forwarded-user') ?? 'local.developer@altura-demo';

function wrap(fn: (req: Request) => Promise<unknown>) {
  return async (req: Request, res: import('express').Response) => {
    try {
      res.json(await fn(req));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error('[npi-api]', req.method, req.path, msg);
      res.status(500).json({ error: msg });
    }
  };
}

interface AdvisorOutputItem {
  type?: string;
  name?: string;
  content?: Array<{ text?: string }>;
}
interface AdvisorResponse {
  output?: AdvisorOutputItem[];
  custom_outputs?: { simulation?: unknown };
}
function unwrap(v: unknown): unknown {
  if (typeof v === 'object' && v !== null && 'data' in v && !('output' in v)) return (v as { data: unknown }).data;
  return v;
}
function isAdvisorResponse(v: unknown): v is AdvisorResponse {
  return typeof v === 'object' && v !== null && 'output' in v;
}

export function setupNpiRoutes(appkit: NpiAppKit) {
  const q = async (sql: string, params?: unknown[]) => (await appkit.lakebase.query(sql, params)).rows;

  /**
   * Invoke the advisor endpoint with the signed-in user's forwarded token (on-behalf-of-user), so the agent's
   * tool calls run under the caller's Unity Catalog permissions (ABAC masks + row filters apply).
   * Calls the REST API directly: in AppKit 0.76.1 `serving(alias).asUser(req).invoke` returns a function that
   * executes outside the user context and silently falls back to the app service principal.
   * Local dev (no forwarded token) falls back to the plugin, which uses the developer's own credentials.
   */
  const invokeAdvisorAsUser = async (req: Request, body: Record<string, unknown>): Promise<unknown> => {
    const token = req.header('x-forwarded-access-token')?.trim();
    const endpoint = process.env.DATABRICKS_SERVING_ENDPOINT_NAME;
    const rawHost = process.env.DATABRICKS_HOST;
    if (!token || !endpoint || !rawHost) return appkit.serving('advisor').invoke(body);
    const host = rawHost.startsWith('http') ? rawHost.replace(/\/$/, '') : `https://${rawHost}`;
    const r = await fetch(`${host}/serving-endpoints/${encodeURIComponent(endpoint)}/invocations`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(240_000),
    });
    const text = await r.text();
    if (!r.ok) throw new Error(`Advisor endpoint returned ${r.status}: ${text.slice(0, 300)}`);
    return JSON.parse(text) as unknown;
  };

  appkit.server.extend((app) => {
    app.get('/api/whoami', (req, res) => {
      res.json({ email: req.header('x-forwarded-email') ?? null, user: req.header('x-forwarded-user') ?? null });
    });

    // ---------------- portfolio ----------------
    app.get(
      '/api/portfolio',
      wrap(async () => {
        const launches = await q(`
          SELECT s.npi_id, s.product_code, s.product_name, s.family_name, s.market_segment, s.oem_customer, s.oem_program,
                 s.region, s.plant, s.production_line, s.sop_date::text AS sop_date, s.weeks_to_sop, s.current_gate, s.npi_manager,
                 s.year1_revenue_usd, s.program_lifetime_value_usd, s.risk_score, s.baseline_risk_score, s.risk_tier,
                 s.revenue_at_risk_usd, s.platform_value_at_risk_usd, s.binding_component_desc, s.predicted_yield_gap_pts,
                 s.min_coverage_at_predicted_yield, s.worst_material_gap_weeks, s.actions_applied, s.scored_at::text AS scored_at,
                 coalesce(a.open_actions, 0) AS open_actions
          FROM serving.launch_risk_scores s
          LEFT JOIN (SELECT npi_id, count(*) AS open_actions FROM ops.mitigation_actions
                     WHERE status IN ('PROPOSED','APPROVED','IN_PROGRESS') GROUP BY npi_id) a USING (npi_id)
          ORDER BY s.revenue_at_risk_usd DESC`);
        return { launches };
      }),
    );

    // ---------------- launch detail ----------------
    app.get(
      '/api/launches/:npiId',
      wrap(async (req) => {
        const id = String(req.params.npiId);
        const [score] = await q(
          `SELECT s.*, s.sop_date::text AS sop_date_txt, s.scored_at::text AS scored_at_txt FROM serving.launch_risk_scores s WHERE s.npi_id = $1`,
          [id],
        );
        if (!score) throw new Error(`Launch ${id} not found`);
        score.sop_date = score.sop_date_txt;   // DATE as plain text (avoid TZ shift in JSON)
        score.scored_at = score.scored_at_txt;
        const [components, curve, briefRows, actions, history] = await Promise.all([
          q(`SELECT * FROM serving.component_readiness WHERE npi_id = $1 ORDER BY coverage_at_predicted_yield`, [id]),
          q(`SELECT week_rel_sop, week_start::text AS week_start, oem_demand_m2, supportable_output_m2, shortfall_m2,
                    component_need_at_predicted_yield, component_supply_available, binding_component_desc
             FROM serving.ramp_supply_curve WHERE npi_id = $1 ORDER BY week_rel_sop`, [id]),
          q(`SELECT headline, situation, business_impact, recommended_actions_json, supplier_questions_json, llm_endpoint,
                    generated_at::text AS generated_at
             FROM serving.launch_briefs WHERE npi_id = $1`, [id]),
          q(`SELECT a.action_id, a.npi_id, a.material_id, a.action_type, a.title, a.rationale, a.status, a.owner,
                    a.estimated_cost_usd, a.source, a.created_by, a.due_date::text AS due_date,
                    a.created_at::text AS created_at, a.updated_at::text AS updated_at
             FROM ops.mitigation_actions a WHERE a.npi_id = $1 ORDER BY a.created_at DESC`, [id]),
          q(`SELECT scored_at::text AS scored_at, risk_score, baseline_risk_score, actions_applied
             FROM serving.launch_risk_history WHERE npi_id = $1 ORDER BY scored_at`, [id]),
        ]);
        return { score, components, curve, brief: briefRows[0] ?? null, actions, history };
      }),
    );

    // ---------------- mitigation actions (Lakebase OLTP write-back) ----------------
    app.get(
      '/api/actions',
      wrap(async () => {
        const actions = await q(`
          SELECT a.action_id, a.npi_id, a.material_id, a.action_type, a.title, a.rationale, a.status, a.owner,
                 a.estimated_cost_usd, a.source, a.created_by,
                 a.due_date::text AS due_date, a.created_at::text AS created_at, a.updated_at::text AS updated_at,
                 s.product_code, s.oem_customer, s.risk_tier, s.risk_score, s.sop_date::text AS sop_date
          FROM ops.mitigation_actions a LEFT JOIN serving.launch_risk_scores s USING (npi_id)
          ORDER BY CASE a.status WHEN 'PROPOSED' THEN 0 WHEN 'APPROVED' THEN 1 WHEN 'IN_PROGRESS' THEN 2 ELSE 3 END,
                   a.updated_at::timestamptz DESC`);
        return { actions };
      }),
    );
    app.get('/api/playbook', wrap(async () => ({ playbook: await q(`SELECT * FROM serving.mitigation_playbook ORDER BY action_type`) })));

    app.post(
      '/api/actions',
      wrap(async (req) => {
        const b = CreateAction.parse(req.body);
        const [play] = await q(`SELECT effect_json, typical_cost_usd FROM serving.mitigation_playbook WHERE action_type = $1`, [b.action_type]);
        const [row] = await q(
          `INSERT INTO ops.mitigation_actions (npi_id, material_id, action_type, title, rationale, status, owner, due_date,
                                               estimated_cost_usd, expected_risk_reduction, effect_json, source, created_by)
           VALUES ($1,$2,$3,$4,$5,$6,$7, COALESCE($8::date, CURRENT_DATE + 21), $9, $10, COALESCE($11::jsonb, '{}'::jsonb), $12, $13)
           RETURNING *`,
          [b.npi_id, b.material_id ?? null, b.action_type, b.title, b.rationale ?? null, b.status, b.owner ?? null,
           b.due_date ?? null, play?.typical_cost_usd ?? null, b.expected_risk_reduction ?? null,
           play?.effect_json ?? null, b.source, userOf(req)],
        );
        return row;
      }),
    );

    app.patch(
      '/api/actions/:id',
      wrap(async (req) => {
        const b = UpdateAction.parse(req.body);
        const [row] = await q(
          `UPDATE ops.mitigation_actions SET status = COALESCE($2, status), owner = COALESCE($3, owner), updated_at = now()
           WHERE action_id = $1 RETURNING *`,
          [String(req.params.id), b.status ?? null, b.owner ?? null],
        );
        if (!row) throw new Error('Action not found');
        return row;
      }),
    );

    // Withdraw a proposal made by mistake. Only PROPOSED actions can be withdrawn; once approved they are part of the
    // decision record (reject instead). The delete still flows to Unity Catalog as CDC through Lakehouse Sync.
    app.delete(
      '/api/actions/:id',
      wrap(async (req) => {
        const [row] = await q(
          `DELETE FROM ops.mitigation_actions WHERE action_id = $1 AND status = 'PROPOSED' RETURNING action_id, title`,
          [String(req.params.id)],
        );
        if (!row) throw new Error('Only proposed actions can be withdrawn');
        return row;
      }),
    );

    // ---------------- Mitigation Advisor (agent on Model Serving, on behalf of the user) ----------------
    app.post(
      '/api/advisor',
      wrap(async (req) => {
        const b = AdvisorBody.parse(req.body);
        const content = b.npi_id ? `[Context: launch ${b.npi_id}] ${b.question}` : b.question;
        const raw = await invokeAdvisorAsUser(req, { input: [{ role: 'user', content }] });
        const resp = unwrap(raw);   // the serving plugin returns { ok, data }
        if (!isAdvisorResponse(resp)) {
          console.error('[npi-api] advisor raw response:', JSON.stringify(resp).slice(0, 800));
          throw new Error('Unexpected advisor response');
        }
        const answer = (resp.output ?? [])
          .filter((o) => o.type === 'message')
          .map((o) => (o.content ?? []).map((c) => c.text ?? '').join(''))
          .join('\n');
        const tools = (resp.output ?? []).filter((o) => o.type === 'function_call').map((o) => o.name ?? '');
        return { answer, tools, simulation: resp.custom_outputs?.simulation ?? null };
      }),
    );
  });
}
