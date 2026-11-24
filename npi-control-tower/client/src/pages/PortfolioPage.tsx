import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import {
  BarChart, Card, CardContent, CardDescription, CardHeader, CardTitle, Input,
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow, ToggleGroup, ToggleGroupItem,
} from '@databricks/appkit-ui/react';
import { ArrowRight } from 'lucide-react';
import { Kpi } from '../components/Kpi';
import { ErrorBox, Loading, NoData } from '../components/States';
import { RiskBadge, RiskBar } from '../components/StatusBadges';
import { dateFmt, dateTimeFmt, fixed, num, pct, useApi, usdM, useChartInk, useTokenColors, type LaunchRow } from '../lib/npi';

const TIERS = ['HIGH', 'MEDIUM', 'LOW'] as const;
const TIER_LABEL = { HIGH: 'High', MEDIUM: 'Medium', LOW: 'Low' } as const;

export function PortfolioPage() {
  const { data, error, loading, reload } = useApi<{ launches: LaunchRow[] }>('/api/portfolio');
  const [tier, setTier] = useState<string>('ALL');
  const [search, setSearch] = useState('');
  const navigate = useNavigate();
  const tierColors = useTokenColors(['--destructive', '--warning', '--success']);
  const ink = useChartInk();
  const launches = useMemo(() => data?.launches ?? [], [data]);

  const k = useMemo(() => {
    const sum = (f: (l: LaunchRow) => number) => launches.reduce((a, l) => a + (num(f(l)) || 0), 0);
    const high = launches.filter((l) => l.risk_tier === 'HIGH');
    const soon = high.filter((l) => num(l.weeks_to_sop) <= 13);
    const mitigated = launches.filter((l) => num(l.actions_applied) > 0);
    const reduction = mitigated.reduce((a, l) => a + (num(l.baseline_risk_score) - num(l.risk_score)) * num(l.year1_revenue_usd), 0);
    return {
      n: launches.length, high: high.length, soon: soon.length, rev: sum((l) => l.year1_revenue_usd),
      rar: sum((l) => l.revenue_at_risk_usd), pvar: sum((l) => l.platform_value_at_risk_usd),
      mitigated: mitigated.length, protected: reduction, scoredAt: launches[0]?.scored_at,
    };
  }, [launches]);

  const byOem = useMemo(() => {
    const m = new Map<string, Record<string, number | string>>();
    for (const l of launches) {
      const r = m.get(l.oem_customer) ?? { oem: l.oem_customer, HIGH: 0, MEDIUM: 0, LOW: 0 };
      r[l.risk_tier] = (num(r[l.risk_tier]) || 0) + num(l.revenue_at_risk_usd) / 1e6;
      m.set(l.oem_customer, r);
    }
    return [...m.values()].sort((a, b) => num(b.HIGH) + num(b.MEDIUM) + num(b.LOW) - (num(a.HIGH) + num(a.MEDIUM) + num(a.LOW)));
  }, [launches]);

  const bySop = useMemo(() => {
    const m = new Map<string, Record<string, number | string>>();
    for (const l of [...launches].sort((a, b) => a.sop_date.localeCompare(b.sop_date))) {
      const key = l.sop_date.slice(0, 7);
      // Category label (not a "month"/date-named field, which the chart would treat as a time axis and not stack)
      const label = new Date(`${key}-01T00:00:00`).toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
      const r = m.get(key) ?? { ym: key, sop: label, HIGH: 0, MEDIUM: 0, LOW: 0 };
      r[l.risk_tier] = (num(r[l.risk_tier]) || 0) + 1;
      m.set(key, r);
    }
    return [...m.values()];
  }, [launches]);

  // Full axis/series overrides (AppKit merges `options` shallowly): OEM names untruncated with the largest exposure
  // on top, and SOP months as a stacked category axis (AppKit only stacks area charts on vertical cartesian axes).
  const oemRows = [...byOem].reverse();
  const oemChartOptions = {
      grid: { left: 8, right: 24, top: 8, bottom: 40, containLabel: true },
      yAxis: { type: 'category', data: oemRows.map((r) => String(r.oem)), axisTick: { show: false },
               axisLabel: { width: 170, overflow: 'truncate', color: ink.strong }, axisLine: { lineStyle: { color: ink.grid } } },
      xAxis: { type: 'value', axisLabel: { formatter: (v: number) => `$${v}M`, color: ink.muted }, splitLine: { lineStyle: { color: ink.grid } } },
      legend: { bottom: 0, textStyle: { color: ink.strong } },
      series: TIERS.map((t, i) => ({ name: TIER_LABEL[t], type: 'bar', stack: 'total', barMaxWidth: 18, color: tierColors?.[i],
                                     data: oemRows.map((r) => Number(num(r[t]).toFixed(2))) })),
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v: number) => `$${Number(v).toFixed(1)}M` },
  };
  const sopChartOptions = {
    grid: { left: 8, right: 16, top: 16, bottom: 40, containLabel: true },
    xAxis: { type: 'category', data: bySop.map((r) => String(r.sop)), axisTick: { alignWithLabel: true },
             axisLabel: { interval: 0, color: ink.strong }, axisLine: { lineStyle: { color: ink.grid } } },
    yAxis: { type: 'value', minInterval: 1, name: 'Launches', nameTextStyle: { color: ink.muted }, axisLabel: { color: ink.muted },
             splitLine: { lineStyle: { color: ink.grid } } },
    legend: { bottom: 0, textStyle: { color: ink.strong } },
    series: TIERS.map((t, i) => ({ name: TIER_LABEL[t], type: 'bar', stack: 'total', barMaxWidth: 28, color: tierColors?.[i],
                                   data: bySop.map((r) => num(r[t]) || 0) })),
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  };

  const peakMonth = useMemo(() => {
    const top = [...bySop].sort((a, b) => num(b.HIGH) - num(a.HIGH))[0];
    return top ? new Date(`${top.ym}-01T00:00:00`).toLocaleDateString(undefined, { month: 'long', year: 'numeric' }) : '—';
  }, [bySop]);

  const rows = launches.filter(
    (l) => (tier === 'ALL' || l.risk_tier === tier) &&
      (!search || `${l.product_code} ${l.product_name} ${l.oem_customer} ${l.oem_program} ${l.npi_id}`.toLowerCase().includes(search.toLowerCase())),
  );

  if (loading && !data) return <Loading rows={4} />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!launches.length) return <NoData title="No active launches" hint="Run the daily refresh job to score the pipeline." />;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">
            {usdM(k.rar)} of year-1 launch revenue is at risk in the scale-up pipeline
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {k.n} pilot-validated NPIs ramping to production for OEM programs · {k.high} high-risk, {k.soon} of them within 13 weeks of SOP
          </p>
        </div>
        <div className="text-xs text-muted-foreground text-right">
          Scored {dateTimeFmt(k.scoredAt)} · risk model + yield model (Unity Catalog)<br />
          Served from Lakebase synced tables
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <Kpi label="Year-1 revenue at risk" value={usdM(k.rar)} tone="bad"
             compare={`of ${usdM(k.rev)} year-1 revenue in the active pipeline (${pct(k.rar / k.rev)})`}
             source="Σ ramp-failure probability × year-1 revenue" />
        <Kpi label="OEM platform value at risk" value={usdM(k.pvar, 0)} tone="bad"
             compare="Lifetime program revenue exposed to a competitor design-in"
             source="risk × P(platform lost | failed ramp) × program value · auto/EV" />
        <Kpi label="High-risk launches" value={`${k.high} of ${k.n}`}
             compare={`${k.soon} with SOP in the next 13 weeks`}
             source="Risk ≥ 60% that the ramp slips >2 wks or 90-day OTIF < 85%" />
        <Kpi label="Revenue protected by committed actions" value={usdM(k.protected)} tone="good"
             compare={`${k.mitigated} launches with committed mitigations`}
             source="(baseline − current risk) × year-1 revenue · actions from Lakebase" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{String(byOem[0]?.oem ?? 'Top OEM')} carries the largest revenue exposure</CardTitle>
            <CardDescription>Year-1 revenue at risk by OEM customer, $M, stacked by risk tier</CardDescription>
          </CardHeader>
          <CardContent>
            <BarChart data={[...byOem].reverse()} xKey="oem" yKey={['HIGH', 'MEDIUM', 'LOW']} stacked height={300} orientation="horizontal" colors={tierColors}
                      options={oemChartOptions}
                      valueFormatter={(v) => `$${Number(v).toFixed(1)}M`} ariaLabel="Revenue at risk by OEM customer" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Peak exposure: {peakMonth} has the most high-risk SOPs</CardTitle>
            <CardDescription>Number of launches by SOP month and risk tier</CardDescription>
          </CardHeader>
          <CardContent>
            <BarChart data={bySop} xKey="sop" yKey={['HIGH', 'MEDIUM', 'LOW']} stacked height={300} orientation="vertical" colors={tierColors}
                      options={sopChartOptions}
                      ariaLabel="Launches by SOP month and tier" />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="text-base">Launch watchlist</CardTitle>
            <CardDescription>Ranked by year-1 revenue at risk · click a launch for drivers, supply curve and mitigation</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Input placeholder="Search product, OEM, program…" value={search} onChange={(e) => setSearch(e.target.value)} className="w-56" />
            <ToggleGroup type="single" value={tier} onValueChange={(v) => setTier(v || 'ALL')} variant="outline" size="sm">
              {['ALL', 'HIGH', 'MEDIUM', 'LOW'].map((t) => <ToggleGroupItem key={t} value={t}>{t === 'ALL' ? 'All' : t}</ToggleGroupItem>)}
            </ToggleGroup>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Launch</TableHead>
                <TableHead>OEM · program</TableHead>
                <TableHead>SOP</TableHead>
                <TableHead>Ramp-failure risk</TableHead>
                <TableHead className="text-right">Revenue at risk</TableHead>
                <TableHead>Bottleneck</TableHead>
                <TableHead className="text-right whitespace-nowrap">Yield gap</TableHead>
                <TableHead className="text-right">Actions</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((l) => (
                <TableRow key={l.npi_id} className="cursor-pointer" onClick={() => void navigate(`/launch/${l.npi_id}`)}>
                  <TableCell>
                    <div className="font-semibold">{l.product_code}</div>
                    <div className="text-xs text-muted-foreground max-w-[170px] 2xl:max-w-[240px] truncate" title={l.product_name}>{productTitle(l.product_name, l.product_code)}</div>
                  </TableCell>
                  <TableCell>
                    <div>{l.oem_customer}</div>
                    <div className="text-xs text-muted-foreground">{l.oem_program} · {l.plant}</div>
                  </TableCell>
                  <TableCell>
                    <div>{dateFmt(l.sop_date)}</div>
                    <div className="text-xs text-muted-foreground">{fixed(l.weeks_to_sop, 0)} wks · {l.current_gate}</div>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <RiskBadge tier={l.risk_tier} />
                      <RiskBar risk={num(l.risk_score)} baseline={num(l.baseline_risk_score)} />
                      <span className="tabular-nums text-sm">{pct(l.risk_score)}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-medium">{usdM(l.revenue_at_risk_usd)}</TableCell>
                  <TableCell className="text-sm"><div className="max-w-[140px] 2xl:max-w-[220px] truncate" title={l.binding_component_desc ?? undefined}>{l.binding_component_desc}</div></TableCell>
                  <TableCell className="text-right tabular-nums whitespace-nowrap">{fixed(l.predicted_yield_gap_pts)} pts</TableCell>
                  <TableCell className="text-right tabular-nums">{num(l.open_actions) || '—'}</TableCell>
                  <TableCell>
                    <Link to={`/launch/${l.npi_id}`} aria-label={`Open ${l.product_code}`} onClick={(e) => e.stopPropagation()}>
                      <ArrowRight className="h-4 w-4 text-muted-foreground" />
                    </Link>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {!rows.length && <NoData title="No launches match the filter" />}
        </CardContent>
      </Card>
    </div>
  );
}

/** "AFT-7200 Structural Battery-Enclosure Foam Tape" -> "Structural Battery-Enclosure Foam Tape" (the code is shown above it). */
const productTitle = (name: string, code: string) => (name.startsWith(`${code} `) ? name.slice(code.length + 1) : name);
