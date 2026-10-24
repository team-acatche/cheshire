import { Check, ScanLine, Square } from "lucide-react"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"
import type { EvaluationProgress, ProgressEvent } from "@/lib/helpers/evaluate_document"
import { TONES, toneColor, type Tone } from "./severity"

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`
const etaText = (s: number | null) =>
  s == null ? null : s < 60 ? "under a minute left" : `~${Math.round(s / 60)} min left`

function Ring({ percent, size = 18 }: { percent: number; size?: number }) {
  const r = (size - 3) / 2
  const c = 2 * Math.PI * r
  return (
    <svg width={size} height={size} className="shrink-0 text-primary">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor" strokeOpacity={0.2} strokeWidth={2.5} />
      <circle
        cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor" strokeWidth={2.5}
        strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - percent / 100)}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dashoffset 600ms ease" }}
      />
    </svg>
  )
}

/** Overlay drawn on top of a PDF page while it is being audited / after it was audited. */
export function ScanOverlay({ active, scanned }: { active: boolean; scanned: boolean }) {
  if (!active && !scanned) return null
  return (
    <>
      {active && <div className="scan-active" aria-hidden />}
      {scanned && !active && (
        <span
          aria-hidden
          className="pointer-events-none absolute right-2 top-2 z-6 inline-flex items-center gap-1 rounded-full bg-emerald-600/90 px-2 py-0.5 text-[10px] font-medium text-white shadow"
        >
          <Check className="size-3" /> Audited
        </span>
      )}
    </>
  )
}

interface Props {
  progress: EvaluationProgress
  events: ProgressEvent[]
  follow: boolean
  onFollowChange: (v: boolean) => void
  onJumpToPage: (page: number) => void
  onCancel?: () => void
  container?: HTMLElement | null
}

export function AnalysisProgressPill({
  progress, events, follow, onFollowChange, onJumpToPage, onCancel, container,
}: Props) {
  const pct = Math.round(progress.percent)
  const stageLabel = progress.stages[progress.stage_index]?.label ?? "Starting…"
  const label =
    progress.stage === "auditing" && progress.total > 0
      ? `Auditing ${Math.min(progress.completed + 1, progress.total)}/${progress.total}`
      : stageLabel
  const eta = etaText(progress.eta_seconds)
  const recent = events.slice(-12).reverse()

  const activeSet = new Set(progress.active_pages)
  const scannedSet = new Set(progress.scanned_pages)
  const cells = Array.from({ length: Math.min(progress.page_count, 150) }, (_, i) => i + 1)

  return (
    <div className="inline-flex items-center rounded-full border bg-background text-xs text-muted-foreground shadow-sm">
      <Popover>
        <PopoverTrigger asChild>
          <button className="inline-flex items-center gap-2 rounded-full py-1 pl-3 pr-3 transition-colors hover:bg-muted">
            <Ring percent={progress.percent} />
            <span>{label}</span>
            <span className="font-semibold tabular-nums text-foreground">{pct}%</span>
          </button>
        </PopoverTrigger>

        <PopoverContent container={container} align="start" className="w-95 gap-0 p-0">
          {/* Header + bar */}
          <div className="space-y-2 border-b bg-muted/40 px-4 py-3">
            <div className="flex items-baseline justify-between gap-2">
              <div className="truncate text-sm font-semibold">{progress.message}</div>
              <div className="shrink-0 text-xs tabular-nums text-muted-foreground">{mmss(progress.elapsed_seconds)}</div>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-border">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${progress.percent}%`,
                  transition: "width 700ms ease",
                  backgroundImage: "linear-gradient(90deg, var(--mb-grad-from), var(--mb-grad-to))",
                }}
              />
            </div>
            {eta && <div className="text-[11px] text-muted-foreground">{eta} in section audit</div>}
          </div>

          {/* Stepper */}
          <ol className="grid grid-cols-5 gap-1 px-4 pt-3">
            {progress.stages.map((s, i) => {
              const done = i < progress.stage_index
              const current = i === progress.stage_index
              return (
                <li key={s.key} className="flex flex-col items-center gap-1 text-center">
                  <span
                    className={cn(
                      "flex size-5 items-center justify-center rounded-full text-[10px] font-semibold",
                      done && "bg-primary/15 text-primary",
                      current && "btn-gradient animate-pulse",
                      !done && !current && "bg-muted text-muted-foreground"
                    )}
                  >
                    {done ? <Check className="size-3" /> : i + 1}
                  </span>
                  <span className={cn("text-[10px] leading-tight", current ? "text-foreground" : "text-muted-foreground")}>
                    {s.label}
                  </span>
                </li>
              )
            })}
          </ol>

          {/* Live counters */}
          <div className="flex gap-2 px-4 pt-3">
            {(["major", "minor", "observation"] as Tone[]).map((t) => {
              const Icon = TONES[t].icon
              return (
                <span
                  key={t}
                  title={TONES[t].hint}
                  className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-full border px-2 py-1 text-xs"
                  style={{ background: toneColor(t, 0.1), borderColor: toneColor(t, 0.4) }}
                >
                  <Icon className={cn("size-3.5", TONES[t].text)} />
                  <span className="font-semibold tabular-nums text-foreground">
                    {progress.counts[t as "major" | "minor" | "observation"]}
                  </span>
                </span>
              )
            })}
          </div>

          {/* Page radar */}
          {cells.length > 0 && (
            <div className="px-4 pt-3">
              <div className="mb-1.5 flex items-center justify-between text-[11px] font-semibold uppercase text-muted-foreground">
                <span className="inline-flex items-center gap-1"><ScanLine className="size-3" /> Page radar</span>
                <label className="inline-flex cursor-pointer items-center gap-1.5 font-normal normal-case">
                  <input type="checkbox" checked={follow} onChange={(e) => onFollowChange(e.target.checked)} />
                  Follow along
                </label>
              </div>
              <div className="flex flex-wrap gap-1">
                {cells.map((p) => (
                  <button
                    key={p}
                    type="button"
                    title={`Page ${p}`}
                    onClick={() => onJumpToPage(p)}
                    className={cn(
                      "size-3.5 rounded-xs transition-colors",
                      activeSet.has(p) ? "animate-pulse bg-primary ring-1 ring-primary"
                        : scannedSet.has(p) ? "bg-primary/60"
                        : "bg-muted"
                    )}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Live feed */}
          <div className="px-4 pb-3 pt-3">
            <div className="mb-1 text-[11px] font-semibold uppercase text-muted-foreground">Live feed</div>
            <ul className="scroll-transparent max-h-40 space-y-1 overflow-y-auto">
              {recent.length === 0 && <li className="text-xs text-muted-foreground">Warming up…</li>}
              {recent.map((e) => (
                <li key={e.seq} className="flex items-start gap-2 text-xs animate-in fade-in slide-in-from-top-1 duration-300">
                  <span
                    className="mt-1.5 size-1.5 shrink-0 rounded-full"
                    style={{
                      background: e.kind === "finding" && e.severity
                        ? toneColor(e.severity)
                        : "var(--muted-foreground)",
                    }}
                  />
                  <span className={cn("min-w-0 flex-1", e.kind === "finding" ? "text-foreground" : "text-muted-foreground")}>
                    {e.message}
                  </span>
                  <span className="shrink-0 tabular-nums text-[10px] text-muted-foreground">{mmss(Math.round(e.t))}</span>
                </li>
              ))}
            </ul>
          </div>
        </PopoverContent>
      </Popover>

      {onCancel && (
        <button
          type="button"
          onClick={onCancel}
          className="mr-1 rounded-full border border-red-600 p-1 hover:bg-red-100 dark:border-red-400 dark:hover:bg-red-950"
          aria-label="Cancel analysis"
          title="Cancel analysis"
        >
          <Square className="h-3 w-3 text-red-600 dark:text-red-400" />
        </button>
      )}
    </div>
  )
}