import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router';
import {
  Alert, AlertDescription, AlertTitle, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle,
  LineChart, Separator, Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@databricks/appkit-ui/react';
import { ArrowLeft, CheckCircle2, Plus, Sparkles } from 'lucide-react';
import { ErrorBox, Loading, NoData } from '../components/States';
import { ActionStatusBadge, ReadinessBadge, RiskBadge } from '../components/StatusBadges';
import { AdvisorPanel } from '../components/AdvisorPanel';
import { covPct,
  ACTION_LABEL, apiSend, useChartInk, useTokenColors, dateFmt, dateTimeFmt, fixed, num, parseJson, pct, useApi, usdM,
  type ActionRow, type Driver, type LaunchDetail, type RecommendedAction,
} from '../lib/npi';

export function LaunchPage() {
  const { npiId = '' } = useParams();
  const { data, error, loading, reload } = useApi<LaunchDetail>(`/api/launches/${npiId}`, [npiId]);
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const lineColors = useTokenColors(['--primary', '--foreground']);
  const ink = useChartInk();

  const curve = useMemo(
    () => (data?.curve ?? []).map((p) => ({
      week: num(p.week_rel_sop) < 0 ? `SOP−${-num(p.week_rel_sop)}` : num(p.week_rel_sop) === 0 ? 'SOP' : `+${num(p.week_rel_sop)}`,
      'Supportable output (m²/wk)': num(p.supportable_output_m2),
      'OEM demand (m²/wk)': num(p.oem_demand_m2),
    })),
    [data],
  );

  // Full ECharts option (AppKit merges `options` shallowly): unrotated week labels, a marked SOP line, the
  // supportable-output step line, and shaded shortfall weeks, which carry the chart's message.
  const curveOptions = useMemo(() => {
    const pts = data?.curve ?? [];
    const weeks = curve.map((c) => c.week);
    const supply = pts.map((p) => num(p.supportable_output_m2));
    const demand = pts.map((p) => num(p.oem_demand_m2));
    const ranges: Array<[{ xAxis: string }, { xAxis: string }]> = [];
    let start = -1;
    demand.forEach((d, i) => {
      const short = num(pts[i]?.week_rel_sop) >= 0 && d > supply[i];
      if (short && start < 0) start = i;
      if ((!short || i === demand.length - 1) && start >= 0) {
        ranges.push([{ xAxis: weeks[start] }, { xAxis: weeks[short ? i : i - 1] }]);
        start = -1;
      }
    });
    const fmt = (v: number) => Math.round(v).toLocaleString();
    return {
      grid: { left: 8, right: 24, top: 24, bottom: 48, containLabel: true },
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${fmt(v)} m²/wk` },
      legend: { bottom: 0, textStyle: { color: ink.strong } },
      xAxis: { type: 'category', data: weeks, boundaryGap: false, axisTick: { show: false },
               axisLabel: { interval: 3, color: ink.muted }, axisLine: { lineStyle: { color: ink.grid } } },
      yAxis: { type: 'value', axisLabel: { formatter: (v: number) => (v >= 1000 ? `${v / 1000}k` : String(v)), color: ink.muted },
               splitLine: { lineStyle: { color: ink.grid } } },
      series: [
        { name: 'Supportable output (m²/wk)', type: 'line', step: 'end', symbol: 'none', data: supply,
          lineStyle: { width: 2.5 }, color: lineColors?.[0] },
        { name: 'OEM demand (m²/wk)', type: 'line', symbol: 'none', smooth: true, data: demand,
          lineStyle: { width: 2 }, color: lineColors?.[1],
          markLine: { symbol: 'none', silent: true, label: { formatter: 'SOP', color: ink.muted },
                      lineStyle: { type: 'dashed', color: ink.muted }, data: [{ xAxis: 'SOP' }] },
          markArea: { silent: true, itemStyle: { color: ink.alert.replace('rgb(', 'rgba(').replace(')', ', 0.14)') },
                      label: { show: ranges.length > 0, formatter: 'Shortfall', color: ink.alert, position: 'insideTop' },
                      data: ranges } },
      ],
    };
  }, [data, curve, lineColors, ink]);

  if (loading && !data) return <Loading rows={5} />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return <NoData title="Launch not found" />;

  const s = data.score;
  const drivers = parseJson<Driver[]>(s.top_drivers_json, []);
  const recs = parseJson<RecommendedAction[]>(data.brief?.recommended_actions_json, []);
  const openKey = (t: string, m: string | null | undefined) => `${t}|${m ?? ''}`;
  const alreadyOpen = new Set(data.actions.filter((a) => a.status !== 'REJECTED').map((a) => openKey(a.action_type, a.material_id)));
  const questions = parseJson<string[]>(data.brief?.supplier_questions_json, []);
  const post = data.curve.filter((p) => num(p.week_rel_sop) >= 0);
  const peakDemand = Math.max(...post.map((p) => num(p.oem_demand_m2)), 1);
  const minSupport = Math.min(...post.map((p) => num(p.supportable_output_m2) / Math.max(num(p.oem_demand_m2), 1)));
  const shortWeeks = post.filter((p) => num(p.shortfall_m2) > 0).length;
  const binding = data.curve[0]?.binding_component_desc ?? s.binding_component_desc;

  /** Run a write, show a success or error notice, and refresh the launch. */
  async function write(key: string, fn: () => Promise<unknown>, ok: string) {
    setBusyId(key);
    try {
      await fn();
      setNotice({ kind: 'ok', text: ok });
      reload();
    } catch (e) {
      setNotice({ kind: 'error', text: `Could not save: ${e instanceof Error ? e.message : String(e)}` });
    } finally {
      setBusyId(null);
    }
  }
  const propose = (r: RecommendedAction) => write(`rec-${r.action_type}-${r.material_id ?? ''}`, () => apiSend<ActionRow>('/api/actions', 'POST', {
    npi_id: s.npi_id, material_id: r.material_id ?? null, action_type: r.action_type, title: r.title,
    rationale: r.why, status: 'PROPOSED', source: 'AI_ADVISOR', owner: s.npi_manager,
  }), `Proposed "${r.title}". Review and approve it below or in the Action Center.`);
  const setStatus = (a: ActionRow, status: ActionRow['status']) => write(a.action_id,
    () => apiSend<ActionRow>(`/api/actions/${a.action_id}`, 'PATCH', { status }),
    status === 'APPROVED'
      ? 'Approved and written to Lakebase. Lakehouse Sync streams it to Unity Catalog and the re-score job updates this launch within a few minutes.'
      : `"${a.title}" set to ${status.replace('_', ' ').toLowerCase()}.`);
  const withdraw = (a: ActionRow) => write(a.action_id, () => apiSend(`/api/actions/${a.action_id}`, 'DELETE'),
    `Withdrew "${a.title}".`);

  return (
    <div className="space-y-6">
      <Link to="/" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Launch portfolio
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>{s.npi_id}</span><span>·</span><span>{s.family_name}</span><span>·</span><Badge variant="outline">{s.current_gate}</Badge>
          </div>
          <h1 className="text-2xl font-bold text-foreground mt-1">{s.product_name}</h1>
          <div className="text-sm text-muted-foreground mt-1">
            {s.oem_customer} · program <span className="font-medium text-foreground">{s.oem_program}</span> · {s.plant} line {s.production_line} · NPI manager {s.npi_manager}
          </div>
        </div>
        <Card className="py-3">
          <CardContent className="px-4 text-right">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">Start of production</div>
            <div className="text-xl font-bold">{dateFmt(s.sop_date)}</div>
            <div className="text-sm text-primary font-semibold">{fixed(s.weeks_to_sop, 0)} weeks to go</div>
          </CardContent>
        </Card>
      </div>

      {notice && (
        <Alert variant={notice.kind === 'error' ? 'destructive' : 'default'}>
          <CheckCircle2 className="h-4 w-4" />
          <AlertTitle>{notice.kind === 'error' ? 'Not saved' : 'Saved'}</AlertTitle>
          <AlertDescription>{notice.text}</AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="border-l-4 border-l-destructive">
          <CardHeader className="pb-2">
            <CardDescription>Ramp-failure risk (slip &gt;2 wks or 90-day OTIF &lt;85%)</CardDescription>
            <CardTitle className="flex items-center gap-3 text-4xl tabular-nums">
              {pct(s.risk_score)} <RiskBadge tier={s.risk_tier} />
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            {num(s.actions_applied) > 0 && (
              <div className="text-success font-medium">↓ from {pct(s.baseline_risk_score)} before {s.actions_applied} committed action(s)</div>
            )}
            <div>Year-1 revenue at risk <span className="font-semibold">{usdM(s.revenue_at_risk_usd)}</span> of {usdM(s.year1_revenue_usd)}</div>
            <div>OEM platform value at risk <span className="font-semibold">{usdM(s.platform_value_at_risk_usd)}</span> (program {usdM(s.program_lifetime_value_usd, 0)})</div>
            <div className="text-[11px] text-muted-foreground pt-1">Model v{s.risk_model_version} @champion · scored {dateTimeFmt(s.scored_at)}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Pilot-to-production yield</CardDescription>
            <CardTitle className="text-4xl tabular-nums">-{fixed(s.predicted_yield_gap_pts)} pts</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {[
              ['Pilot line', num(s.pilot_yield_pct)],
              ['Production trials', num(s.production_trial_yield_pct)],
              ['Predicted (first 12 wks)', num(s.predicted_yield_pct)],
            ].map(([label, v]) => (
              <div key={String(label)} className="flex items-center gap-2">
                <span className="w-40 text-muted-foreground">{label}</span>
                <div className="flex-1 h-2 bg-muted rounded-full">
                  {Number.isFinite(v) && <div className="h-2 rounded-full bg-foreground/70" style={{ width: `${v}%` }} />}
                </div>
                <span className="w-12 text-right tabular-nums">{Number.isFinite(v) ? `${Number(v).toFixed(1)}%` : '—'}</span>
              </div>
            ))}
            <div className="text-[11px] text-muted-foreground">Basis: {s.yield_basis}. Ramp plans today assume pilot yield.</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Top actionable risk drivers (model contribution)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {drivers.length ? drivers.map((d) => (
              <div key={d.feature} className="text-sm">
                <div className="font-medium">{d.label}</div>
                <div className="text-muted-foreground">{d.detail}</div>
              </div>
            )) : <div className="text-sm text-muted-foreground">No material drivers — launch is on track.</div>}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {shortWeeks > 0
              ? `${binding} supply supports only ${pct(minSupport)} of OEM demand at the ramp low point — short in ${shortWeeks} of the first ${post.length} weeks`
              : `Qualified supply of ${binding} covers OEM demand through the ramp`}
          </CardTitle>
          <CardDescription>
            Weekly OEM demand (EDI forecast) vs output supportable by qualified {binding} supply at predicted production yield · peak demand {Math.round(peakDemand).toLocaleString()} m²/wk
          </CardDescription>
        </CardHeader>
        <CardContent>
          <LineChart data={curve} xKey="week" yKey={['Supportable output (m²/wk)', 'OEM demand (m²/wk)']} height={280} smooth={false}
                     colors={lineColors} showLegend valueFormatter={(v) => Number(v).toLocaleString()} ariaLabel="Ramp supply curve"
                     options={curveOptions} />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2"><Sparkles className="h-4 w-4 text-primary" /> Steering-committee brief</CardTitle>
            <CardDescription>AI-generated from governed lakehouse data · {data.brief?.llm_endpoint ?? '—'} · {dateTimeFmt(data.brief?.generated_at)} · verify before acting</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            {data.brief ? (
              <>
                <p className="font-semibold text-base">{units(data.brief.headline)}</p>
                <p>{units(data.brief.situation)}</p>
                <p className="text-muted-foreground">{units(data.brief.business_impact)}</p>
                <Separator />
                <div className="space-y-2">
                  <div className="font-medium">Recommended mitigations (playbook)</div>
                  {recs.map((r, i) => (
                    <div key={i} className="flex items-start justify-between gap-3 rounded-md border p-3">
                      <div>
                        <div className="font-medium">{r.title}</div>
                        <div className="text-xs text-muted-foreground">{ACTION_LABEL[r.action_type] ?? r.action_type}{r.material_id ? ` · ${r.material_id}` : ''}</div>
                        <div className="text-xs mt-1">{units(r.why)}</div>
                      </div>
                      {alreadyOpen.has(openKey(r.action_type, r.material_id))
                        ? <Button size="sm" variant="ghost" disabled><CheckCircle2 className="h-3 w-3" /> Proposed</Button>
                        : <Button size="sm" variant="outline" disabled={busyId === `rec-${r.action_type}-${r.material_id ?? ''}`} onClick={() => void propose(r)}><Plus className="h-3 w-3" /> Propose</Button>}
                    </div>
                  ))}
                </div>
                {questions.length > 0 && (
                  <div>
                    <div className="font-medium mb-1">Questions for suppliers</div>
                    <ul className="list-disc pl-5 space-y-1 text-muted-foreground">{questions.map((q, i) => <li key={i}>{units(q)}</li>)}</ul>
                  </div>
                )}
              </>
            ) : <NoData title="No brief yet" hint="Briefs are generated by the daily refresh job." />}
          </CardContent>
        </Card>

        <div className="xl:col-span-2 space-y-4">
          <AdvisorPanel npiId={s.npi_id} productCode={s.product_code} onCommitted={(m) => { setNotice({ kind: 'ok', text: m }); reload(); }} />
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Mitigation actions</CardTitle>
              <CardDescription>System of record: Lakebase · approved actions feed the next risk score</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {data.actions.length ? data.actions.map((a) => (
                <div key={a.action_id} className="rounded-md border p-3 text-sm space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{a.title}</span>
                    <ActionStatusBadge status={a.status} />
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {ACTION_LABEL[a.action_type]} · {a.source === 'AI_ADVISOR' ? 'AI-proposed' : 'manual'} · owner {a.owner ?? '—'} · due {dateFmt(a.due_date)}
                  </div>
                  {a.status === 'PROPOSED' && (
                    <div className="flex gap-2 pt-1">
                      <Button size="sm" disabled={busyId === a.action_id} onClick={() => void setStatus(a, 'APPROVED')}>Approve</Button>
                      <Button size="sm" variant="ghost" disabled={busyId === a.action_id} onClick={() => void setStatus(a, 'REJECTED')}>Reject</Button>
                      <Button size="sm" variant="ghost" className="ml-auto text-muted-foreground" disabled={busyId === a.action_id}
                              title="Remove a proposal made by mistake" onClick={() => void withdraw(a)}>Withdraw</Button>
                    </div>
                  )}
                  {a.status === 'APPROVED' && <Button size="sm" variant="outline" disabled={busyId === a.action_id} onClick={() => void setStatus(a, 'IN_PROGRESS')}>Start</Button>}
                  {a.status === 'IN_PROGRESS' && <Button size="sm" variant="outline" disabled={busyId === a.action_id} onClick={() => void setStatus(a, 'DONE')}>Mark done</Button>}
                </div>
              )) : <NoData title="No actions yet" hint="Propose one from the brief or ask the Mitigation Advisor." />}
            </CardContent>
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Bill-of-materials supply readiness at predicted production yield</CardTitle>
          <CardDescription>Coverage = qualified weekly capacity available to this launch ÷ ramp-peak need · sources from SAP approved-source list / PPAP status</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Component</TableHead><TableHead>Status</TableHead><TableHead>Sources (PPAP)</TableHead>
                <TableHead className="text-right">Coverage @ pilot</TableHead><TableHead className="text-right">Coverage @ predicted</TableHead>
                <TableHead className="text-right">Peak shortfall / wk</TableHead><TableHead className="text-right">Lead time</TableHead>
                <TableHead className="text-right">Material gap</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.components.map((c) => (
                <TableRow key={c.material_id}>
                  <TableCell>
                    <div className="font-medium">{c.material_desc}</div>
                    <div className="text-xs text-muted-foreground">{c.material_id} · {c.material_category.replaceAll('_', ' ').toLowerCase()}{c.is_novel_material ? ' · new to BTD' : ''}</div>
                  </TableCell>
                  <TableCell><ReadinessBadge status={c.readiness_status} /></TableCell>
                  <TableCell className="text-xs max-w-[300px] whitespace-normal"><SourceList sources={String(c.sources ?? '')} /></TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">{covPct(c.coverage_at_pilot_yield)}</TableCell>
                  <TableCell className="text-right tabular-nums font-medium">{covPct(c.coverage_at_predicted_yield)}</TableCell>
                  <TableCell className="text-right tabular-nums">{num(c.weekly_shortfall_at_peak) > 0 ? `${Math.round(num(c.weekly_shortfall_at_peak)).toLocaleString()} ${uomLabel(c.uom)}` : '—'}</TableCell>
                  <TableCell className="text-right tabular-nums">{fixed(c.lead_time_weeks, 0)} wks</TableCell>
                  <TableCell className="text-right tabular-nums">{num(c.material_gap_weeks) > 0 ? `${fixed(c.material_gap_weeks, 0)} wks` : '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

const UOM: Record<string, string> = { M2: 'm²', KG: 'kg', L: 'L', EA: 'ea' };
const uomLabel = (u: unknown) => { const v = typeof u === 'string' ? u : ''; return UOM[v.toUpperCase()] ?? v; };

const QUAL_LABEL: Record<string, { label: string; cls: string }> = {
  QUALIFIED: { label: 'Qualified', cls: 'tone-ok' },
  PPAP_IN_PROGRESS: { label: 'PPAP in progress', cls: 'tone-warn' },
  PPAP_SUBMITTED: { label: 'PPAP submitted', cls: 'tone-warn' },
  NOT_STARTED: { label: 'Not started', cls: 'tone-bad' },
};
/** "Arden Specialty Polymers (QUALIFIED), Kvarn Materials AB (PPAP_IN_PROGRESS)" -> one readable line per source. */
function SourceList({ sources }: { sources: string }) {
  const items = [...sources.matchAll(/([^,(]+?)\s*\(([A-Z_]+)\)/g)].map((m) => ({ name: m[1].trim(), status: m[2] }));
  if (!items.length) return <span>{sources || '—'}</span>;
  return (
    <ul className="space-y-0.5">
      {items.map((it) => {
        const q = QUAL_LABEL[it.status] ?? { label: it.status.replace(/_/g, ' ').toLowerCase(), cls: 'text-muted-foreground' };
        return <li key={`${it.name}-${it.status}`}>{it.name} <span className={`font-medium ${q.cls}`}>· {q.label}</span></li>;
      })}
    </ul>
  );
}

/** LLM text echoes SAP units ("16,564 M2"); show them as people write them. */
const units = (t: unknown) => (typeof t === 'string' ? t : '').replace(/(\d)\s?M2\b/g, '$1 m²');
