import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Home } from "lucide-react";

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-background text-foreground">
      <div className="max-w-md w-full border border-border bg-card p-6 rounded-xl shadow-xs text-center space-y-4">
        <div className="text-3xl font-mono font-bold text-muted-foreground">404</div>
        <div className="space-y-1">
          <h2 className="text-base font-semibold text-foreground tracking-tight">
            Page Not Found
          </h2>
          <p className="text-xs text-muted-foreground">
            The requested console resource could not be found.
          </p>
        </div>
        <div>
          <Link href="/">
            <Button variant="outline" size="sm" className="gap-2 text-xs">
              <Home className="w-3.5 h-3.5" />
              Return to Operator Console
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}
