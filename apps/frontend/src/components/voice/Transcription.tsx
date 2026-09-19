"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import { Bot, User, ShieldAlert, CheckCircle2, ArrowDown } from "lucide-react";
import { ConversationMessage } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface TranscriptionProps {
  messages: ConversationMessage[];
  className?: string;
  isProcessing?: boolean;
  headerAction?: React.ReactNode;
}

export function Transcription({
  messages,
  className = "",
  isProcessing = false,
  headerAction,
}: TranscriptionProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [isScrolledUp, setIsScrolledUp] = useState(false);
  const prevMessagesLength = useRef(messages.length);

  const scrollToBottom = useCallback((smooth = true) => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: smooth ? "smooth" : "auto",
      });
      setIsScrolledUp(false);
    }
  }, []);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    setIsScrolledUp(distanceFromBottom > 75);
  };

  useEffect(() => {
    if (!isScrolledUp) {
      scrollToBottom(true);
    }
    prevMessagesLength.current = messages.length;
  }, [messages, isProcessing, isScrolledUp, scrollToBottom]);

  const formatTime = (ts?: string) => {
    if (!ts) return "";
    try {
      const date = new Date(ts);
      return date.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return "";
    }
  };

  return (
    <div
      className={`surface flex flex-col bg-card border border-border rounded-xl overflow-hidden shadow-xs relative ${className}`}
    >
      {/* Header with integrated Voice Model / Header Action */}
      <div className="flex flex-wrap items-center justify-between px-3.5 py-2 border-b border-border bg-muted/20 shrink-0 gap-2">
        <div className="flex items-center gap-2">
          <span className="eyebrow uppercase tracking-wider font-semibold text-xs text-muted-foreground">
            Live Voice Transcript
          </span>
          <Badge variant="outline" className="font-mono text-[10px] py-0">
            {messages.length} turns
          </Badge>
          <div className="text-[11px] text-muted-foreground hidden sm:flex items-center gap-1 font-mono">
            <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span>Sync</span>
          </div>
        </div>

        {/* Integrated Voice Model container right in the chat header */}
        {headerAction && <div className="flex items-center gap-2">{headerAction}</div>}
      </div>

      {/* Transcript Scroll Area */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 p-3.5 overflow-y-auto space-y-3 scroll-smooth min-h-0"
      >
        {messages.length === 0 ? (
          <div className="h-full min-h-[140px] flex flex-col items-center justify-center text-center p-4 text-muted-foreground">
            <Bot className="size-7 mb-1.5 opacity-30 text-muted-foreground" />
            <p className="text-xs font-medium text-foreground">No active dialogue turns</p>
            <p className="text-[11px] text-muted-foreground mt-0.5 max-w-xs leading-normal">
              Click &quot;Start Recovery Call&quot; to begin voice recovery.
            </p>
          </div>
        ) : (
          messages.map((msg, index) => {
            const isAgent = msg.role === "assistant";
            const isSystem = msg.role === "system";
            const isLatest = index === messages.length - 1;

            if (isSystem) {
              return (
                <div key={index} className="flex items-center justify-center my-1">
                  <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground bg-muted/40 border border-border rounded-full px-2.5 py-0.5 font-mono">
                    <ShieldAlert className="size-3 text-amber-500" />
                    <span>{msg.content}</span>
                  </div>
                </div>
              );
            }

            return (
              <div
                key={index}
                className={`flex gap-2.5 max-w-[88%] transition-opacity duration-150 ${
                  isAgent ? "mr-auto" : "ml-auto flex-row-reverse"
                } ${isLatest ? "opacity-100" : "opacity-90 hover:opacity-100"}`}
              >
                {/* Avatar */}
                <div
                  className={`size-6 rounded-md flex items-center justify-center shrink-0 mt-0.5 border text-xs font-medium ${
                    isAgent
                      ? "bg-primary text-primary-foreground border-transparent"
                      : "bg-muted text-foreground border-border"
                  }`}
                >
                  {isAgent ? <Bot className="size-3" /> : <User className="size-3" />}
                </div>

                <div className="flex flex-col gap-0.5 min-w-0">
                  {/* Speaker Label & Timestamp */}
                  <div
                    className={`flex items-center gap-1.5 px-0.5 ${
                      isAgent ? "justify-start" : "justify-end"
                    }`}
                  >
                    <span className="text-[10px] font-medium text-muted-foreground">
                      {isAgent ? "Emma (CIMET Agent)" : "Customer"}
                    </span>
                    {msg.timestamp && (
                      <span className="text-[9px] text-muted-foreground/60 font-mono tabular">
                        {formatTime(msg.timestamp)}
                      </span>
                    )}
                  </div>

                  {/* Message Bubble */}
                  <div
                    className={`p-2.5 rounded-xl text-xs sm:text-sm leading-relaxed ${
                      isAgent
                        ? `bg-muted/40 text-foreground border ${
                            isLatest
                              ? "border-primary/40 ring-1 ring-primary/20"
                              : "border-border/80"
                          } rounded-tl-xs`
                        : `bg-primary text-primary-foreground ${
                            isLatest ? "ring-1 ring-primary/30" : ""
                          } rounded-tr-xs`
                    }`}
                  >
                    <p className="whitespace-pre-wrap break-words text-xs sm:text-[13px]">{msg.content}</p>

                    {/* Extracted Field & Confidence Metadata */}
                    {msg.field_name && (
                      <div className="mt-1.5 pt-1 border-t border-border/40 flex items-center gap-1.5">
                        <Badge
                          variant="secondary"
                          className="text-[9px] gap-1 px-1 py-0 font-mono"
                        >
                          <CheckCircle2 className="size-2.5 text-emerald-600 dark:text-emerald-400" />
                          <span>Saved: {msg.field_name}</span>
                        </Badge>
                        {msg.confidence !== undefined && (
                          <span className="text-[9px] text-muted-foreground font-mono">
                            {Math.round(msg.confidence * 100)}%
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}

        {/* Real-time Processing Turn Indicator */}
        {isProcessing && (
          <div className="flex gap-2.5 mr-auto max-w-[88%] animate-in fade-in-50 duration-200">
            <div className="size-6 rounded-md bg-primary/10 text-primary border border-primary/20 flex items-center justify-center shrink-0">
              <Bot className="size-3" />
            </div>
            <div className="p-2 rounded-xl bg-muted/40 border border-border/80 rounded-tl-xs text-xs text-muted-foreground flex items-center gap-2 font-mono">
              <span className="size-1.5 rounded-full bg-primary animate-ping" />
              <span>Whisper-1 &rarr; GPT-4o &rarr; TTS...</span>
            </div>
          </div>
        )}
      </div>

      {/* Floating 'Scroll to latest' button */}
      {isScrolledUp && (
        <div className="absolute bottom-3 right-4 z-10">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => scrollToBottom(true)}
            className="h-6 text-[11px] gap-1 shadow-md border border-border bg-background/95 backdrop-blur-xs font-medium text-foreground rounded-md px-2"
          >
            <ArrowDown className="size-3" />
            <span>Latest</span>
          </Button>
        </div>
      )}
    </div>
  );
}
