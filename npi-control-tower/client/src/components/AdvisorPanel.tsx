import { useRef, useState } from 'react';
import { Alert, AlertDescription, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Spinner, Textarea } from '@databricks/appkit-ui/react';
import { Bot, ShieldCheck } from 'lucide-react';
import { RichText } from './States';
import { ACTION_LABEL, apiSend, pct, usdM, type AdvisorReply } from '../lib/npi';

const TOOL_LABEL: Record<string, string> = {
  get_launch_risk: 'Risk score', get_component_readiness: 'BOM readiness', get_mitigation_playbook: 'Playbook',
  simulate_mitigations: 'What-if simulation (UC models)', ask_genie: 'Genie',
};

export function AdvisorPanel({ npiId, productCode, onCommitted, compact = true, showHeader = true }: {
  npiId?: string; productCode?: string; onCommitted?: (msg: string) => void; compact?: boolean; showHeader?: boolean;
}) {
  const presets = productCode
    ? [`Why is ${productCode} at risk?`, `What should we do to protect the ${productCode} SOP? Quantify the impact.`]
    : ['Which three launches carry the most revenue at risk right now?',
       'What should we do to protect the AFT-7200 SOP? Quantify the impact.',
       'Historically, what is the most common root cause of failed launch ramps?'];
  const [q, setQ] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [busy, setBusy] = useState(false);
  const [reply, setReply] = useState<AdvisorReply | null>(null);
  const [asked, setAsked] = useState<string>('');
  const [err, setErr] = useState<string | null>(null);
  const [committing, setCommitting] = useState(false);

  async function ask(question: string) {
    if (!question.trim()) return;
    setBusy(true); setErr(null); setReply(null); setAsked(question);
    try {
      setReply(await apiSend<AdvisorReply>('/api/advisor', 'POST', { question, npi_id: npiId }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function commit() {
    const sim = reply?.simulation;
    if (!sim) return;
    setCommitting(true);
    try {
      for (const a of sim.proposed_actions) {
        await apiSend('/api/actions', 'POST', {
          npi_id: sim.npi_id, material_id: a.material_id, action_type: a.action_type, status: 'APPROVED', source: 'AI_ADVISOR',
          title: `${ACTION_LABEL[a.action_type] ?? a.action_type}${a.material_id ? ` - ${a.material_id}` : ''}`,
          rationale: `Mitigation Advisor package: simulated risk ${pct(sim.risk_before)} -> ${pct(sim.risk_after)}`,
          expected_risk_reduction: Math.round((sim.risk_before - sim.risk_after) * 1e4) / 1e4,
        });
      }
      onCommitted?.(`Committed ${sim.proposed_actions.length} approved actions to Lakebase. Lakehouse Sync streams them to Unity Catalog; the re-score job refreshes risk within minutes.`);
      if (reply) setReply({ ...reply, simulation: null });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setCommitting(false);
    }
  }

  const sim = reply?.simulation;
  return (
    <Card className="border-primary/40">
      {showHeader && (
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2"><Bot className="h-4 w-4 text-primary" /> Mitigation Advisor</CardTitle>
          <CardDescription>
            Tool-calling agent on Databricks Model Serving · grounded in governed lakehouse data · quantifies options with the production risk models
          </CardDescription>
        </CardHeader>
      )}
      <CardContent className={`space-y-3 ${showHeader ? '' : 'pt-6'}`}>
        <div className="text-xs font-medium text-muted-foreground">Try asking (click to insert)</div>
        <div className="flex flex-wrap gap-2">
          {presets.map((p) => <Button key={p} size="sm" variant="outline" disabled={busy} title="Insert this question" className="h-auto whitespace-normal text-left font-normal hover:border-primary/60"
                                         onClick={() => { setQ(p); inputRef.current?.focus(); }}>{p}</Button>)}
        </div>
        <Textarea ref={inputRef} rows={compact ? 2 : 3} placeholder="Ask about risk drivers, suppliers, or what to do…" value={q} onChange={(e) => setQ(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void ask(q); } }} />
        <div className="flex justify-end"><Button size="sm" disabled={busy || !q.trim()} onClick={() => void ask(q)}>Ask</Button></div>
        {busy && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Spinner className="h-4 w-4" /> Reading launch data, checking supply, running what-if simulations… (30-90 s)
          </div>
        )}
        {err && <Alert variant="destructive"><AlertDescription>{err}</AlertDescription></Alert>}
        {reply && (
          <div className="space-y-3">
            <div className="text-xs text-muted-foreground">Q: {asked}</div>
            <div className="flex flex-wrap gap-1">
              {reply.tools.map((t, i) => <Badge key={i} variant="outline" className="text-[10px]">{TOOL_LABEL[t] ?? t}</Badge>)}
            </div>
            <RichText text={humanizeActions(reply.answer)} />
            {sim && (
              <div className="rounded-md border border-success/50 bg-success/5 p-3 space-y-2">
                <div className="text-sm font-semibold">
                  Simulated package: risk {pct(sim.risk_before)} → {pct(sim.risk_after)} ({sim.tier_before} → {sim.tier_after}) ·
                  revenue at risk {usdM(sim.revenue_at_risk_before_usd)} → {usdM(sim.revenue_at_risk_after_usd)}
                </div>
                <ul className="text-xs list-disc pl-5">
                  {sim.proposed_actions.map((a, i) => <li key={i}>{ACTION_LABEL[a.action_type] ?? a.action_type}{a.material_id ? ` · ${a.material_id}` : ''}</li>)}
                </ul>
                <Button size="sm" disabled={committing} onClick={() => void commit()}>
                  {committing ? 'Committing…' : `Approve & commit ${sim.proposed_actions.length} actions`}
                </Button>
              </div>
            )}
            <p className="text-[11px] text-muted-foreground flex items-center gap-1">
              <ShieldCheck className="h-3 w-3" /> AI-generated — runs on behalf of you, so Unity Catalog permissions apply. Recommendations are proposals until a person approves them.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** The agent reasons with playbook codes (PULL_AHEAD_BUY); show readers the playbook labels instead. */
const humanizeActions = (t: string) =>
  t.replace(/`?\b(DUAL_SOURCE_EXPEDITE|CAPACITY_RESERVATION|PULL_AHEAD_BUY|YIELD_SPRINT|LINE_REALLOCATION|PHASED_RAMP_WITH_OEM)\b`?/g,
    (_m, code: string) => ACTION_LABEL[code] ?? code);
