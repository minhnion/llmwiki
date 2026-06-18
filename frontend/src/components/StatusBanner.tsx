import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

export type BusyState = "idle" | "busy" | "success" | "error";

interface StatusBannerProps {
  state: BusyState;
  message: string;
}

export function StatusBanner({ state, message }: StatusBannerProps) {
  if (state === "idle" || !message) {
    return null;
  }
  const Icon = state === "busy" ? Loader2 : state === "success" ? CheckCircle2 : AlertCircle;
  const color =
    state === "error"
      ? "border-rose/30 bg-rose/10 text-rose"
      : state === "success"
        ? "border-forest/30 bg-forest/10 text-forest"
        : "border-cobalt/30 bg-cobalt/10 text-cobalt";
  return (
    <div className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm ${color}`}>
      <Icon className={state === "busy" ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
      <span>{message}</span>
    </div>
  );
}
