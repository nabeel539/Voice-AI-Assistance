"use client";

import React from "react";
import { Check, Circle, CheckCircle2 } from "lucide-react";
import { JourneyStep } from "@/types";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";

interface JourneyProgressProps {
  currentStep: JourneyStep;
  completedSteps: JourneyStep[];
  isSubmitted?: boolean;
  submissionRef?: string | null;
  className?: string;
}

const COLLECTION_STEPS: { id: JourneyStep; label: string; number: number }[] = [
  { id: "property_details", label: "Property", number: 1 },
  { id: "energy_details", label: "Energy", number: 2 },
  { id: "usage_details", label: "Usage", number: 3 },
  { id: "customer_details", label: "Customer", number: 4 },
];

export function JourneyProgress({
  currentStep,
  completedSteps,
  isSubmitted = false,
  submissionRef = null,
  className = "",
}: JourneyProgressProps) {
  const completedCollectionCount = Math.min(
    completedSteps.filter((s) => s !== "completion").length,
    4
  );
  const percent = Math.round((completedCollectionCount / 4) * 100);
  const isCompletionStep = currentStep === "completion" || isSubmitted;

  return (
    <div
      className={`surface bg-card border border-border rounded-xl p-3 shadow-xs space-y-2 shrink-0 ${className}`}
    >
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-1.5">
        <div className="flex items-center gap-2">
          <span className="eyebrow uppercase tracking-wider font-semibold text-[11px] text-muted-foreground">
            Journey Progress
          </span>
          <span className="text-xs font-mono font-medium text-foreground">
            {completedCollectionCount}/4 steps · {percent}%
          </span>
        </div>

        <div className="flex items-center gap-1.5 font-mono text-xs">
          {isSubmitted ? (
            <Badge
              variant="outline"
              className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[10px] gap-1 font-mono py-0"
            >
              <CheckCircle2 className="size-2.5" />
              <span>Submitted</span>
              {submissionRef && (
                <span className="text-muted-foreground ml-0.5 font-normal">
                  REF: {submissionRef}
                </span>
              )}
            </Badge>
          ) : isCompletionStep ? (
            <Badge variant="secondary" className="text-[10px] text-primary font-mono py-0">
              Ready for Submit
            </Badge>
          ) : (
            <span className="text-[11px] text-muted-foreground font-mono">
              Step {completedCollectionCount + 1}: {COLLECTION_STEPS[completedCollectionCount]?.label || "Active"}
            </span>
          )}
        </div>
      </div>

      <Progress value={percent} className="h-1" />

      {/* 4 Data Collection Steps + Final Sandbox Submit */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-1.5 pt-0.5">
        {COLLECTION_STEPS.map((step) => {
          const isComplete = completedSteps.includes(step.id);
          const isCurrent = step.id === currentStep && !isSubmitted;

          return (
            <div
              key={step.id}
              className={`flex items-center justify-between px-2 py-1.5 rounded-lg border text-xs transition-colors ${
                isComplete
                  ? "border-emerald-500/20 bg-emerald-500/5 text-foreground"
                  : isCurrent
                  ? "border-primary/40 bg-card ring-1 ring-primary/20 text-foreground"
                  : "border-border/60 bg-muted/20 text-muted-foreground/60"
              }`}
            >
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="font-mono text-[10px] text-muted-foreground shrink-0">
                  0{step.number}
                </span>
                <span className="font-medium truncate text-[11px]">{step.label}</span>
              </div>
              {isComplete ? (
                <Check className="size-3 text-emerald-600 dark:text-emerald-400 stroke-[2.5] shrink-0" />
              ) : isCurrent ? (
                <span className="size-1.5 rounded-full bg-primary animate-pulse shrink-0" />
              ) : (
                <Circle className="size-1.5 text-muted-foreground/30 shrink-0" />
              )}
            </div>
          );
        })}

        {/* 5th Final Submit Step */}
        <div
          className={`flex items-center justify-between px-2 py-1.5 rounded-lg border text-xs transition-colors ${
            isSubmitted
              ? "border-emerald-500/30 bg-emerald-500/10 text-foreground"
              : isCompletionStep
              ? "border-primary/50 bg-primary/5 text-primary"
              : "border-border/50 bg-muted/20 text-muted-foreground/60"
          }`}
        >
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="font-mono text-[10px] text-muted-foreground shrink-0">05</span>
            <span className="font-medium truncate text-[11px]">Submit</span>
          </div>
          {isSubmitted ? (
            <CheckCircle2 className="size-3 text-emerald-600 dark:text-emerald-400 shrink-0" />
          ) : isCompletionStep ? (
            <span className="size-1.5 rounded-full bg-primary animate-ping shrink-0" />
          ) : (
            <Circle className="size-1.5 text-muted-foreground/30 shrink-0" />
          )}
        </div>
      </div>
    </div>
  );
}
