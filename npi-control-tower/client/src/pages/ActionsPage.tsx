import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import {
  Alert, AlertDescription, AlertTitle, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle,
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue, Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
  ToggleGroup, ToggleGroupItem,
} from '@databricks/appkit-ui/react';
import { RefreshCw, Workflow } from 'lucide-react';
import { ErrorBox, Loading, NoData } from '../components/States';
import { ActionStatusBadge, RiskBadge } from '../components/StatusBadges';
import { ACTION_LABEL, apiSend, dateFmt, dateTimeFmt, num, useApi, usdM, type ActionRow, type ActionStatus } from '../lib/npi';

interface JobRun { run_id: number; state?: { life_cycle_state?: string; result_state?: string }; start_time?: number; end_time?: number }

export function ActionsPage() {
  const { data, error, loading, reload } = useApi<{ actions: ActionRow[] }>('/api/actions');
  const runs = useApi<{ runs?: JobRun[] }>('/api/jobs/default/runs?limit=3');
  const [filter, setFilter] = useState('OPEN');
  const [msg, setMsg] = useState<string | null>(null);
  const actions = useMemo(() => data?.actions ?? [], [data]);
  const rows = actions.filter((a) => filter === 'ALL' || (filter === 'OPEN' ? ['PROPOSED', 'APPROVED', 'IN_PROGRESS'].includes(a.status) : a.status === filter));
  const committedCost = actions.filter((a) => ['APPROVED', 'IN_PROGRESS', 'DONE'].includes(a.status)).reduce((s, a) => s + (num(a.estimated_cost_usd) || 0), 0);

  async function update(a: ActionRow, status: ActionStatus) {
    try {
      await apiSend(`/api/actions/${a.action_id}`, 'PATCH', { status });
      setMsg(`${a.title}: ${status.replace('_', ' ').toLowerCase()}. Written to Lakebase; Lakehouse Sync and the table-update trigger re-score the launch automatically.`);
      reload();
    } catch (e) {
      setMsg(`Could not update "${a.title}": ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  async function rescoreNow() {
    try {
      const r = await fetch('/api/jobs/default/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setMsg('Re-score job started. The launch scores refresh in a few minutes.');
      setTimeout(runs.reload, 1500);
    } catch (e) {
      setMsg(`Could not start the re-score job: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  if (loading && !data) return <Loading rows={3} />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  const last = runs.data?.runs?.[0];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Action Center</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Every mitigation across the launch pipeline: proposed by planners or the Mitigation Advisor, approved by owners, tracked to done.
          </p>
        </div>
        <div className="text-sm text-right">
          <div><span className="font-semibold">{actions.filter((a) => ['APPROVED', 'IN_PROGRESS', 'DONE'].includes(a.status)).length}</span> committed actions · {usdM(committedCost, 2)} committed spend</div>
        </div>
      </div>

      <Card>
        <CardContent className="py-4 flex flex-wrap items-center gap-4 text-sm">
          <Workflow className="h-5 w-5 text-primary" />
          <div className="flex-1 min-w-[280px]">
            <div className="font-medium">Closed loop</div>
            <div className="text-muted-foreground text-xs">
              App → Lakebase <code>ops.mitigation_actions</code> → Lakehouse Sync (CDC) → Unity Catalog → table-update trigger → re-score job → Lakebase synced tables → app
            </div>
          </div>
          <div className="text-xs">
            Last re-score: {last ? <>
              <RunBadge state={String(last.state?.result_state ?? last.state?.life_cycle_state ?? '')} /> {dateTimeFmt(last.start_time ? new Date(last.start_time).toISOString() : null)}
            </> : runs.error ? 'unavailable' : '—'}
          </div>
          <Button size="sm" variant="outline" onClick={() => void rescoreNow()}><RefreshCw className="h-3 w-3" /> Re-score now</Button>
        </CardContent>
      </Card>

      {msg && <Alert><AlertTitle>Updated</AlertTitle><AlertDescription>{msg}</AlertDescription></Alert>}

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <div><CardTitle className="text-base">Mitigation actions</CardTitle><CardDescription>System of record: Lakebase (Postgres)</CardDescription></div>
          <ToggleGroup type="single" value={filter} onValueChange={(v) => setFilter(v || 'OPEN')} variant="outline" size="sm">
            {['OPEN', 'PROPOSED', 'APPROVED', 'IN_PROGRESS', 'DONE', 'ALL'].map((s) => <ToggleGroupItem key={s} value={s}>{STATUS_LABEL[s] ?? s}</ToggleGroupItem>)}
          </ToggleGroup>
        </CardHeader>
        <CardContent>
          {rows.length ? (
            <Table>
              <TableHeader><TableRow>
                <TableHead>Launch</TableHead><TableHead>Action</TableHead><TableHead>Source</TableHead><TableHead>Owner</TableHead>
                <TableHead>Due</TableHead><TableHead className="text-right">Est. cost</TableHead><TableHead>Status</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {rows.map((a) => (
                  <TableRow key={a.action_id}>
                    <TableCell>
                      <Link to={`/launch/${a.npi_id}`} className="font-medium text-foreground underline decoration-muted-foreground/40 underline-offset-4 hover:decoration-primary">{a.product_code ?? a.npi_id}</Link>
                      <div className="text-xs text-muted-foreground flex items-center gap-1">{a.oem_customer} {a.risk_tier && <RiskBadge tier={a.risk_tier} />}</div>
                    </TableCell>
                    <TableCell className="max-w-[340px] whitespace-normal">
                      <div className="font-medium text-sm">{a.title}</div>
                      <div className="text-xs text-muted-foreground">{ACTION_LABEL[a.action_type]}</div>
                    </TableCell>
                    <TableCell className="text-xs">{a.source === 'AI_ADVISOR' ? 'Mitigation Advisor' : 'Planner'}</TableCell>
                    <TableCell className="text-xs">{a.owner ?? '—'}</TableCell>
                    <TableCell className="text-xs">{dateFmt(a.due_date)}</TableCell>
                    <TableCell className="text-right tabular-nums text-xs">{a.estimated_cost_usd ? `$${Math.round(num(a.estimated_cost_usd) / 1000)}K` : '—'}</TableCell>
                    <TableCell>
                      <Select value={a.status} onValueChange={(v) => void update(a, v as ActionStatus)}>
                        <SelectTrigger className="h-8 w-[150px]" aria-label={`Status of ${a.title}`}><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {(['PROPOSED', 'APPROVED', 'IN_PROGRESS', 'DONE', 'REJECTED'] as ActionStatus[]).map((s) => <SelectItem key={s} value={s}><ActionStatusBadge status={s} /></SelectItem>)}
                        </SelectContent>
                      </Select>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : <NoData title="No actions in this view" hint="Propose mitigations from a launch page or the Mitigation Advisor." />}
        </CardContent>
      </Card>
    </div>
  );
}

const STATUS_LABEL: Record<string, string> = {
  OPEN: 'Open', PROPOSED: 'Proposed', APPROVED: 'Approved', IN_PROGRESS: 'In progress', DONE: 'Done', REJECTED: 'Rejected', ALL: 'All',
};

/** Lakeflow Jobs run state in plain words, colored by outcome. */
function RunBadge({ state }: { state: string }) {
  const map: Record<string, [string, string]> = {
    SUCCESS: ['Succeeded', 'tone-ok'], FAILED: ['Failed', 'tone-bad'],
    CANCELED: ['Canceled', ''], TIMEDOUT: ['Timed out', 'tone-bad'], RUNNING: ['Running…', 'tone-info'],
    PENDING: ['Queued…', 'tone-info'], QUEUED: ['Queued…', 'tone-info'], TERMINATING: ['Finishing…', 'tone-info'],
  };
  const [label, cls] = map[state] ?? [state.charAt(0) + state.slice(1).toLowerCase(), ''];
  return <Badge variant="outline" className={cls}>{label}</Badge>;
}
