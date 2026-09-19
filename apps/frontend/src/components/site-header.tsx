"use client";

import React from "react";
import { Zap, PhoneOff, Radio, Activity } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface SiteHeaderProps {
  backendOnline: boolean | null;
  isCallActive: boolean;
  onEndCall?: () => void;
  activeLeadId?: string | null;
}

export function SiteHeader({
  backendOnline,
  isCallActive,
  onEndCall,
  activeLeadId,
}: SiteHeaderProps) {
  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur-md">
      <div className="mx-auto flex h-14 w-full max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
        {/* Left: Brand Wordmark & Role */}
        <div className="flex items-center gap-3">
          <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Zap className="size-4 fill-current" />
          </div>

          <div className="flex items-center gap-2">
            <span className="font-semibold text-sm tracking-tight text-foreground">
              CIMET Reconnect
            </span>
            <span className="hidden text-xs text-muted-foreground sm:inline">·</span>
            <span className="hidden text-xs text-muted-foreground sm:inline">
              Energy Voice Console
            </span>
          </div>

          {activeLeadId && (
            <Badge
              variant="outline"
              className="ml-2 font-mono text-[11px] py-0 hidden md:inline-flex"
            >
              Session: {activeLeadId}
            </Badge>
          )}
        </div>

        {/* Right: Telemetry pill, End Call, and Theme Toggle */}
        <div className="flex items-center gap-2.5">
          {/* Engine Specs */}
          <div className="hidden lg:flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground px-2 py-1 rounded-md border border-border bg-muted/40">
            <span>Whisper-1</span>
            <span>·</span>
            <span>GPT-4o</span>
            <span>·</span>
            <span>TTS</span>
          </div>

          {/* Backend Connection */}
          <div className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs font-mono bg-card">
            <span
              className={`size-1.5 rounded-full ${
                backendOnline === true
                  ? "bg-emerald-500"
                  : backendOnline === false
                  ? "bg-destructive"
                  : "bg-amber-500 animate-pulse"
              }`}
            />
            <span className="text-[11px] text-muted-foreground">
              {backendOnline === true
                ? "Live"
                : backendOnline === false
                ? "Offline"
                : "Connecting..."}
            </span>
          </div>

          {isCallActive && onEndCall && (
            <Button
              variant="destructive"
              size="sm"
              onClick={onEndCall}
              className="h-8 text-xs gap-1.5 font-medium px-3"
            >
              <PhoneOff className="size-3.5" />
              <span>End Call</span>
            </Button>
          )}

          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
