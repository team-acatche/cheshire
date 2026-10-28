import type { Severity, VulnerabilityFinding } from "@/types/VulnerabilityFinding"
import { authFetch } from "@/lib/auth"
import { parseTimestamp } from "@/lib/helpers/format_timestamps"
import { getBoxes, isUnanchored } from "@/components/document-preview/helpers"

// ── Severity / status metadata ────────────────────────────────────────────────

export const SEVERITIES: Severity[] = ["major", "minor", "observation"]

export const SEVERITY_META: Record<
  Severity,
  { label: string; plural: string; weight: number; hex: string; priority: string }
> = {
  major:       { label: "Major",       plural: "major",        weight: 12, hex: "#dc2626", priority: "Resolve before approval" },
  minor:       { label: "Minor",       plural: "minor",        weight: 4,  hex: "#ca8a04", priority: "Resolve before development" },
  observation: { label: "Observation", plural: "observations", weight: 1,  hex: "#0033b2", priority: "Optional, recommended" },
}

const RANK: Record<Severity, number> = { major: 3, minor: 2, observation: 1 }

export type ComplianceStatus = "compliant" | "needs_improvement" | "non_compliant"

export const STATUS_META: Record<ComplianceStatus, { label: string; hex: string; blurb: string }> = {
  compliant: {
    label: "Compliant",
    hex: "#059669",
    blurb: "No major or minor gaps were found.",
  },
  needs_improvement: {
    label: "Needs Improvement",
    hex: "#ca8a04",
    blurb: "No major gaps, but compliance gaps remain and should be resolved before development.",
  },
  non_compliant: {
    label: "Non-Compliant",
    hex: "#dc2626",
    blurb: "Major gaps block approval until they are resolved.",
  },
}

export interface SeverityCounts {
  major: number
  minor: number
  observation: number
}

/** 100 minus weighted gaps (major 12, minor 4, observation 1), floored at 0. */
export function scoreFromCounts(c: SeverityCounts): number {
  const penalty =
    c.major * SEVERITY_META.major.weight +
    c.minor * SEVERITY_META.minor.weight +
    c.observation * SEVERITY_META.observation.weight
  return Math.max(0, Math.min(100, Math.round(100 - penalty)))
}

export function statusFromCounts(c: SeverityCounts): ComplianceStatus {
  if (c.major > 0) return "non_compliant"
  if (c.minor > 0) return "needs_improvement"
  return "compliant"
}

// ── Report model ──────────────────────────────────────────────────────────────

export interface ReportFinding {
  id: string
  title: string
  description: string
  severity: Severity
  missing: boolean
  confidence: number | null
  confidenceLabel: string
  pages: number[]
  location: string
  recommendations: string[]
  references: string[]
}

export interface RecommendationGroup {
  text: string
  severity: Severity
  findingIds: string[]
}

export interface ReportData {
  documentName: string
  sessionId: string
  userName: string
  userEmail: string
  generatedAt: Date
  assessedAt: Date | null
  findings: ReportFinding[]
  counts: SeverityCounts
  total: number
  missingCount: number
  score: number
  status: ComplianceStatus
  avgConfidence: number | null
  recommendations: RecommendationGroup[]
}

export interface BuildReportInput {
  findings: VulnerabilityFinding[]
  documentName: string
  sessionId: string
  userName: string
  userEmail: string
  assessedAt?: string | null
  generatedAt?: Date
}

const isMissing = (f: VulnerabilityFinding) => f.scope === "document" || /^missing\b/i.test(f.title)

export function confidenceLabel(c: number | null | undefined): string {
  if (c == null) return "Not rated"
  if (c >= 0.95) return `${c.toFixed(1)} (High)`
  if (c >= 0.75) return `${c.toFixed(1)} (Medium)`
  return `${c.toFixed(1)} (Low)`
}

function describeLocation(pages: number[]): string {
  if (pages.length === 0) return "Document-wide"
  if (pages.length === 1) return `Page ${pages[0]}`
  return `Pages ${pages.join(", ")}`
}

export function buildReport(input: BuildReportInput): ReportData {
  const prepared = input.findings.map((f) => {
    const pages = isUnanchored(f)
      ? []
      : [...new Set(getBoxes(f).map((b) => b.page_no ?? f.page_no))].sort((a, b) => a - b)
    return { f, pages }
  })

  prepared.sort(
    (a, b) =>
      RANK[b.f.severity ?? "observation"] - RANK[a.f.severity ?? "observation"] ||
      (a.pages[0] ?? Infinity) - (b.pages[0] ?? Infinity) ||
      a.f.title.localeCompare(b.f.title)
  )

  const findings: ReportFinding[] = prepared.map(({ f, pages }, i) => ({
    id: `F-${String(i + 1).padStart(2, "0")}`,
    title: f.title,
    description: f.description,
    severity: f.severity ?? "observation",
    missing: isMissing(f),
    confidence: f.confidence ?? null,
    confidenceLabel: confidenceLabel(f.confidence),
    pages,
    location: describeLocation(pages),
    recommendations: (f.recommendations ?? []).filter((r) => r.trim()),
    references: (f.web_references ?? []).filter((r) => r.trim()),
  }))

  const counts: SeverityCounts = { major: 0, minor: 0, observation: 0 }
  for (const f of findings) counts[f.severity]++

  const rated = findings.filter((f) => f.confidence != null)
  const avgConfidence = rated.length
    ? rated.reduce((sum, f) => sum + (f.confidence ?? 0), 0) / rated.length
    : null

  // Same advice shows up on several findings: list it once, at its highest priority.
  const groups = new Map<string, RecommendationGroup>()
  for (const f of findings) {
    for (const rec of f.recommendations) {
      const key = rec.trim().toLowerCase().replace(/\s+/g, " ")
      const existing = groups.get(key)
      if (existing) {
        if (!existing.findingIds.includes(f.id)) existing.findingIds.push(f.id)
      } else {
        groups.set(key, { text: rec.trim(), severity: f.severity, findingIds: [f.id] })
      }
    }
  }
  const recommendations = [...groups.values()].sort(
    (a, b) => RANK[b.severity] - RANK[a.severity] || b.findingIds.length - a.findingIds.length
  )

  return {
    documentName: input.documentName,
    sessionId: input.sessionId,
    userName: input.userName,
    userEmail: input.userEmail,
    generatedAt: input.generatedAt ?? new Date(),
    assessedAt: parseTimestamp(input.assessedAt),
    findings,
    counts,
    total: findings.length,
    missingCount: findings.filter((f) => f.missing).length,
    score: scoreFromCounts(counts),
    status: statusFromCounts(counts),
    avgConfidence,
    recommendations,
  }
}

export function summaryText(r: ReportData): string {
  const status = STATUS_META[r.status]
  if (r.total === 0) {
    return `Cheshire found no gaps in ${r.documentName}. ${status.blurb}`
  }
  const parts = SEVERITIES.filter((s) => r.counts[s] > 0).map(
    (s) => `${r.counts[s]} ${r.counts[s] === 1 ? SEVERITY_META[s].label.toLowerCase() : SEVERITY_META[s].plural}`
  )
  const list = parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}` : parts[0]
  const missing = r.missingCount
    ? ` ${r.missingCount} of these ${r.missingCount === 1 ? "is" : "are"} required content that is missing from the document.`
    : ""
  const conf = r.avgConfidence != null ? ` Average finding confidence is ${r.avgConfidence.toFixed(2)}.` : ""
  return `Cheshire identified ${r.total} ${r.total === 1 ? "gap" : "gaps"} in ${r.documentName}: ${list}.${missing} ${status.blurb}${conf}`
}

// ── Formatting ────────────────────────────────────────────────────────────────

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
const pad = (n: number) => String(n).padStart(2, "0")

/** Locale-independent on purpose, so the PDF (Latin-1 fonts) never gets odd spacing characters. */
export function formatReportDate(d: Date | null | undefined, withTime = true): string {
  if (!d) return "Not available"
  const date = `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`
  return withTime ? `${date}, ${pad(d.getHours())}:${pad(d.getMinutes())}` : date
}

export function formatShortDate(s: string | null | undefined): string {
  const d = parseTimestamp(s)
  return d ? `${d.getDate()} ${MONTHS[d.getMonth()]}` : "?"
}

/** DocumentName_Assessment_Date.pdf */
export function reportFileName(documentName: string, date: Date): string {
  const base =
    documentName
      .replace(/\.pdf$/i, "")
      .replace(/[^A-Za-z0-9_-]+/g, "_")
      .replace(/^_+|_+$/g, "") || "Document"
  return `${base}_Assessment_${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}.pdf`
}

// ── Trend (multiple assessments) ──────────────────────────────────────────────

export interface TrendPoint extends SeverityCounts {
  session_id: string
  title: string
  assessed_at: string | null
  total: number
  missing: number
}

export async function fetchAssessmentTrend(limit = 20): Promise<TrendPoint[]> {
  try {
    const res = await authFetch(`/api/v1/reports/trend?limit=${limit}`)
    return res.ok ? ((await res.json()) as TrendPoint[]) : []
  } catch {
    return []
  }
}

export interface TrendCoord {
  x: number
  y: number
  score: number
  point: TrendPoint
}

/** Shared by the on-screen chart and the PDF so both draw the same line. */
export function trendGeometry(
  points: TrendPoint[],
  width: number,
  height: number,
  pad = { l: 28, r: 12, t: 10, b: 22 }
): TrendCoord[] {
  const innerW = width - pad.l - pad.r
  const innerH = height - pad.t - pad.b
  return points.map((point, i) => {
    const score = scoreFromCounts(point)
    return {
      x: pad.l + (points.length === 1 ? innerW / 2 : (innerW * i) / (points.length - 1)),
      y: pad.t + innerH * (1 - score / 100),
      score,
      point,
    }
  })
}

/** SVG arc starting at 12 o'clock and sweeping clockwise. */
export function arcPath(cx: number, cy: number, r: number, fraction: number): string {
  const f = Math.min(Math.max(fraction, 0), 0.9999)
  if (f <= 0) return ""
  const a0 = -Math.PI / 2
  const a1 = a0 + f * 2 * Math.PI
  const x0 = cx + r * Math.cos(a0)
  const y0 = cy + r * Math.sin(a0)
  const x1 = cx + r * Math.cos(a1)
  const y1 = cy + r * Math.sin(a1)
  return `M ${x0} ${y0} A ${r} ${r} 0 ${f > 0.5 ? 1 : 0} 1 ${x1} ${y1}`
}