import { AdvisorPanel } from '../components/AdvisorPanel';

export function AdvisorPage() {
  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">Mitigation Advisor</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Ask about any launch in the scale-up pipeline. The advisor reads risk scores, BOM supply readiness and the mitigation
          playbook, then quantifies each option by re-scoring the launch with the production ML models before recommending it.
        </p>
        <p className="text-xs text-muted-foreground mt-2">
          Tool-calling agent on Databricks Model Serving · runs on behalf of you, so Unity Catalog permissions apply · recommendations
          are proposals until a person approves them.
        </p>
      </div>
      <AdvisorPanel compact={false} showHeader={false} />
    </div>
  );
}
