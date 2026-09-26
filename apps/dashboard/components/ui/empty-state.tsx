import { Activity } from "lucide-react";

export function EmptyState({ title = "No data yet", description = "Data will appear here as decisions are recorded." }: { title?: string; description?: string }) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center rounded-lg border border-dashed border-border px-6 text-center">
      <Activity className="mb-3 h-5 w-5 text-muted-foreground" />
      <p className="text-sm font-medium">{title}</p>
      <p className="mt-1 max-w-sm text-xs text-muted-foreground">{description}</p>
    </div>
  );
}
