import { useState } from "react"
import type { Severity } from "@/types/VulnerabilityFinding"
import { cn } from "@/lib/utils"
import {
  SEVERITIES,
  SEVERITY_META,
  formatReportDate,
  formatShortDate,
  scoreFromCounts,
  trendGeometry,
  type SeverityCounts,
  type TrendPoint,
} from "@/lib/report"
import { parseTimestamp } from "@/lib/helpers/format_timestamps"

// ── Compliance gauge ──────────────────────────────────────────────────────────

export function ComplianceGauge({ score, color, size = 140 }: { score: number; color: string; size?: number }) {
  const r = 54
  const circumference = 2 * Math.PI * r
  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`Compliance score ${score} out of 100`}
    >
      <svg viewBox="0 0 140 140" className="size-full -rotate-90">
        <circle cx="70" cy="70" r={r} fill="none" stroke="currentColor" strokeOpacity={0.12} strokeWidth={12} />
        <circle
          cx="70"
          cy="70"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={12}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - score / 100)}
          style={{ transition: "stroke-dashoffset 700ms ease" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold tabular-nums" style={{ color }}>{score}</span>
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">out of 100</span>
      </div>
    </div>
  )
}

// ── Gap distribution by severity (click a bar to drill down) ──────────────────

interface SeverityDistributionProps {
  counts: SeverityCounts
  total: number
  selected: Severity | null
  onSelect: (s: Severity | null) => void
}

export function SeverityDistribution({ counts, total, selected, onSelect }: SeverityDistributionProps) {
  return (
    <div className="space-y-2">
      {SEVERITIES.map((s) => {
        const meta = SEVERITY_META[s]
        const n = counts[s]
        const pct = total ? Math.round((n / total) * 100) : 0
        const active = selected === s
        return (
          <button
            key={s}
            type="button"
            disabled={n === 0}
            aria-pressed={active}
            onClick={() => onSelect(active ? null : s)}
            title={n === 0 ? `No ${meta.label.toLowerCase()} gaps` : `Show ${meta.label.toLowerCase()} findings`}
            className={cn(
              "group block w-full rounded-md px-2 py-1.5 text-left transition-colors",
              n > 0 && "hover:bg-muted",
              active && "bg-muted ring-1 ring-border",
              n === 0 && "cursor-not-allowed opacity-50"
            )}
          >
            <div className="mb-1 flex items-baseline justify-between text-xs">
              <span className="font-medium">{meta.label}</span>
              <span className="tabular-nums text-muted-foreground">
                <span className="font-semibold text-foreground">{n}</span> · {pct}%
              </span>
            </div>
            <div className="h-2.5 w-full overflow-hidden rounded-full bg-border/60">
              <div
                className="h-full rounded-full"
                style={{ width: `${pct}%`, background: meta.hex, transition: "width 600ms ease" }}
              />
            </div>
          </button>
        )
      })}
    </div>
  )
}

// ── Trend across assessments ──────────────────────────────────────────────────

const W = 600
const H = 190

export function TrendChart({ points, currentSessionId }: { points: TrendPoint[]; currentSessionId: string }) {
  const currentIdx = points.findIndex((p) => p.session_id === currentSessionId)
  const [hover, setHover] = useState<number | null>(null)

  if (points.length < 2) {
    return (
      <div className="flex h-40 items-center justify-center rounded-md border border-dashed px-4 text-center text-sm text-muted-foreground">
        Assess more documents to see how compliance changes over time.
      </div>
    )
  }

  const coords = trendGeometry(points, W, H)
  const shownIdx = hover ?? (currentIdx >= 0 ? currentIdx : points.length - 1)
  const shown = coords[shownIdx]
  const showAllLabels = points.length <= 8
  const line = coords.map((c) => `${c.x},${c.y}`).join(" ")

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Compliance score across assessments">
        {[0, 50, 100].map((g) => {
          const y = 10 + (H - 10 - 22) * (1 - g / 100)
          return (
            <g key={g}>
              <line x1={28} x2={W - 12} y1={y} y2={y} stroke="currentColor" strokeOpacity={0.12} strokeDasharray="3 4" />
              <text x={22} y={y + 3} textAnchor="end" fontSize={10} fill="currentColor" fillOpacity={0.55}>{g}</text>
            </g>
          )
        })}

        <polyline points={line} fill="none" stroke="var(--primary)" strokeWidth={2.5} strokeLinejoin="round" />

        {coords.map((c, i) => {
          const isCurrent = i === currentIdx
          const isShown = i === shownIdx
          return (
            <g key={c.point.session_id}>
              {(showAllLabels || i === 0 || i === coords.length - 1) && (
                <text x={c.x} y={H - 6} textAnchor="middle" fontSize={10} fill="currentColor" fillOpacity={0.55}>
                  {formatShortDate(c.point.assessed_at)}
                </text>
              )}
              <circle
                cx={c.x}
                cy={c.y}
                r={isShown ? 7 : isCurrent ? 6 : 4.5}
                fill={isCurrent ? "var(--primary)" : "var(--background)"}
                stroke="var(--primary)"
                strokeWidth={2}
                tabIndex={0}
                className="cursor-pointer outline-none"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
              >
                <title>{`${c.point.title}: ${c.score}/100`}</title>
              </circle>
            </g>
          )
        })}
      </svg>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-md bg-muted/50 px-3 py-2 text-xs">
        <div className="min-w-0">
          <div className="truncate font-medium">
            {shown.point.title}
            {shownIdx === currentIdx && <span className="ml-2 text-primary">This report</span>}
          </div>
          <div className="text-muted-foreground">{formatReportDate(parseTimestamp(shown.point.assessed_at))}</div>
        </div>
        <div className="flex items-center gap-3 tabular-nums">
          <span className="text-sm font-semibold">{scoreFromCounts(shown.point)}/100</span>
          {SEVERITIES.map((s) => (
            <span key={s} className="inline-flex items-center gap-1" title={SEVERITY_META[s].label}>
              <span className="size-2 rounded-full" style={{ background: SEVERITY_META[s].hex }} />
              {shown.point[s]}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}