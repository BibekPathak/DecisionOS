import { Braces } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { listSchemas } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SchemasPage() {
  try {
    const schemas = await listSchemas();
    return <><PageHeader eyebrow="Contracts" title="Decision schemas" description="Versioned action spaces that define what a probabilistic provider may choose." />
      {!schemas.length ? <EmptyState title="No schemas registered" description="Register an immutable schema version through POST /v1/schemas." /> : <div className="grid gap-3 xl:grid-cols-2">{schemas.map((schema) => <Card key={`${schema.name}@${schema.version}`} className="p-5"><div className="flex items-start gap-3"><div className="rounded-md bg-primary/10 p-2 text-primary"><Braces className="h-4 w-4" /></div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h2 className="font-mono text-sm font-semibold">{schema.name}<span className="text-muted-foreground">@{schema.version}</span></h2><span className="rounded border border-border px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-muted-foreground">immutable</span></div>{schema.description && <p className="mt-1 text-xs text-muted-foreground">{schema.description}</p>}<div className="mt-4 flex flex-wrap gap-2">{schema.actions.map((action) => <span key={action} className="rounded-md border border-border bg-secondary/50 px-2 py-1 font-mono text-[11px]">{action}</span>)}</div><div className="mt-4 space-y-1">{schema.actions.map((action) => schema.action_descriptions[action] && <p key={action} className="text-[11px] text-muted-foreground"><span className="font-mono text-foreground">{action}</span> — {schema.action_descriptions[action]}</p>)}</div><p className="mt-4 text-[10px] text-muted-foreground">Registered {schema.created_at ? new Date(schema.created_at).toLocaleString() : "—"}</p></div></div></Card>)}</div>}
    </>;
  } catch (error) { return <><PageHeader eyebrow="Contracts" title="Decision schemas" /><ErrorState message={error instanceof Error ? error.message : "API unavailable"} /></>; }
}
