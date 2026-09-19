"use client";

import React, { useState, useRef, useEffect } from "react";
import { Mic, Square, Send, Loader2, Volume2, Keyboard } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface SpeechInputProps {
  onAudioSubmit?: (audioBlob: Blob) => void;
  onAudioRecorded?: (audioBlob: Blob) => void;
  onTextSubmit?: (text: string) => void;
  onRecordingStateChange?: (recording: boolean) => void;
  disabled?: boolean;
  isDisabled?: boolean;
  isProcessing?: boolean;
  isSpeaking?: boolean;
}

export function SpeechInput({
  onAudioSubmit,
  onAudioRecorded,
  onTextSubmit,
  onRecordingStateChange,
  disabled = false,
  isDisabled = false,
  isProcessing = false,
  isSpeaking = false,
}: SpeechInputProps) {
  const isInputDisabled = disabled || isDisabled;
  const emitAudio = onAudioSubmit || onAudioRecorded;

  const [isRecording, setIsRecording] = useState(false);
  const [recordDuration, setRecordDuration] = useState(0);
  const [textInput, setTextInput] = useState("");
  const [useTextInput, setUseTextInput] = useState(false);
  const [micError, setMicError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
        mediaRecorderRef.current.stop();
      }
    };
  }, []);

  const startRecording = async () => {
    setMicError(null);
    audioChunksRef.current = [];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "audio/webm",
      });

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        if (audioBlob.size > 0 && emitAudio) {
          emitAudio(audioBlob);
        }
      };

      mediaRecorder.start(100);
      mediaRecorderRef.current = mediaRecorder;
      setIsRecording(true);
      onRecordingStateChange?.(true);
      setRecordDuration(0);

      timerRef.current = setInterval(() => {
        setRecordDuration((prev) => prev + 1);
      }, 1000);
    } catch (err: any) {
      console.error("Microphone access error:", err);
      setMicError(
        err.name === "NotAllowedError"
          ? "Microphone access blocked. Use text mode below."
          : "Could not access microphone."
      );
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      mediaRecorderRef.current.stop();
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setIsRecording(false);
    onRecordingStateChange?.(false);
  };

  const cancelRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      mediaRecorderRef.current.onstop = null;
      mediaRecorderRef.current.stop();
      if (mediaRecorderRef.current.stream) {
        mediaRecorderRef.current.stream.getTracks().forEach((t) => t.stop());
      }
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setIsRecording(false);
    onRecordingStateChange?.(false);
    setRecordDuration(0);
    audioChunksRef.current = [];
  };

  const handleTextSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!textInput.trim() || isInputDisabled || isProcessing) return;
    if (onTextSubmit) {
      onTextSubmit(textInput.trim());
    }
    setTextInput("");
  };

  const formatSeconds = (sec: number) => {
    const mins = Math.floor(sec / 60);
    const s = sec % 60;
    return `${mins}:${s < 10 ? "0" : ""}${s}`;
  };

  return (
    <div className="surface w-full bg-card border border-border rounded-xl p-3 shadow-xs">
      {micError && (
        <div className="text-xs text-destructive mb-2 px-1 flex items-center gap-1.5 font-mono">
          <span>{micError}</span>
        </div>
      )}

      {useTextInput ? (
        <form onSubmit={handleTextSubmit} className="flex items-center gap-2">
          <input
            type="text"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            placeholder="Type customer reply (e.g. 'Yes, my postcode is 4000')..."
            disabled={isInputDisabled || isProcessing}
            className="flex-1 text-xs sm:text-sm bg-muted/40 border border-input rounded-lg px-3 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            autoFocus
          />
          <Button
            type="submit"
            size="sm"
            disabled={!textInput.trim() || isInputDisabled || isProcessing}
            className="shrink-0 h-9 rounded-lg px-3"
          >
            {isProcessing ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Send className="size-3.5" />
            )}
          </Button>
          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => setUseTextInput(false)}
                  className="size-9 text-muted-foreground hover:text-foreground rounded-lg"
                >
                  <Mic className="size-4" />
                </Button>
              }
            />
            <TooltipContent>Switch to Voice Mic</TooltipContent>
          </Tooltip>
        </form>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            {isRecording ? (
              <div className="flex items-center gap-2.5">
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  onClick={stopRecording}
                  className="gap-1.5 font-medium rounded-lg h-8 px-3"
                >
                  <Square className="size-3.5 fill-current" />
                  <span>Stop &amp; Submit</span>
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={cancelRecording}
                  className="h-8 text-xs text-muted-foreground rounded-lg"
                >
                  Cancel
                </Button>
                <div className="flex items-center gap-1.5 text-xs text-destructive font-mono font-medium pl-1">
                  <span className="size-2 rounded-full bg-destructive animate-ping" />
                  <span className="tabular">{formatSeconds(recordDuration)}</span>
                </div>
              </div>
            ) : isProcessing ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground font-medium py-1 font-mono">
                <Loader2 className="size-3.5 animate-spin text-primary" />
                <span>Processing turn audio...</span>
              </div>
            ) : isSpeaking ? (
              <div className="flex items-center gap-2 text-xs text-primary font-medium py-1 font-mono">
                <Volume2 className="size-3.5 animate-pulse" />
                <span>AI Agent speaking to customer...</span>
              </div>
            ) : (
              <div className="flex items-center gap-2.5">
                <Button
                  type="button"
                  size="sm"
                  variant="default"
                  onClick={startRecording}
                  disabled={isInputDisabled}
                  className="gap-2 font-medium rounded-lg h-8 px-3.5"
                >
                  <Mic className="size-3.5" />
                  <span>Press to Speak</span>
                </Button>
                <span className="text-xs text-muted-foreground hidden sm:inline">
                  Click to capture customer response
                </span>
              </div>
            )}
          </div>

          <Tooltip>
            <TooltipTrigger
              render={
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setUseTextInput(true)}
                  disabled={isRecording}
                  className="h-8 text-xs text-muted-foreground hover:text-foreground gap-1.5 rounded-lg"
                >
                  <Keyboard className="size-3.5" />
                  <span>Text Mode</span>
                </Button>
              }
            />
            <TooltipContent>Switch to text keyboard</TooltipContent>
          </Tooltip>
        </div>
      )}
    </div>
  );
}
