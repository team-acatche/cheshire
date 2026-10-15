import { cn } from "@/lib/utils";
import {TONES, toneColor, confidenceLevel, type Tone} from "./severity";

export function SeverityBadge({ tone, className }: {tone: Tone; className?: string}) {
    const s = TONES[tone];
    const Icon = s.icon;
    return (
        <span
            title={s.hint}
            className={cn(
                "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                s.text,
                className
            )}
            style={{ background: toneColor(tone, 0.12), borderColor: toneColor(tone, 0.4) }}
        >
            <Icon className="size-3" />
            {s.label}
        </span>
    );
}

export function ConfidenceMeter({ value, className }: {value?: number | null; className?: string}) {
    const lvl = confidenceLevel(value);
    if (!lvl || value == null) return null;
    return (
        <span
        title={`${Math.round(value * 100)} confidence: ${lvl.hint}`}
        className={cn("inline-flex items-center gap-1.5 text-[10px] font-medium text-zinc-400", className)}
        >
            <span aria-hidden className="flex-items-end gap-px">
                {[1, 2, 3].map((i) => (
                    <span
                    key={i}
                    className={cn("w-0.75 rounded-[1px]", i <= lvl.bars ? "bg-current" : "bg-zinc-300 dark:bg-zinc-600")}
                    style={{ height: 4 + i * 3}}
                    />
                ))}
            </span>
            {lvl.label}
        </span>
    );
}