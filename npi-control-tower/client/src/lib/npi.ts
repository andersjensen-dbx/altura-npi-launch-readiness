import { useMemo, useCallback, useEffect, useState } from 'react';

export type RiskTier = 'HIGH' | 'MEDIUM' | 'LOW';
export type ActionStatus = 'PROPOSED' | 'APPROVED' | 'IN_PROGRESS' | 'DONE' | 'REJECTED';

export interface LaunchRow {
  npi_id: string;
  product_code: string;
  product_name: string;
  family_name: string;
  market_segment: string;
  oem_customer: string;
  oem_program: string;
  region: string;
  plant: string;
  production_line: string;
  sop_date: string;
  weeks_to_sop: number;
  current_gate: string;
  npi_manager: string;
  year1_revenue_usd: number;
  program_lifetime_value_usd: number;
  risk_score: number;
  baseline_risk_score: number;
  risk_tier: RiskTier;
  revenue_at_risk_usd: number;
  platform_value_at_risk_usd: number;
  binding_component_desc: string;
  predicted_yield_gap_pts: number;
  min_coverage_at_predicted_yield: number;
  worst_material_gap_weeks: number;
  actions_applied: number;
  scored_at: string;
  open_actions?: number;
}
export interface LaunchScore extends LaunchRow {
  pilot_yield_pct: number;
  production_trial_yield_pct: number | null;
  predicted_yield_pct: number;
  yield_basis: string;
  planned_line_utilization: number;
  n_single_source_components: number;
  n_unqualified_components: number;
  top_drivers_json: string;
  risk_model_version: number;
}
export interface ComponentRow {
  material_id: string;
  material_desc: string;
  material_category: string;
  uom: string;
  is_novel_material: boolean;
  lead_time_weeks: number;
  sources: string;
  n_sources_qualified_by_peak: number;
  latest_pending_qualification_date: string | null;
  coverage_at_pilot_yield: number;
  coverage_at_predicted_yield: number;
  weekly_shortfall_at_peak: number;
  material_gap_weeks: number;
  readiness_status: 'RED' | 'AMBER' | 'GREEN';
  open_po_qty: number | null;
}
export interface CurvePoint {
  week_rel_sop: number;
  week_start: string;
  oem_demand_m2: number;
  supportable_output_m2: number;
  shortfall_m2: number;
  binding_component_desc: string;
}
export interface Brief {
  headline: string;
  situation: string;
  business_impact: string;
  recommended_actions_json: string;
  supplier_questions_json: string;
  llm_endpoint: string;
  generated_at: string;
}
export interface ActionRow {
  action_id: string;
  npi_id: string;
  material_id: string | null;
  action_type: string;
  title: string;
  rationale: string | null;
  status: ActionStatus;
  owner: string | null;
  due_date: string | null;
  estimated_cost_usd: number | null;
  source: 'MANUAL' | 'AI_ADVISOR';
  created_by: string;
  created_at: string;
  updated_at: string;
  product_code?: string;
  oem_customer?: string;
  risk_tier?: RiskTier;
}
export interface HistoryPoint {
  scored_at: string;
  risk_score: number;
  baseline_risk_score: number;
  actions_applied: number;
}
export interface LaunchDetail {
  score: LaunchScore;
  components: ComponentRow[];
  curve: CurvePoint[];
  brief: Brief | null;
  actions: ActionRow[];
  history: HistoryPoint[];
}
export interface Driver {
  feature: string;
  label: string;
  impact: number;
  detail: string;
}
export interface RecommendedAction {
  action_type: string;
  material_id?: string | null;
  title: string;
  why: string;
}
export interface Simulation {
  npi_id: string;
  risk_before: number;
  risk_after: number;
  tier_before: RiskTier;
  tier_after: RiskTier;
  revenue_at_risk_before_usd: number;
  revenue_at_risk_after_usd: number;
  proposed_actions: Array<{ action_type: string; material_id: string | null }>;
  new_binding_component: string;
}
export interface AdvisorReply {
  answer: string;
  tools: string[];
  simulation: Simulation | null;
}

export const ACTION_LABEL: Record<string, string> = {
  DUAL_SOURCE_EXPEDITE: 'Dual-source expedite (PPAP fast-track)',
  CAPACITY_RESERVATION: 'Supplier capacity reservation',
  PULL_AHEAD_BUY: 'Pull-ahead buy / safety stock',
  YIELD_SPRINT: 'Production yield sprint',
  LINE_REALLOCATION: 'Coating line reallocation',
  PHASED_RAMP_WITH_OEM: 'Phased ramp with OEM',
};

// ---------- formatting (Postgres numerics arrive as strings) ----------
export const num = (v: unknown): number => (v === null || v === undefined || v === '' ? NaN : Number(v));
export const usdM = (v: unknown, d = 1) => {
  const n = num(v);
  return Number.isFinite(n) ? `$${(n / 1e6).toFixed(d)}M` : '—';
};
/** Supply coverage: sources with ample headroom are capped upstream (9.99); show them as ">200%" instead of a sentinel. */
export const covPct = (v: unknown) => {
  const n = num(v);
  return Number.isFinite(n) && n > 2 ? '>200%' : pct(n);
};
export const pct = (v: unknown, d = 0) => {
  const n = num(v);
  return Number.isFinite(n) ? `${(n * 100).toFixed(d)}%` : '—';
};
export const fixed = (v: unknown, d = 1) => {
  const n = num(v);
  return Number.isFinite(n) ? n.toFixed(d) : '—';
};
export const dateFmt = (v: string | null | undefined) =>
  v ? new Date(v.length <= 10 ? `${v}T00:00:00` : v).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : '—';
export const dateTimeFmt = (v: string | null | undefined) =>
  v ? new Date(v).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
export const parseJson = <T,>(s: string | null | undefined, fallback: T): T => {
  try {
    return s ? (JSON.parse(s) as T) : fallback;
  } catch {
    return fallback;
  }
};

// ---------- data hooks ----------
function errorOf(body: unknown): string | undefined {
  if (typeof body === 'object' && body !== null && 'error' in body) {
    const e = (body as { error?: unknown }).error;
    return typeof e === 'string' ? e : undefined;
  }
  return undefined;
}
export function useApi<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => {
    if (!path) return;
    let alive = true;
    setLoading(true);
    fetch(path)
      .then(async (r) => {
        const body: unknown = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(errorOf(body) ?? `HTTP ${r.status}`);
        return body as T;
      })
      .then((d) => {
        if (alive) {
          setData(d);
          setError(null);
        }
      })
      .catch((e: unknown) => alive && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick, ...deps]);
  return { data, error, loading, reload };
}

export async function apiSend<T>(path: string, method: 'POST' | 'PATCH' | 'DELETE', body?: unknown): Promise<T> {
  const r = await fetch(path, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
  const j: unknown = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(errorOf(j) ?? `HTTP ${r.status}`);
  return j as T;
}

/**
 * Theme tokens are oklch(). Canvas can paint them, but ECharts cannot parse them when it derives hover/emphasis
 * colors, so hovered bars and lines turned transparent. Rasterize each token to one pixel and return rgb()/rgba().
 */
function toRgb(color: string): string {
  if (!color) return color;
  const c = document.createElement('canvas');
  c.width = 1;
  c.height = 1;
  const ctx = c.getContext('2d', { willReadFrequently: true });
  if (!ctx) return color;
  ctx.clearRect(0, 0, 1, 1);
  ctx.fillStyle = '#000';
  ctx.fillStyle = color;
  ctx.fillRect(0, 0, 1, 1);
  const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
  return a === 255 ? `rgb(${r}, ${g}, ${b})` : `rgba(${r}, ${g}, ${b}, ${(a / 255).toFixed(3)})`;
}

/** Resolve design tokens (CSS custom properties) to concrete colors for ECharts, so charts follow the theme. */
export function useTokenColors(vars: string[]): string[] | undefined {
  const [colors, setColors] = useState<string[] | undefined>(undefined);
  const key = vars.join('|');
  useEffect(() => {
    const read = () => {
      const cs = getComputedStyle(document.documentElement);
      setColors(key.split('|').map((v) => toRgb(cs.getPropertyValue(v).trim())).filter(Boolean));
    };
    read();
    const mo = new MutationObserver(read);   // theme toggle swaps the class on <html>
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => mo.disconnect();
  }, [key]);
  return colors;
}

/** Chart "ink" from theme tokens (rgb, follows light/dark): strong labels, muted labels, grid lines. */
export function useChartInk() {
  const c = useTokenColors(['--foreground', '--muted-foreground', '--border', '--destructive']);
  return useMemo(() => {
    const [strong, muted, grid, alert] = c ?? ['#3f3f46', '#71717a', '#e4e4e7', '#b91c1c'];
    return { strong, muted, grid, alert };
  }, [c]);
}
