import { Badge } from '@databricks/appkit-ui/react';
import type { ActionStatus, RiskTier } from '../lib/npi';

const tierClass: Record<RiskTier, string> = {
  HIGH: 'bg-destructive text-destructive-foreground border-transparent',
  MEDIUM: 'bg-warning text-warning-foreground border-transparent',
  LOW: 'bg-success text-success-foreground border-transparent',
};
export function RiskBadge({ tier }: { tier: RiskTier }) {
  return <Badge className={tierClass[tier]}>{tier}</Badge>;
}

const readyClass = {
  RED: 'bg-destructive text-destructive-foreground border-transparent',
  AMBER: 'bg-warning text-warning-foreground border-transparent',
  GREEN: 'bg-success text-success-foreground border-transparent',
} as const;
export function ReadinessBadge({ status }: { status: keyof typeof readyClass }) {
  return <Badge className={readyClass[status]}>{status}</Badge>;
}

export function ActionStatusBadge({ status }: { status: ActionStatus }) {
  if (status === 'DONE') return <Badge className="bg-success text-success-foreground border-transparent">Done</Badge>;
  if (status === 'IN_PROGRESS') return <Badge variant="outline" className="tone-info">In progress</Badge>;
  if (status === 'APPROVED') return <Badge variant="secondary">Approved</Badge>;
  if (status === 'REJECTED') return <Badge variant="outline" className="text-muted-foreground">Rejected</Badge>;
  return <Badge variant="outline">Proposed</Badge>;
}

/** Horizontal risk bar: baseline (outline) vs current (filled) - shows the effect of committed mitigations. */
export function RiskBar({ risk, baseline }: { risk: number; baseline?: number }) {
  const tone = risk >= 0.6 ? 'bg-destructive' : risk >= 0.25 ? 'bg-warning' : 'bg-success';
  return (
    <div className="relative h-2 w-16 2xl:w-24 shrink-0 rounded-full bg-muted" aria-label={`risk ${(risk * 100).toFixed(0)}%`}>
      {baseline !== undefined && baseline > risk + 0.005 && (
        <div className="absolute inset-y-0 left-0 rounded-full border border-foreground/30" style={{ width: `${baseline * 100}%` }} />
      )}
      <div className={`absolute inset-y-0 left-0 rounded-full ${tone}`} style={{ width: `${Math.max(risk * 100, 2)}%` }} />
    </div>
  );
}
