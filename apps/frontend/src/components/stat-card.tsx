import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/**
 * BidRank StatCard: Small caption, big number/value, icon in a bordered tile.
 */
export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "default",
  size = "default",
  className,
}: {
  label: string;
  value: ReactNode | null;
  hint?: ReactNode;
  icon?: LucideIcon;
  tone?: "default" | "lime" | "emerald" | "amber" | "destructive";
  size?: "default" | "sm";
  className?: string;
}) {
  const compact = size === "sm";
  return (
    <div
      className={cn(
        "surface flex items-start justify-between gap-3 bg-card border border-border rounded-xl",
        compact ? "p-3" : "p-4",
        className,
      )}
    >
      <div className="min-w-0 flex-1">
        <p className="eyebrow truncate text-xs font-medium text-muted-foreground">{label}</p>
        <div
          className={cn(
            "bid-amount mt-1 leading-tight font-semibold tracking-tight text-foreground",
            compact ? "text-base sm:text-lg" : "text-lg sm:text-xl",
          )}
        >
          {value ?? <Skeleton className={cn(compact ? "h-5 w-16" : "h-6 w-24")} />}
        </div>
        {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
      </div>
      {Icon && <IconTile icon={Icon} tone={tone} size={compact ? "sm" : "default"} />}
    </div>
  );
}

/** A line icon inside a small bordered tile from BidRank. */
export function IconTile({
  icon: Icon,
  tone = "default",
  size = "default",
  className,
}: {
  icon: LucideIcon;
  tone?: "default" | "lime" | "emerald" | "amber" | "destructive" | "ink";
  size?: "default" | "sm" | "lg";
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-lg border transition-colors",
        size === "sm" ? "size-7" : size === "lg" ? "size-10" : "size-8",
        tone === "lime" || tone === "emerald"
          ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
          : tone === "amber"
          ? "border-amber-500/20 bg-amber-500/10 text-amber-600 dark:text-amber-400"
          : tone === "destructive"
          ? "border-destructive/20 bg-destructive/10 text-destructive"
          : tone === "ink"
          ? "border-transparent bg-primary text-primary-foreground"
          : "border-border bg-muted/40 text-foreground",
        className,
      )}
      aria-hidden="true"
    >
      <Icon className={size === "sm" ? "size-3.5" : size === "lg" ? "size-5" : "size-4"} />
    </span>
  );
}
