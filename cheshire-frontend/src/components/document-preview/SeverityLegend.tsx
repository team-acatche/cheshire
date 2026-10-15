import { cn } from "@/lib/utils";
import { TONES, TONE_ORDER, toneColor, type Tone } from "./severity";

interface Props {
  counts: Record<Tone, number>;
  hidden: Set<Tone>;
  onToggle: (t: Tone) => void;
}

export function SeverityLegend({ counts, hidden, onToggle }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 px-1 shrink-0">
      {TONE_ORDER.map((tone) => {
        const s = TONES[tone];
        const Icon = s.icon;
        const off = hidden.has(tone);
        const n = counts[tone];
        return (
          <button
            key={tone}
            type="button"
            disabled={n === 0}
            aria-pressed={!off}
            title={`${s.hint}. Click to ${off ? "show" : "hide"}.`}
            onClick={() => onToggle(tone)}
            className={cn(
            "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-1 text-xs transition-all",
            n === 0 && "cursor-not-allowed opacity-40",
            off && "opacity-50 line-through"
            )}
            style={off ? undefined : { background: toneColor(tone, 0.1), borderColor: toneColor(tone, 0.4) }}
          >
            <Icon className={cn("size-3.5", s.text)} />
            <span className="hidden @3xl:inline">{s.label}</span>
            <span className="font-semibold tabular-nums">{n}</span>
          </button>
        );
      })}

      <span className="ml-auto hidden items-center gap-2 text-[11px] text-muted-foreground md:inline-flex">
        <span className="inline-block w-5 border-b-2 border-solid border-current" /> verified
        <span className="inline-block w-5 border-b-2 border-dashed border-current" /> lower confidence
      </span>
    </div>
  );
}