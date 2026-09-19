"use client";

import React from "react";
import { Mic, Phone, PhoneCall, RefreshCw, User } from "lucide-react";
import { Lead } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface LeadsQueueProps {
  leads: Lead[];
  activeLeadId?: string | null;
  activeChannel?: string;
  onSelectLead: (leadId: string, channel?: string) => void;
  isStartingCall?: boolean;
  isLoading?: boolean;
  onRefresh?: () => void;
  className?: string;
}

export function LeadsQueue({
  leads,
  activeLeadId,
  activeChannel = "browser",
  onSelectLead,
  isStartingCall = false,
  isLoading = false,
  onRefresh,
  className = "",
}: LeadsQueueProps) {
  return (
    <div
      className={`surface bg-card border border-border rounded-xl flex flex-col h-full shadow-xs ${className}`}
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/20">
        <div className="flex items-center gap-2">
          <span className="eyebrow uppercase tracking-wider font-semibold text-xs text-muted-foreground">
            Dropped Leads Queue
          </span>
          <Badge variant="outline" className="font-mono text-[11px] py-0">
            {leads.length}
          </Badge>
        </div>
        {onRefresh && (
          <Button
            variant="ghost"
            size="icon"
            className="size-7 rounded-lg text-muted-foreground hover:text-foreground"
            onClick={onRefresh}
            disabled={isLoading}
            title="Refresh Leads"
          >
            <RefreshCw className={`size-3.5 ${isLoading ? "animate-spin" : ""}`} />
          </Button>
        )}
      </div>

      <div className="flex-1 p-2.5 overflow-y-auto space-y-2">
        {leads.length === 0 ? (
          <div className="p-6 text-center text-xs text-muted-foreground">
            {isLoading ? "Loading leads..." : "No dropped leads found"}
          </div>
        ) : (
          leads.map((lead) => {
            const isActive = lead.lead_id === activeLeadId;

            return (
              <div
                key={lead.lead_id}
                className={`p-3 rounded-lg border transition-colors text-xs flex flex-col gap-2 ${
                  isActive
                    ? "bg-card border-primary/50 ring-1 ring-primary/20 shadow-2xs"
                    : "bg-background border-border/70 hover:border-border hover:bg-muted/20"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 font-mono font-semibold text-foreground">
                    <User className="size-3.5 text-muted-foreground" />
                    <span>{lead.lead_id}</span>
                  </div>
                  <Badge variant="secondary" className="font-mono text-[10px] py-0">
                    {lead.last_completed_step.replace("_details", "")}
                  </Badge>
                </div>

                <div className="flex items-center justify-between text-muted-foreground text-[11px] font-mono">
                  <span className="flex items-center gap-1">
                    <Phone className="size-3 text-muted-foreground/70" />
                    {lead.test_contact || "No contact"}
                  </span>
                  <span className="text-[10px] capitalize text-muted-foreground/80">
                    Step: {lead.last_completed_step.replace(/_/g, " ")}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-1.5 mt-0.5">
                  <Button
                    size="sm"
                    variant={isActive && (!activeChannel || activeChannel === "browser") ? "secondary" : "default"}
                    onClick={() => onSelectLead(lead.lead_id, "browser")}
                    disabled={isStartingCall}
                    className="h-8 text-[11px] font-medium gap-1 rounded-lg"
                    title="Start Voice Session via Browser Mic"
                  >
                    <Mic className="size-3" />
                    <span>Browser</span>
                  </Button>

                  <Button
                    size="sm"
                    variant={isActive && activeChannel !== "browser" ? "secondary" : "outline"}
                    onClick={() => onSelectLead(lead.lead_id, "twilio")}
                    disabled={isStartingCall}
                    className="h-8 text-[11px] font-medium gap-1 rounded-lg border-emerald-600/30 hover:bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                    title="Dial Real Phone via Twilio Telephony"
                  >
                    <PhoneCall className="size-3 text-emerald-600 dark:text-emerald-400" />
                    <span>Phone Call</span>
                  </Button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
