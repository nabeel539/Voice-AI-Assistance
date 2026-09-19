"use client";

import React from "react";
import { Volume2 } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface VoiceSelectorProps {
  currentVoice: string;
  onVoiceChange: (voice: string) => void;
  synthesizeVoice: boolean;
  onSynthesizeChange: (enabled: boolean) => void;
  className?: string;
}

const VOICES = [
  { id: "sage", name: "Sage (Recommended)", language: "en-AU/en-US" },
  { id: "alloy", name: "Alloy (Neutral)", language: "en-US" },
  { id: "echo", name: "Echo (Authoritative)", language: "en-US" },
  { id: "shimmer", name: "Shimmer (Expressive)", language: "en-US" },
  { id: "onyx", name: "Onyx (Professional)", language: "en-US" },
  { id: "fable", name: "Fable (Dynamic)", language: "en-GB" },
];

export function VoiceSelector({
  currentVoice,
  onVoiceChange,
  synthesizeVoice,
  onSynthesizeChange,
  className = "",
}: VoiceSelectorProps) {
  return (
    <div className={`flex items-center gap-2 text-xs shrink-0 ${className}`}>
      {/* Voice Model Selector */}
      <div className="flex items-center gap-1.5">
        <Volume2 className="size-3.5 text-muted-foreground" />
        <span className="text-[11px] font-medium text-muted-foreground hidden sm:inline">
          Voice:
        </span>
        <Select
          value={currentVoice}
          onValueChange={(val: string | null) => {
            if (val) onVoiceChange(val);
          }}
        >
          <SelectTrigger className="h-6 w-[120px] text-xs font-medium bg-card border-border rounded-md px-2 py-0">
            <SelectValue placeholder="Select voice" />
          </SelectTrigger>
          <SelectContent className="bg-popover border-border rounded-lg">
            {VOICES.map((v) => (
              <SelectItem key={v.id} value={v.id} className="text-xs">
                {v.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* TTS Audio Checkbox */}
      <label className="flex items-center gap-1 cursor-pointer select-none text-[11px] text-muted-foreground hover:text-foreground">
        <input
          type="checkbox"
          checked={synthesizeVoice}
          onChange={(e) => onSynthesizeChange(e.target.checked)}
          className="size-3 rounded border-border accent-primary cursor-pointer"
        />
        <span>TTS Audio</span>
      </label>

      {/* Model Pipeline Badges */}
      <div className="hidden md:flex items-center gap-1 pl-1.5 border-l border-border font-mono text-[10px] text-muted-foreground/70">
        <span>Whisper-1</span>
        <span>·</span>
        <span>GPT-4o</span>
        <span>·</span>
        <span>OpenAI TTS</span>
      </div>
    </div>
  );
}
