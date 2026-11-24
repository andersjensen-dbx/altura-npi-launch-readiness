import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, GenieChat } from '@databricks/appkit-ui/react';
import { ShieldCheck } from 'lucide-react';
import { useWhoAmI } from '../components/Shell';

const examples = [
  'Which high-risk launches have SOP in Q1 2027, and what is their bottleneck material?',
  'What did failed ramps cost us in expedites and E&O by year?',
  'Which root causes drive most failed ramps?',
  'Which suppliers are still in PPAP for AFT-7200 components?',
];

/** GenieChat has no prop to pre-fill a question: put the example into its textarea (React-safe) and focus it. */
function askExample(text: string) {
  const ta = document.querySelector<HTMLTextAreaElement>('.npi-genie textarea');
  if (!ta) return;
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set?.call(ta, text);
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  ta.focus();
}

export function AskPage() {
  const me = useWhoAmI();
  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
      <div className="lg:col-span-3 space-y-3">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Ask the Data</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Natural-language questions over the governed launch-readiness metrics (Genie Agent on Unity Catalog metric views).
          </p>
        </div>
        <div className="h-[min(680px,72vh)] border rounded-lg overflow-hidden bg-card">
          <GenieChat alias="default" className="npi-genie" placeholder="e.g. Which launches are single-sourced on a novel material?" />
        </div>
        <p className="text-xs text-muted-foreground">
          AI-generated from your data via Genie — expand the generated SQL on each answer and verify before acting.
        </p>
      </div>
      <div className="space-y-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-success" /> Governed access</CardTitle></CardHeader>
          <CardContent className="text-xs space-y-2 text-muted-foreground">
            <div>Signed in as <Badge variant="outline">{me?.email ?? 'local development (your CLI identity)'}</Badge></div>
            <div>Queries run <span className="text-foreground font-medium">on behalf of you</span>: Unity Catalog permissions, column masks
              (supplier prices) and regional row filters apply to every answer.</div>
            <div>Metrics come from certified UC metric views — the same definitions used by the risk scoring and this app.</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Try asking</CardTitle><CardDescription className="text-xs">Benchmarked: 12/12 reference questions correct · click to insert</CardDescription></CardHeader>
          <CardContent className="text-xs space-y-2">{examples.map((e) => (
            <button key={e} type="button" onClick={() => askExample(e)}
              className="block w-full rounded border p-2 text-left hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
              {e}
            </button>
          ))}</CardContent>
        </Card>
      </div>
    </div>
  );
}
