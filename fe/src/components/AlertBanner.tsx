import { AlertCircle, Bus, MapPin, WifiOff } from "lucide-react";

export type AlertTone = "info" | "warning" | "success";

export type AlertItem = {
  id: string;
  tone: AlertTone;
  icon: "stop" | "arriving" | "moving" | "offline";
  message: string;
};

const iconFor = (k: AlertItem["icon"]) => {
  switch (k) {
    case "stop":
      return MapPin;
    case "arriving":
      return AlertCircle;
    case "moving":
      return Bus;
    case "offline":
      return WifiOff;
  }
};

const toneClasses: Record<AlertTone, string> = {
  info: "border-info/40 bg-info/10 text-foreground",
  warning: "border-warning/50 bg-warning/15 text-foreground",
  success: "border-primary/40 bg-primary/10 text-foreground",
};

const iconToneClasses: Record<AlertTone, string> = {
  info: "bg-info/20 text-info",
  warning: "bg-warning/25 text-warning",
  success: "bg-primary/20 text-primary",
};

export function AlertBanner({ alert }: { alert: AlertItem | null }) {
  if (!alert) return null;
  const Icon = iconFor(alert.icon);
  return (
    <div
      key={alert.id}
      className={`flex items-center gap-3 rounded-2xl border px-3 py-2.5 shadow-card backdrop-blur-md animate-fade-in ${toneClasses[alert.tone]}`}
    >
      <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${iconToneClasses[alert.tone]}`}>
        <Icon className="h-4 w-4" />
      </div>
      <p className="text-sm font-medium leading-snug">{alert.message}</p>
    </div>
  );
}
