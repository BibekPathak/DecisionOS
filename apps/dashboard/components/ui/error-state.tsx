import { AlertCircle } from "lucide-react";

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center rounded-lg border border-red-500/20 bg-red-500/5 px-6 text-center">
      <AlertCircle className="mb-3 h-5 w-5 text-red-400" />
      <p className="text-sm font-medium">Could not load data</p>
      <p className="mt-1 max-w-lg break-words text-xs text-muted-foreground">{message}</p>
    </div>
  );
}
