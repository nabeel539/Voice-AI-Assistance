"use client";

import React, { useState } from "react";
import { CheckCircle2, ChevronDown, ChevronUp, Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface SubmissionSuccessBannerProps {
  referenceId: string;
  message: string;
  payload?: Record<string, any> | null;
  className?: string;
}

export function SubmissionSuccessBanner({
  referenceId,
  message,
  payload,
  className = "",
}: SubmissionSuccessBannerProps) {
  const [showPayload, setShowPayload] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyRef = () => {
    navigator.clipboard.writeText(referenceId);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className={`surface bg-card border border-border rounded-xl p-4 sm:p-5 shadow-xs text-foreground space-y-3 ${className}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 className="size-4.5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-semibold text-foreground tracking-tight">
                Journey Successfully Submitted
              </h4>
              <Badge
                variant="outline"
                className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-mono text-[11px] py-0"
              >
                Sandbox 200 OK
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">{message}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div className="flex items-center gap-1.5 rounded-lg border border-border bg-muted/40 px-2.5 py-1 text-xs font-mono">
            <span className="text-muted-foreground">REF:</span>
            <span className="font-semibold text-foreground">{referenceId}</span>
            <button
              onClick={copyRef}
              className="text-muted-foreground hover:text-foreground ml-1 p-0.5"
              title="Copy reference ID"
            >
              {copied ? (
                <Check className="size-3.5 text-emerald-600 dark:text-emerald-400" />
              ) : (
                <Copy className="size-3.5" />
              )}
            </button>
          </div>

          {payload && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowPayload(!showPayload)}
              className="h-8 text-xs gap-1 font-mono rounded-lg"
            >
              <span>{showPayload ? "Hide" : "Payload"}</span>
              {showPayload ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
            </Button>
          )}
        </div>
      </div>

      {showPayload && payload && (
        <div className="pt-3 border-t border-border">
          <div className="flex items-center justify-between text-[11px] text-muted-foreground mb-1.5 font-mono">
            <span>External CIMET Energy Partner Payload:</span>
            <span>Schema v1.0</span>
          </div>
          <pre className="p-3 bg-muted/40 border border-border rounded-lg text-xs font-mono text-foreground overflow-x-auto max-h-60 leading-normal">
            {JSON.stringify(payload, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
