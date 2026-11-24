import { Alert, AlertDescription, AlertTitle, Empty, EmptyDescription, EmptyHeader, EmptyTitle, Skeleton } from '@databricks/appkit-ui/react';
import { AlertTriangle } from 'lucide-react';

export const Loading = ({ rows = 3 }: { rows?: number }) => (
  <div className="space-y-3">{Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}</div>
);
export const ErrorBox = ({ error, onRetry }: { error: string; onRetry?: () => void }) => (
  <Alert variant="destructive">
    <AlertTriangle className="h-4 w-4" />
    <AlertTitle>Could not load data</AlertTitle>
    <AlertDescription>
      {error} {onRetry && <button className="underline ml-2" onClick={onRetry}>Retry</button>}
    </AlertDescription>
  </Alert>
);
export const NoData = ({ title, hint }: { title: string; hint?: string }) => (
  <Empty><EmptyHeader><EmptyTitle>{title}</EmptyTitle>{hint && <EmptyDescription>{hint}</EmptyDescription>}</EmptyHeader></Empty>
);

/** Minimal, safe markdown: paragraphs, bullets, numbered items, **bold**. */
/** Minimal markdown for agent answers: headings, bullets, numbered items, **bold**, `code` and pipe tables. */
export function RichText({ text }: { text: string }) {
  const inline = (s: string) =>
    s.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((p, i) =>
      p.startsWith('**') && p.endsWith('**') ? <strong key={i}>{p.slice(2, -2)}</strong>
        : p.startsWith('`') && p.endsWith('`') ? <code key={i} className="rounded bg-muted px-1 text-[0.85em]">{p.slice(1, -1)}</code>
          : <span key={i}>{p}</span>);
  const cells = (row: string) => row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
  const isRow = (l: string) => l.trim().startsWith('|');
  const isSep = (l: string) => /^\|?\s*:?-{2,}/.test(l.trim());

  // Group the text into blocks; table rows may be separated by blank lines (LLMs often emit them that way).
  const lines = text.split('\n');
  const blocks: Array<{ kind: 'table'; rows: string[][] } | { kind: 'line'; text: string }> = [];
  for (let i = 0; i < lines.length; i++) {
    if (isRow(lines[i])) {
      const rows: string[][] = [];
      let j = i;
      while (j < lines.length && (isRow(lines[j]) || (!lines[j].trim() && j + 1 < lines.length && isRow(lines[j + 1])))) {
        if (isRow(lines[j]) && !isSep(lines[j])) rows.push(cells(lines[j]));
        j++;
      }
      blocks.push({ kind: 'table', rows });
      i = j - 1;
    } else blocks.push({ kind: 'line', text: lines[i] });
  }

  return (
    <div className="space-y-1.5 text-sm leading-relaxed">
      {blocks.map((b, i) => {
        if (b.kind === 'table') {
          const [head, ...body] = b.rows;
          return (
            <div key={i} className="overflow-x-auto py-1">
              <table className="w-full text-xs border-collapse">
                <thead><tr>{head.map((h, k) => <th key={k} className="border-b px-2 py-1 text-left font-semibold">{inline(h)}</th>)}</tr></thead>
                <tbody>{body.map((r, k) => (
                  <tr key={k} className="border-b last:border-0">{r.map((c, m) => <td key={m} className={`px-2 py-1 ${m > 0 ? 'tabular-nums' : ''}`}>{inline(c)}</td>)}</tr>
                ))}</tbody>
              </table>
            </div>
          );
        }
        const t = b.text.trim();
        if (!t) return <div key={i} className="h-1" />;
        if (/^#{1,4}\s/.test(t)) return <div key={i} className="font-semibold pt-1">{inline(t.replace(/^#+\s/, ''))}</div>;
        if (/^[-*]\s/.test(t)) return <div key={i} className="pl-4 relative before:content-['•'] before:absolute before:left-1">{inline(t.slice(2))}</div>;
        if (/^\d+[.)]\s/.test(t)) return <div key={i} className="pl-4">{inline(t)}</div>;
        return <p key={i}>{inline(t)}</p>;
      })}
    </div>
  );
}
