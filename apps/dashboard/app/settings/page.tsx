import { ExternalLink, Server, Shield, Workflow } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API_BASE_URL } from "@/lib/api";

export default function SettingsPage() {
  return <><PageHeader eyebrow="Configuration" title="Settings" description="Connection and runtime information for this dashboard instance." />
    <div className="grid gap-4 xl:grid-cols-2">
      <Card><CardHeader><CardTitle className="flex items-center gap-2"><Server className="h-4 w-4 text-primary" />API connection</CardTitle></CardHeader><CardContent className="space-y-4"><Setting label="API base URL" value={API_BASE_URL} mono /><Setting label="Health endpoint" value={`${API_BASE_URL}/health`} mono /><a href={`${API_BASE_URL}/docs`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-primary hover:underline">Open API docs <ExternalLink className="h-3 w-3" /></a></CardContent></Card>
      <Card><CardHeader><CardTitle className="flex items-center gap-2"><Workflow className="h-4 w-4 text-primary" />Decision architecture</CardTitle></CardHeader><CardContent className="space-y-4 text-xs leading-relaxed text-muted-foreground"><p>Providers return structured probabilities. Deterministic policies resolve the permitted action. Outcomes feed calibration.</p><div className="rounded-md border border-border bg-background p-3 font-mono text-[11px] leading-6 text-foreground">Context → Provider → Probabilities<br />         → Policy → Final action<br />         → Outcome → Calibration</div><p>The AI provider never executes tools or infrastructure operations directly.</p></CardContent></Card>
      <Card><CardHeader><CardTitle className="flex items-center gap-2"><Shield className="h-4 w-4 text-primary" />Security posture</CardTitle></CardHeader><CardContent className="space-y-3 text-xs text-muted-foreground"><Setting label="Action execution" value="Never performed by DecisionOS" /><Setting label="Policy precedence" value="Hard deny → human review → model" /><Setting label="Sensitive context" value="Not displayed in decision listings" /></CardContent></Card>
    </div>
  </>;
}

function Setting({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="flex flex-col gap-1 border-b border-border/60 pb-3 last:border-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between"><span className="text-[11px] text-muted-foreground">{label}</span><span className={`break-all text-xs text-foreground ${mono ? "font-mono" : ""}`}>{value}</span></div>;
}
