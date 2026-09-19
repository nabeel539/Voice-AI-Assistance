"use client";

import React from "react";
import { Check, Circle, CheckCircle2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface CollectedFieldsGridProps {
  collectedFields: Record<string, any>;
  currentField?: string | null;
  isSubmitted?: boolean;
  className?: string;
}

interface FieldConfig {
  name: string;
  label: string;
  step: string;
}

const ALL_FIELDS: FieldConfig[] = [
  { name: "address", label: "Address", step: "Property" },
  { name: "suburb", label: "Suburb", step: "Property" },
  { name: "postcode", label: "Postcode", step: "Property" },
  { name: "energy_type", label: "Energy Type", step: "Energy" },
  { name: "electricity_meter_type", label: "Meter Type", step: "Energy" },
  { name: "has_solar", label: "Solar", step: "Energy" },
  { name: "electricity_usage", label: "Usage", step: "Usage" },
  { name: "usage_period", label: "Period", step: "Usage" },
  { name: "first_name", label: "First Name", step: "Customer" },
  { name: "last_name", label: "Last Name", step: "Customer" },
  { name: "email", label: "Email", step: "Customer" },
];

export function CollectedFieldsGrid({
  collectedFields,
  currentField,
  isSubmitted = false,
  className = "",
}: CollectedFieldsGridProps) {
  const collectedCount = ALL_FIELDS.filter((f) => f.name in collectedFields).length;
  const remainingCount = ALL_FIELDS.length - collectedCount;

  return (
    <div
      className={`surface bg-card border border-border rounded-xl p-3 shadow-xs flex flex-col justify-between space-y-2 shrink-0 ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <span className="eyebrow uppercase tracking-wider font-semibold text-[11px] text-muted-foreground">
            Captured Fields
          </span>
          <Badge variant="outline" className="font-mono text-[10px] py-0">
            {collectedCount} / {ALL_FIELDS.length}
          </Badge>
        </div>
        <div className="text-[11px] font-mono">
          {isSubmitted ? (
            <span className="text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1">
              <CheckCircle2 className="size-3" />
              Verified &amp; Submitted
            </span>
          ) : remainingCount === 0 ? (
            <span className="text-emerald-600 dark:text-emerald-400 font-medium">
              100% Captured
            </span>
          ) : (
            <span className="text-muted-foreground">{remainingCount} remaining</span>
          )}
        </div>
      </div>

      {/* Grid of Fields (Compact) */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-1.5">
        {ALL_FIELDS.map((field) => {
          const isCollected = field.name in collectedFields;
          const isCurrent = !isSubmitted && field.name === currentField;
          const rawValue = collectedFields[field.name];

          let displayValue = "";
          if (isCollected) {
            if (typeof rawValue === "boolean") {
              displayValue = rawValue ? "Yes" : "No";
            } else if (
              field.name === "electricity_usage" &&
              collectedFields["electricity_usage_unit"]
            ) {
              displayValue = `${rawValue} ${collectedFields["electricity_usage_unit"]}`;
            } else {
              displayValue = rawValue?.toString() || "";
            }
          }

          return (
            <div
              key={field.name}
              className={`flex flex-col p-1.5 px-2 rounded-md border text-[11px] transition-colors ${
                isCurrent
                  ? "bg-card border-primary/50 ring-1 ring-primary/20 shadow-2xs"
                  : isCollected
                  ? "bg-muted/30 border-border/70"
                  : "bg-muted/10 border-border/40 text-muted-foreground/50"
              }`}
            >
              <div className="flex items-center justify-between gap-1">
                <span className="text-[9px] uppercase font-mono text-muted-foreground truncate">
                  {field.label}
                </span>
                {isCollected ? (
                  <Check className="size-2.5 text-emerald-600 dark:text-emerald-400 shrink-0 stroke-[2.5]" />
                ) : isCurrent ? (
                  <span className="size-1.5 rounded-full bg-primary animate-pulse shrink-0" />
                ) : (
                  <Circle className="size-1.5 text-muted-foreground/30 shrink-0" />
                )}
              </div>

              <div className="font-mono text-xs font-semibold truncate text-foreground mt-0.5">
                {isCollected ? (
                  <span>{displayValue}</span>
                ) : isCurrent ? (
                  <span className="text-[10px] text-primary font-normal italic">
                    Listening...
                  </span>
                ) : (
                  <span className="text-[10px] text-muted-foreground/40 font-normal">—</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
