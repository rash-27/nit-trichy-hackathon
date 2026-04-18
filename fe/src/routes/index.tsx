import { createFileRoute, Link } from "@tanstack/react-router";
import { BUSES } from "@/lib/transit-data";
import { Bus, ChevronRight, Radio } from "lucide-react";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Resilient Transit — Live Bus Tracking" },
      { name: "description", content: "Real-time bus tracking for Varanasi public transit." },
      { property: "og:title", content: "Resilient Transit — Live Bus Tracking" },
      { property: "og:description", content: "Track buses live across the city in real time." },
    ],
  }),
  component: Index,
});

function Index() {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border bg-gradient-card backdrop-blur sticky top-0 z-10">
        <div className="mx-auto max-w-3xl px-5 py-6">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-primary shadow-glow">
              <Radio className="h-5 w-5 text-primary-foreground" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight">Resilient Transit</h1>
              <p className="text-xs text-muted-foreground">Live bus tracking · Varanasi</p>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-5 py-6">
        <div className="mb-5 flex items-baseline justify-between">
          <h2 className="text-2xl font-bold">Available buses</h2>
          <span className="text-xs text-muted-foreground">{BUSES.length} routes</span>
        </div>

        <ul className="space-y-3">
          {BUSES.map((bus) => (
            <li key={bus.number}>
              <Link
                to="/route/$busNumber"
                params={{ busNumber: bus.number }}
                className="group flex items-center gap-4 rounded-2xl border border-border bg-gradient-card p-4 shadow-card transition-all hover:border-primary/50 hover:shadow-glow"
              >
                <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-secondary">
                  <Bus className="h-6 w-6 text-primary" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-bold text-primary">{bus.number}</span>
                    {bus.scheduled ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-primary">
                        <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
                        Live
                      </span>
                    ) : (
                      <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        Off-service
                      </span>
                    )}
                  </div>
                  <h3 className="mt-1 truncate font-semibold">{bus.name}</h3>
                  <p className="truncate text-xs text-muted-foreground">{bus.route}</p>
                </div>
                <ChevronRight className="h-5 w-5 text-muted-foreground transition-transform group-hover:translate-x-1 group-hover:text-primary" />
              </Link>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}
