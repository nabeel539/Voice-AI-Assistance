"use client";

import React, { useState, useRef, useEffect } from "react";
import { Play, Pause, Volume2, VolumeX, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface AudioPlayerProps {
  audioBase64?: string | null;
  audioUrl?: string | null;
  autoPlay?: boolean;
  onPlayStateChange?: (isPlaying: boolean) => void;
  onPlaybackStart?: () => void;
  onPlaybackComplete?: () => void;
  voiceName?: string;
  className?: string;
}

export function AudioPlayer({
  audioBase64,
  audioUrl,
  autoPlay = true,
  onPlayStateChange,
  onPlaybackStart,
  onPlaybackComplete,
  voiceName = "sage",
  className = "",
}: AudioPlayerProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isMuted, setIsMuted] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const onPlayStateChangeRef = useRef(onPlayStateChange);
  const onPlaybackStartRef = useRef(onPlaybackStart);
  const onPlaybackCompleteRef = useRef(onPlaybackComplete);

  useEffect(() => {
    onPlayStateChangeRef.current = onPlayStateChange;
    onPlaybackStartRef.current = onPlaybackStart;
    onPlaybackCompleteRef.current = onPlaybackComplete;
  });

  const resolvedSource = audioBase64
    ? `data:audio/mp3;base64,${audioBase64}`
    : audioUrl || null;

  useEffect(() => {
    if (audioRef.current && resolvedSource) {
      audioRef.current.src = resolvedSource;
      audioRef.current.load();
      if (autoPlay) {
        audioRef.current
          .play()
          .then(() => {
            setIsPlaying(true);
            onPlayStateChangeRef.current?.(true);
            onPlaybackStartRef.current?.();
          })
          .catch((err) => {
            console.warn("Autoplay prevented by browser policy:", err);
            setIsPlaying(false);
            onPlayStateChangeRef.current?.(false);
          });
      }
    }
  }, [resolvedSource, autoPlay]);

  const togglePlay = () => {
    if (!audioRef.current || !resolvedSource) return;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
      onPlayStateChangeRef.current?.(false);
    } else {
      audioRef.current
        .play()
        .then(() => {
          setIsPlaying(true);
          onPlayStateChangeRef.current?.(true);
          onPlaybackStartRef.current?.();
        })
        .catch((e) => console.error("Playback error:", e));
    }
  };

  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime);
    }
  };

  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(audioRef.current.duration);
    }
  };

  const handleEnded = () => {
    setIsPlaying(false);
    setCurrentTime(0);
    onPlayStateChangeRef.current?.(false);
    onPlaybackCompleteRef.current?.();
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const time = parseFloat(e.target.value);
    if (audioRef.current) {
      audioRef.current.currentTime = time;
      setCurrentTime(time);
    }
  };

  const toggleMute = () => {
    if (audioRef.current) {
      audioRef.current.muted = !isMuted;
      setIsMuted(!isMuted);
    }
  };

  const replay = () => {
    if (audioRef.current) {
      audioRef.current.currentTime = 0;
      audioRef.current.play();
      setIsPlaying(true);
      onPlayStateChangeRef.current?.(true);
      onPlaybackStartRef.current?.();
    }
  };

  const formatTime = (secs: number) => {
    if (isNaN(secs)) return "0:00";
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${s < 10 ? "0" : ""}${s}`;
  };

  if (!resolvedSource) {
    return null;
  }

  return (
    <div
      className={`surface flex items-center gap-3 bg-muted/40 border border-border rounded-xl px-3.5 py-2 text-sm shadow-xs ${className}`}
    >
      <audio
        ref={audioRef}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onEnded={handleEnded}
      />

      <Button
        type="button"
        variant="outline"
        size="icon"
        className="size-8 rounded-lg shrink-0 border-border bg-card hover:bg-muted"
        onClick={togglePlay}
      >
        {isPlaying ? (
          <Pause className="size-3.5 fill-current" />
        ) : (
          <Play className="size-3.5 fill-current ml-0.5" />
        )}
      </Button>

      <div className="flex-1 flex items-center gap-2 min-w-0">
        <span className="text-xs text-muted-foreground font-mono tabular shrink-0">
          {formatTime(currentTime)}
        </span>
        <input
          type="range"
          min={0}
          max={duration || 100}
          step={0.1}
          value={currentTime}
          onChange={handleSeek}
          className="w-full h-1 bg-border rounded-lg appearance-none cursor-pointer accent-primary"
        />
        <span className="text-xs text-muted-foreground font-mono tabular shrink-0">
          {formatTime(duration)}
        </span>
      </div>

      <div className="flex items-center gap-1 shrink-0">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-7 rounded-md text-muted-foreground hover:text-foreground"
          onClick={replay}
          title="Replay from start"
        >
          <RotateCcw className="size-3" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-7 rounded-md text-muted-foreground hover:text-foreground"
          onClick={toggleMute}
          title={isMuted ? "Unmute" : "Mute"}
        >
          {isMuted ? <VolumeX className="size-3.5" /> : <Volume2 className="size-3.5" />}
        </Button>
        <Badge
          variant="secondary"
          className="text-[10px] font-mono uppercase tracking-wider px-1.5 py-0.5"
        >
          {voiceName}
        </Badge>
      </div>
    </div>
  );
}
