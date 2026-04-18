import { useEffect, useState } from "react";
import { ChevronUp, Clock, MapPin } from "lucide-react";

function formatEta(seconds: number) {
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))} sec`;
  const m = Math.round(seconds / 60);
  return `${m} min`;
}

export type EtaSheetProps = {
  nextStopName: string | null;
  nextStopEta: number | null;
  upcoming: Array<{ stop_name: string; eta_seconds: number }>;
};

export function EtaSheet({ nextStopName, nextStopEta, upcoming }: EtaSheetProps) {
  const [expanded, setExpanded] = useState(false);
  // console.log("Upcooming, ", upcoming)
  // Lock body scroll when expanded
  useEffect(() => {
    if (expanded) {
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = "";
      };
    }
  }, [expanded]);

  return (
    <>
      {/* Backdrop */}
      {expanded && (
        <button
          aria-label="Close ETA sheet"
          onClick={() => setExpanded(false)}
          className="fixed inset-0 z-40 bg-background/60 backdrop-blur-sm animate-fade-in"
        />
      )}

      {/* Bottom sheet */}
      <div
        className={`fixed inset-x-0 bottom-0 z-50 rounded-t-3xl border-t border-border bg-gradient-card shadow-sheet transition-transform duration-300 ${expanded ? "translate-y-0" : "translate-y-0"
          }`}
      >
        <button
          onClick={() => setExpanded((v) => !v)}
          className="w-full px-5 pt-3 pb-2 flex flex-col items-center gap-2"
          aria-label={expanded ? "Collapse ETAs" : "Expand ETAs"}
        >
          <div className="h-1.5 w-12 rounded-full bg-muted" />
        </button>

        <div className="px-5 pb-5">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/15">
                <MapPin className="h-5 w-5 text-primary" />
              </div>
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Next stop</p>
                {nextStopName && nextStopEta != null ? (
                  <p className="truncate font-semibold">
                    <span className="text-primary">{nextStopName}</span>
                    <span className="text-muted-foreground"> in </span>
                    <span>{formatEta(nextStopEta)}</span>
                  </p>
                ) : (
                  <p className="text-sm text-muted-foreground">Calculating…</p>
                )}
              </div>
            </div>
            <button
              onClick={() => setExpanded((v) => !v)}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-secondary text-foreground transition-transform hover:bg-primary hover:text-primary-foreground"
              aria-label="Show all ETAs"
            >
              <ChevronUp className={`h-5 w-5 transition-transform ${expanded ? "rotate-180" : ""}`} />
            </button>
          </div>

          {expanded && (
            <div className="mt-5 animate-fade-in">
              <p className="mb-3 text-[11px] uppercase tracking-wider text-muted-foreground">
                Upcoming stops
              </p>
              <ul className="space-y-2">
                {upcoming.map((s, i) => (
                  <li
                    key={`${s.stop_name}-${i}`}
                    className="flex items-center justify-between gap-3 rounded-xl border border-border bg-secondary/40 p-3"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-background">
                        <span className="text-xs font-bold text-primary">{i + 1}</span>
                      </div>
                      <span className="truncate font-medium">{s.stop_name}</span>
                    </div>
                    <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                      <Clock className="h-3.5 w-3.5" />
                      <span className="font-mono">{formatEta(s.eta_seconds)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
