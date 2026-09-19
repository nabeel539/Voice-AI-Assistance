"use client";

import React, { useEffect } from "react";
import { AlertCircle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function ErrorPage({ error, reset }: ErrorProps) {
  useEffect(() => {
    // Log error for internal monitoring/debugging
    console.error("Application error boundary triggered:", error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-background text-foreground">
      <div className="max-w-md w-full border border-border bg-card p-6 rounded-xl shadow-xs text-center space-y-4">
        <div className="w-12 h-12 mx-auto rounded-full bg-destructive/10 text-destructive flex items-center justify-center">
          <AlertCircle className="w-6 h-6" />
        </div>
        
        <div className="space-y-1">
          <h2 className="text-base font-semibold text-foreground tracking-tight">
            An unexpected error occurred
          </h2>
          <p className="text-xs text-muted-foreground">
            Something went wrong while displaying the console. Please try refreshing the session.
          </p>
        </div>

        <div className="pt-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => reset()}
            className="gap-2 text-xs"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Try again
          </Button>
        </div>
      </div>
    </div>
  );
}
