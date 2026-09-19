"use client";

import React from "react";
import { AlertTriangle, User, CheckCircle2 } from "lucide-react";
import { HandoffPackage } from "@/types";
import { Badge } from "@/components/ui/badge";

interface HandoffAlertProps {
  handoff: HandoffPackage;
  className?: string;
}

export function HandoffAlert({ handoff, className = "" }: HandoffAlertProps) {
  const reasonLabels: Record<string, { label: string; tone: "destructive" | "amber" | "default" }> = {
    payment: { label: "Payment / Card Boundary", tone: "destructive" },
    human_request: { label: "Customer Requested Human", tone: "default" },
    frustration: { label: "Customer Frustration", tone: "amber" },
    confusion: { label: "Customer Confusion", tone: "amber" },
    advice_request: { label: "Retailer Advice Boundary", tone: "amber" },
    sensitive: { label: "Sensitive Situation", tone: "destructive" },
    off_script: { label: "Off-Script Request", tone: "default" },
    low_confidence: { label: "Low Voice Confidence", tone: "amber" },
    repeated_failure: { label: "Max Validation Retries Exceeded", tone: "amber" },
  };

  const reasonInfo = reasonLabels[handoff.escalation_reason] || {
    label: handoff.escalation_reason.replace("_", " "),
    tone: "amber" as const,
  };

  const collectedEntries = Object.entries(handoff.collected_fields || {});
  const collectedCount = collectedEntries.length;
  const missingCount = (handoff.missing_fields || []).length;

  return (
    <div
      className={`bg-card border border-border rounded-xl p-5 shadow-xs text-foreground space-y-4 ${className}`}
    >
      {/* Primary Escalation Header */}
      <div className="flex flex-wrap items-start justify-between gap-3 pb-3 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-amber-500/20 bg-amber-500/10 text-amber-600 dark:text-amber-400">
            <AlertTriangle className="size-4.5" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold tracking-tight text-foreground">
                Human Escalation Required
              </h3>
              <Badge
                variant="outline"
                className="font-mono text-[11px] py-0 border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400"
              >
                {reasonInfo.label}
              </Badge>
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground font-mono">
              Ref: <span className="font-semibold text-foreground">{handoff.handoff_id}</span> · Lead:{" "}
              <span className="font-semibold text-foreground">{handoff.lead_id}</span>
            </p>
          </div>
        </div>

        {/* Fields Preservation Counter */}
        <div className="flex items-center gap-2 font-mono text-xs">
          <span className="rounded-md border border-border bg-muted/40 px-2 py-0.5 text-[11px] text-muted-foreground">
            {collectedCount} / 11 Fields Preserved
          </span>
          {missingCount > 0 && (
            <span className="rounded-md border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-600 dark:text-amber-400">
              {missingCount} Remaining
            </span>
          )}
        </div>
      </div>

      {/* Triggering Customer Statement */}
      <div className="space-y-1.5">
        <span className="block text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Triggering Customer Utterance
        </span>
        <div
          dir="auto"
          className="rounded-lg border border-border bg-muted/40 p-3.5 text-sm text-foreground leading-relaxed"
        >
          {handoff.customer_statement ? `"${handoff.customer_statement}"` : "No utterance recorded"}
        </div>
      </div>

      {/* Suggested Operator Opening Script */}
      <div className="space-y-1.5">
        <span className="block text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          Suggested Operator Action
        </span>
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-3.5 text-sm font-medium text-foreground leading-snug">
          {handoff.suggested_operator_action || "Review preserved fields and assist customer directly."}
        </div>
      </div>

      {/* Summary & Preserved Fields Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
        {/* Context Summary */}
        <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-1">
          <span className="block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Escalation Context
          </span>
          <p className="text-xs text-muted-foreground leading-relaxed">
            {handoff.summary || "Automated voice session escalated per deterministic safety guardrail."}
          </p>
        </div>

        {/* Preserved Fields */}
        <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-1.5 overflow-hidden">
          <span className="block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Preserved State ({collectedCount} captured)
          </span>
          <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto overflow-x-hidden pr-1">
            {collectedEntries.length > 0 ? (
              collectedEntries.map(([k, v]) => (
                <span
                  key={k}
                  className="inline-flex items-center gap-1 rounded-md border border-border bg-card px-2 py-0.5 text-[11px] font-mono text-foreground break-all"
                >
                  <span className="text-muted-foreground">{k}:</span>
                  <span className="font-semibold">{String(v)}</span>
                </span>
              ))
            ) : (
              <span className="text-xs text-muted-foreground italic">
                No fields collected prior to escalation.
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
