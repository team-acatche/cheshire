import { useEffect, useMemo, useRef, useState } from "react"
import { ArrowLeft, ChevronDown, Download, ExternalLink, ShieldCheck } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { cn } from "@/lib/utils"
import type { AuthUser } from "@/lib/auth"
import type { Severity, VulnerabilityFinding } from "@/types/VulnerabilityFinding"
import {
  SEVERITIES,
  SEVERITY_META,
  STATUS_META,
  buildReport,
  fetchAssessmentTrend,
  formatReportDate,
  summaryText,
  type RecommendationGroup,
  type ReportFinding,
  type TrendPoint,
} from "@/lib/report"
import { ComplianceGauge, SeverityDistribution, TrendChart } from "./ReportCharts"

type Filter = Severity | "missing" | null

interface ReportPageProps {
  sessionId: string
  documentName: string
  findings: VulnerabilityFinding[]
  loading: boolean
  user: AuthUser
  /** Used for the assessment date when the trend list doesn't include this session. */
  fallbackAssessedAt?: string | null
  onClose: () => void
}

function SeverityPill({ severity, className }: { severity: Severity; className?: string }) {
  const { hex, label } = SEVERITY_META[severity]
  return (
    <span
      className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide", className)}
      style={{ color: hex, background: `${hex}1a`, borderColor: `${hex}66` }}
    >
      {label}
    </span>
  )
}

function Stat({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div className="rounded-lg border bg-background px-3 py-2.5">
      <div className="text-2xl font-semibold tabular-nums" style={color ? { color } : undefined}>{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  )
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="truncate text-sm" title={value}>{value}</dd>
    </div>
  )
}

function FindingCard({ finding, open, onToggle }: { finding: ReportFinding; open: boolean; onToggle: () => void }) {
  const { hex } = SEVERITY_META[finding.severity]
  return (
    <div className="overflow-hidden rounded-lg border bg-card" style={{ borderLeft: `4px solid ${hex}` }}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/50"
      >
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-xs font-mono text-muted-foreground">{finding.id}</span>
            <SeverityPill severity={finding.severity} />
            {finding.missing && (
              <span className="rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Missing content
              </span>
            )}
            <span className="ml-auto text-xs text-muted-foreground">{finding.location}</span>
          </div>
          <div className="text-sm font-semibold leading-snug">{finding.title}</div>
        </div>
        <ChevronDown className={cn("mt-1 size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="space-y-4 border-t px-4 py-4 text-sm">
          <section className="space-y-1">
            <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Evidence</h4>
            <p className="leading-relaxed">{finding.description}</p>
            <p className="text-xs text-muted-foreground">Found in: {finding.location}</p>
          </section>

          <section className="space-y-1">
            <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Confidence</h4>
            <p className="text-xs">{finding.confidenceLabel}</p>
          </section>

          {finding.recommendations.length > 0 && (
            <section className="space-y-1">
              <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Recommendations</h4>
              <ol className="list-decimal space-y-1 pl-5 leading-relaxed">
                {finding.recommendations.map((r, i) => <li key={i}>{r}</li>)}
              </ol>
            </section>
          )}

          {finding.references.length > 0 && (
            <section className="space-y-1">
              <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">References</h4>
              <ul className="space-y-1">
                {finding.references.map((url, i) => (
                  <li key={i}>
                    <a
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex max-w-full items-center gap-1 text-xs text-blue-600 hover:underline dark:text-blue-400"
                    >
                      <ExternalLink className="size-3 shrink-0" />
                      <span className="truncate">{url}</span>
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  )
}

export default function ReportPage({
  sessionId,
  documentName,
  findings,
  loading,
  user,
  fallbackAssessedAt,
  onClose,
}: ReportPageProps) {
  const [trend, setTrend] = useState<TrendPoint[]>([])
  const [filter, setFilter] = useState<Filter>(null)
  const [openIds, setOpenIds] = useState<Set<string>>(new Set())
  const [exporting, setExporting] = useState(false)
  const [generatedAt] = useState(() => new Date())
  const findingsRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchAssessmentTrend().then((points) => { if (!cancelled) setTrend(points) })
    return () => { cancelled = true }
  }, [sessionId])

  const assessedAt = trend.find((p) => p.session_id === sessionId)?.assessed_at ?? fallbackAssessedAt ?? null

  const report = useMemo(
    () =>
      buildReport({
        findings,
        documentName,
        sessionId,
        userName: user.full_name ?? user.username ?? user.email,
        userEmail: user.email,
        assessedAt,
        generatedAt,
      }),
    [findings, documentName, sessionId, user, assessedAt, generatedAt]
  )

  const status = STATUS_META[report.status]

  const visible = useMemo(() => {
    if (filter === null) return report.findings
    if (filter === "missing") return report.findings.filter((f) => f.missing)
    return report.findings.filter((f) => f.severity === filter)
  }, [report.findings, filter])

  const drillDown = (next: Filter) => {
    setFilter(next)
    if (next !== null) findingsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
  }

  const toggleOpen = (id: string) =>
    setOpenIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const allOpen = visible.length > 0 && visible.every((f) => openIds.has(f.id))
  const toggleAll = () =>
    setOpenIds((prev) => {
      const next = new Set(prev)
      for (const f of visible) {
        if (allOpen) next.delete(f.id)
        else next.add(f.id)
      }
      return next
    })

  const handleExport = async () => {
    setExporting(true)
    try {
      // Loaded on demand so the PDF renderer stays out of the main bundle.
      const { exportReportPdf } = await import("@/lib/helpers/export_report")
      const fileName = await exportReportPdf({ ...report, generatedAt: new Date() }, trend)
      toast.success("Report exported", { description: fileName })
    } catch (err) {
      console.error("report export failed:", err)
      toast.error("Couldn't export the report", { description: "Please try again." })
    } finally {
      setExporting(false)
    }
  }

  const priorityGroups = SEVERITIES.map((s) => ({
    severity: s,
    items: report.recommendations.filter((r: RecommendationGroup) => r.severity === s),
  })).filter((g) => g.items.length > 0)

  const filterChips: { key: Filter; label: string; count: number }[] = [
    { key: null, label: "All", count: report.total },
    ...SEVERITIES.map((s) => ({ key: s as Filter, label: SEVERITY_META[s].label, count: report.counts[s] })),
    { key: "missing", label: "Missing content", count: report.missingCount },
  ]

  return (
    <div className="h-full overflow-y-auto bg-muted/30 scroll-transparent">
      <div className="mx-auto max-w-5xl space-y-5 p-4 md:p-8">
        {/* Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button variant="outline" size="sm" onClick={onClose}>
            <ArrowLeft /> Back to document
          </Button>
          <Button size="sm" onClick={handleExport} disabled={loading || exporting}>
            {exporting ? <Spinner /> : <Download />}
            {exporting ? "Preparing PDF…" : "Export PDF"}
          </Button>
        </div>

        {/* Header + metadata */}
        <Card>
          <CardHeader>
            <CardDescription className="text-[11px] font-semibold uppercase tracking-wider">
              Compliance Assessment Report
            </CardDescription>
            <CardTitle className="wrap-break-word text-xl md:text-2xl">{documentName}</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-4">
              <MetaItem label="Assessed" value={formatReportDate(report.assessedAt)} />
              <MetaItem label="Report generated" value={formatReportDate(report.generatedAt)} />
              <MetaItem label="Generated by" value={report.userName} />
              <MetaItem label="Session ID" value={report.sessionId} />
            </dl>
          </CardContent>
        </Card>

        {/* Executive summary */}
        <Card>
          <CardHeader>
            <CardTitle>Executive summary</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-3">
                <Skeleton className="h-8 w-48" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-2/3" />
              </div>
            ) : (
              <div className="flex flex-col items-center gap-6 md:flex-row md:items-start">
                <ComplianceGauge score={report.score} color={status.hex} />
                <div className="min-w-0 flex-1 space-y-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-semibold"
                      style={{ color: status.hex, background: `${status.hex}14`, borderColor: `${status.hex}66` }}
                    >
                      {report.status === "compliant" && <ShieldCheck className="size-4" />}
                      {status.label}
                    </span>
                    <span className="text-xs text-muted-foreground">Overall compliance status</span>
                  </div>
                  <p className="text-sm leading-relaxed text-muted-foreground">{summaryText(report)}</p>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    <Stat label="Total gaps" value={report.total} />
                    <Stat label="Major" value={report.counts.major} color={SEVERITY_META.major.hex} />
                    <Stat label="Minor" value={report.counts.minor} color={SEVERITY_META.minor.hex} />
                    <Stat label="Observations" value={report.counts.observation} color={SEVERITY_META.observation.hex} />
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Dashboard */}
        <div className="grid gap-5 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Gaps by severity</CardTitle>
              <CardDescription>Select a bar to jump to those findings.</CardDescription>
            </CardHeader>
            <CardContent>
              <SeverityDistribution
                counts={report.counts}
                total={report.total}
                selected={SEVERITIES.includes(filter as Severity) ? (filter as Severity) : null}
                onSelect={drillDown}
              />
              {report.missingCount > 0 && (
                <button
                  type="button"
                  onClick={() => drillDown("missing")}
                  className="mt-3 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                >
                  {report.missingCount} {report.missingCount === 1 ? "gap is" : "gaps are"} missing required content
                </button>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Compliance trend</CardTitle>
              <CardDescription>Score across your completed assessments.</CardDescription>
            </CardHeader>
            <CardContent>
              <TrendChart points={trend} currentSessionId={sessionId} />
            </CardContent>
          </Card>
        </div>

        {/* Detailed findings */}
        <div ref={findingsRef} className="scroll-mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Detailed findings</CardTitle>
              <CardDescription>
                {report.avgConfidence != null
                  ? `Showing ${visible.length} of ${report.total}. Average confidence ${report.avgConfidence.toFixed(2)}.`
                  : `Showing ${visible.length} of ${report.total}.`}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                {filterChips.map((chip) => (
                  <button
                    key={chip.label}
                    type="button"
                    disabled={chip.count === 0 && chip.key !== null}
                    aria-pressed={filter === chip.key}
                    onClick={() => setFilter(chip.key)}
                    className={cn(
                      "rounded-full border px-3 py-1 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-40",
                      filter === chip.key ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                    )}
                  >
                    {chip.label} <span className="tabular-nums opacity-80">{chip.count}</span>
                  </button>
                ))}
                {visible.length > 0 && (
                  <button
                    type="button"
                    onClick={toggleAll}
                    className="ml-auto text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                  >
                    {allOpen ? "Collapse all" : "Expand all"}
                  </button>
                )}
              </div>

              {loading ? (
                <div className="space-y-2">
                  {[0, 1, 2].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
                </div>
              ) : visible.length === 0 ? (
                <div className="rounded-md border border-dashed px-4 py-8 text-center text-sm text-muted-foreground">
                  {report.total === 0 ? "No gaps were found in this document." : "No findings match this filter."}
                </div>
              ) : (
                <div className="space-y-2">
                  {visible.map((f) => (
                    <FindingCard key={f.id} finding={f} open={openIds.has(f.id)} onToggle={() => toggleOpen(f.id)} />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Recommendations */}
        <Card>
          <CardHeader>
            <CardTitle>Recommendations</CardTitle>
            <CardDescription>Actions combined across findings, most urgent first.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {priorityGroups.length === 0 ? (
              <p className="text-sm text-muted-foreground">No recommendations: nothing needs to be fixed.</p>
            ) : (
              priorityGroups.map(({ severity, items }) => (
                <section key={severity} className="space-y-2">
                  <div className="flex items-center gap-2">
                    <SeverityPill severity={severity} />
                    <span className="text-xs text-muted-foreground">{SEVERITY_META[severity].priority}</span>
                  </div>
                  <ol className="list-decimal space-y-2 pl-5 text-sm leading-relaxed marker:font-semibold">
                    {items.map((r, i) => (
                      <li key={i}>
                        {r.text}
                        <span className="ml-2 text-xs text-muted-foreground">({r.findingIds.join(", ")})</span>
                      </li>
                    ))}
                  </ol>
                </section>
              ))
            )}
          </CardContent>
        </Card>

        <p className="pb-4 text-center text-[11px] text-muted-foreground">
          Score = 100 minus 12 per major, 4 per minor and 1 per observation (minimum 0). Cheshire can make mistakes. Verify important security findings.
        </p>
      </div>
    </div>
  )
}