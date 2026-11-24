import { Card, CardContent } from '@databricks/appkit-ui/react';
import type { ReactNode } from 'react';

/** KPI tile: label, value, comparison line and provenance (unit/period/source on every number). */
export function Kpi({ label, value, compare, source, tone }: {
  label: string; value: ReactNode; compare?: ReactNode; source?: string; tone?: 'bad' | 'good' | 'neutral';
}) {
  const accent = tone === 'bad' ? 'border-l-destructive' : tone === 'good' ? 'border-l-success' : 'border-l-foreground/30';
  return (
    <Card className={`border-l-4 ${accent} py-4`}>
      <CardContent className="px-4 space-y-1">
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
        <div className="text-2xl font-bold text-foreground tabular-nums">{value}</div>
        {compare && <div className="text-xs text-muted-foreground">{compare}</div>}
        {source && <div className="text-[10px] text-muted-foreground/80 pt-1">{source}</div>}
      </CardContent>
    </Card>
  );
}
