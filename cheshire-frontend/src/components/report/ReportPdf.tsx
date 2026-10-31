import { Circle, Document, Line, Page, Polyline, StyleSheet, Svg, Text, View } from "@react-pdf/renderer"
import {
  SEVERITIES,
  SEVERITY_META,
  STATUS_META,
  formatReportDate,
  formatShortDate,
  pdfSafe as t,
  summaryText,
  trendGeometry,
  type ReportData,
  type TrendPoint,
} from "@/lib/report"

// Debug switch: add "trend" | "glance" | "findings" | "recs" to skip a section while bisecting.
const SKIP = new Set<string>(["findings"])
// A4 is 595pt wide; page padding is 40 each side. Every width below is a fixed number
// (no %, no flex:1) so yoga never has an undefined size to resolve.
const CW = 515
const CARD_PAD = 12
const INNER = CW - CARD_PAD * 2 // 491

const INK = "#18181b"
const MUTED = "#71717a"
const LINE = "#e4e4e7"
const SOFT = "#f4f4f5"
const PRIMARY = "#1a47d0"

const SCORE_W = 104
const RIGHT_W = INNER - SCORE_W - 16 // 371
const TILE_W = Math.floor((RIGHT_W - 18) / 4) // 88
const BAR_LABEL = 78
const BAR_COUNT = 56
const BAR_TRACK = INNER - BAR_LABEL - BAR_COUNT // 357

const COL_ID = 36
const COL_SEV = 70
const COL_LOC = 78
const COL_TITLE = CW - COL_ID - COL_SEV - COL_LOC // 331

const s = StyleSheet.create({
  page: { paddingTop: 40, paddingBottom: 60, paddingHorizontal: 40, fontSize: 10, fontFamily: "Helvetica", color: INK, lineHeight: 1.4 },
  brand: { fontSize: 9, fontFamily: "Helvetica-Bold", color: PRIMARY, marginBottom: 6 },
  title: { fontSize: 22, fontFamily: "Helvetica-Bold", lineHeight: 1.2, marginBottom: 6, width: CW },
  docName: { fontSize: 12, color: MUTED, marginBottom: 14, width: CW },
  metaGrid: { width: CW, flexDirection: "row", flexWrap: "wrap", backgroundColor: SOFT, padding: 10, marginBottom: 18 },
  metaItem: { width: (CW - 20) / 2, paddingVertical: 3, paddingRight: 8 },
  metaLabel: { fontSize: 7.5, fontFamily: "Helvetica-Bold", color: MUTED },
  metaValue: { fontSize: 10 },
  h2: { fontSize: 14, fontFamily: "Helvetica-Bold", marginTop: 6, marginBottom: 8, width: CW },
  label: { fontSize: 7.5, fontFamily: "Helvetica-Bold", color: MUTED, marginTop: 10, marginBottom: 3 },
  body: { fontSize: 10 },
  muted: { fontSize: 9, color: MUTED },
  row: { flexDirection: "row", alignItems: "center" },
  card: { width: CW, backgroundColor: SOFT, padding: CARD_PAD, marginBottom: 14 },
  divider: { width: CW, height: 1, backgroundColor: LINE },

  // summary
  summaryRow: { flexDirection: "row", alignItems: "flex-start" },
  scoreCol: { width: SCORE_W, marginRight: 16 },
  scoreNum: { fontSize: 38, fontFamily: "Helvetica-Bold", lineHeight: 1.1 },
  scoreSub: { fontSize: 7.5, color: MUTED, marginBottom: 6 },
  scoreTrack: { width: SCORE_W, height: 6, backgroundColor: LINE },
  rightCol: { width: RIGHT_W },
  statusPill: { paddingHorizontal: 8, paddingVertical: 3, alignSelf: "flex-start", marginBottom: 6 },
  statusText: { fontSize: 11, fontFamily: "Helvetica-Bold", color: "#ffffff" },
  tiles: { flexDirection: "row", marginTop: 10 },
  tile: { width: TILE_W, backgroundColor: "#ffffff", padding: 6 },
  tileValue: { fontSize: 16, fontFamily: "Helvetica-Bold" },

  // severity bars
  barRow: { flexDirection: "row", alignItems: "center", marginBottom: 6 },
  barLabel: { width: BAR_LABEL, fontSize: 9 },
  barTrack: { width: BAR_TRACK, height: 8, backgroundColor: LINE },
  barCount: { width: BAR_COUNT, textAlign: "right", fontSize: 9 },

  // pills
  pill: { paddingHorizontal: 6, paddingVertical: 2, marginRight: 6 },
  pillText: { fontSize: 7.5, fontFamily: "Helvetica-Bold", color: "#ffffff" },
  pillMuted: { backgroundColor: LINE, paddingHorizontal: 6, paddingVertical: 2, marginRight: 6 },
  pillMutedText: { fontSize: 7.5, fontFamily: "Helvetica-Bold", color: MUTED },

  // glance table
  thRow: { width: CW, flexDirection: "row", paddingBottom: 3 },
  th: { fontSize: 7.5, fontFamily: "Helvetica-Bold", color: MUTED },
  tr: { width: CW, flexDirection: "row", paddingVertical: 4 },
  colId: { width: COL_ID },
  colSev: { width: COL_SEV },
  colTitle: { width: COL_TITLE, paddingRight: 8 },
  colLoc: { width: COL_LOC, textAlign: "right" },

  // findings
  finding: { width: CW, backgroundColor: SOFT, marginBottom: 10 },
  findingBar: { width: CW, height: 4 },
  findingBody: { width: CW, padding: CARD_PAD },
  findingHead: { width: INNER, flexDirection: "row", alignItems: "center" },
  headLeft: { width: INNER - 91, flexDirection: "row", alignItems: "center" },
  headId: { width: 91, textAlign: "right" },
  findingTitle: { width: INNER, fontSize: 11, fontFamily: "Helvetica-Bold", lineHeight: 1.3, marginTop: 5, marginBottom: 3 },
  textInner: { width: INNER },
  listItem: { width: INNER, flexDirection: "row", marginBottom: 4 },
  listNum: { width: 16, fontFamily: "Helvetica-Bold" },
  listTextInner: { width: INNER - 16 },
  listItemOuter: { width: CW, flexDirection: "row", marginBottom: 4 },
  listTextOuter: { width: CW - 16 },
  link: { width: INNER, fontSize: 8.5, color: PRIMARY, marginBottom: 2 },

  footer: { position: "absolute", left: 40, bottom: 24, width: CW },
  footerRow: { width: CW, flexDirection: "row", paddingTop: 6 },
  footerLeft: { width: CW - 115, fontSize: 8, color: MUTED },
  footerRight: { width: 115, fontSize: 8, color: MUTED, textAlign: "right" },
})

function Pill({ color, label }: { color: string; label: string }) {
  return (
    <View style={[s.pill, { backgroundColor: color }]}>
      <Text style={s.pillText}>{label.toUpperCase()}</Text>
    </View>
  )
}

function Footer({ docName }: { docName: string }) {
  return (
    <View style={s.footer} fixed>
      <View style={s.divider} />
      <View style={s.footerRow}>
        <Text style={s.footerLeft}>Cheshire | {docName}</Text>
        <Text style={s.footerRight} render={({ pageNumber, totalPages }) => `Page ${pageNumber} of ${totalPages}`} />
      </View>
    </View>
  )
}

function TrendSvg({ points, currentSessionId }: { points: TrendPoint[]; currentSessionId: string }) {
  const W = 480
  const H = 110
  const pad = { l: 24, r: 10, t: 8, b: 8 }
  const coords = trendGeometry(points, W, H, pad)
  const gridY = (g: number) => pad.t + (H - pad.t - pad.b) * (1 - g / 100)
  return (
    <Svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
      {[0, 50, 100].map((g) => (
        <Line key={g} x1={pad.l} x2={W - pad.r} y1={gridY(g)} y2={gridY(g)} stroke={LINE} strokeWidth={0.8} />
      ))}
      <Polyline points={coords.map((c) => `${c.x},${c.y}`).join(" ")} stroke={PRIMARY} strokeWidth={2} fill="none" />
      {coords.map((c) => {
        const current = c.point.session_id === currentSessionId
        return (
          <Circle
            key={c.point.session_id}
            cx={c.x}
            cy={c.y}
            r={current ? 4.5 : 3}
            fill={current ? PRIMARY : "#ffffff"}
            stroke={PRIMARY}
            strokeWidth={1.5}
          />
        )
      })}
    </Svg>
  )
}

export function ReportDocument({ report, trend }: { report: ReportData; trend: TrendPoint[] }) {
  const status = STATUS_META[report.status]
  const docName = t(report.documentName) || "Document"
  const meta: [string, string][] = [
    ["ASSESSED", formatReportDate(report.assessedAt)],
    ["REPORT GENERATED", formatReportDate(report.generatedAt)],
    ["GENERATED BY", t(`${report.userName} (${report.userEmail})`)],
    ["SESSION ID", t(report.sessionId)],
  ]
  const priorityGroups = SEVERITIES.map((sev) => ({
    severity: sev,
    items: report.recommendations.filter((r) => r.severity === sev),
  })).filter((g) => g.items.length > 0)

  const score = Math.max(0, Math.min(100, Math.round(report.score)))
  const showTrend = !SKIP.has("trend") && trend.length >= 2

  return (
    <Document
      title={`${docName} - Compliance Assessment Report`}
      author={t(report.userName)}
      creator="Cheshire"
      producer="Cheshire"
    >
      {/* Page 1: summary + dashboard */}
      <Page size="A4" style={s.page}>
        <Text style={s.brand}>CHESHIRE</Text>
        <Text style={s.title}>Compliance Assessment Report</Text>
        <Text style={s.docName}>{docName}</Text>

        <View style={s.metaGrid}>
          {meta.map(([label, value]) => (
            <View key={label} style={s.metaItem}>
              <Text style={s.metaLabel}>{label}</Text>
              <Text style={s.metaValue}>{value}</Text>
            </View>
          ))}
        </View>

        <Text style={s.h2}>Executive summary</Text>
        <View style={s.card}>
          <View style={s.summaryRow}>
            <View style={s.scoreCol}>
              <Text style={[s.scoreNum, { color: status.hex }]}>{score}</Text>
              <Text style={s.scoreSub}>OUT OF 100</Text>
              <View style={s.scoreTrack}>
                <View style={{ width: Math.round((SCORE_W * score) / 100), height: 6, backgroundColor: status.hex }} />
              </View>
            </View>
            <View style={s.rightCol}>
              <View style={[s.statusPill, { backgroundColor: status.hex }]}>
                <Text style={s.statusText}>{status.label}</Text>
              </View>
              <Text style={[s.body, { width: RIGHT_W }]}>{t(summaryText(report))}</Text>
              <View style={s.tiles}>
                <View style={[s.tile, { marginRight: 6 }]}>
                  <Text style={s.tileValue}>{report.total}</Text>
                  <Text style={s.muted}>Total gaps</Text>
                </View>
                {SEVERITIES.map((sev, i) => (
                  <View key={sev} style={[s.tile, i < SEVERITIES.length - 1 ? { marginRight: 6 } : {}]}>
                    <Text style={[s.tileValue, { color: SEVERITY_META[sev].hex }]}>{report.counts[sev]}</Text>
                    <Text style={s.muted}>{SEVERITY_META[sev].label}</Text>
                  </View>
                ))}
              </View>
            </View>
          </View>
        </View>

        <Text style={s.h2}>Compliance dashboard</Text>
        <View style={s.card}>
          <Text style={[s.label, { marginTop: 0, marginBottom: 6 }]}>GAPS BY SEVERITY</Text>
          {SEVERITIES.map((sev) => {
            const n = report.counts[sev]
            const pct = report.total ? Math.round((n / report.total) * 100) : 0
            return (
              <View key={sev} style={s.barRow}>
                <Text style={s.barLabel}>{SEVERITY_META[sev].label}</Text>
                <View style={s.barTrack}>
                  <View style={{ width: Math.round((BAR_TRACK * pct) / 100), height: 8, backgroundColor: SEVERITY_META[sev].hex }} />
                </View>
                <Text style={s.barCount}>{n} ({pct}%)</Text>
              </View>
            )
          })}
          {report.missingCount > 0 && (
            <Text style={[s.muted, { width: INNER }]}>
              {report.missingCount} {report.missingCount === 1 ? "gap is" : "gaps are"} missing required content.
            </Text>
          )}
        </View>

        {showTrend && (
          <View style={s.card}>
            <Text style={[s.label, { marginTop: 0, marginBottom: 6 }]}>COMPLIANCE TREND ACROSS ASSESSMENTS</Text>
            <TrendSvg points={trend} currentSessionId={report.sessionId} />
            <View style={{ width: 480, flexDirection: "row", paddingLeft: 24 }}>
              <Text style={{ width: 223, fontSize: 9, color: MUTED }}>{formatShortDate(trend[0]?.assessed_at)}</Text>
              <Text style={{ width: 223, fontSize: 9, color: MUTED, textAlign: "right" }}>
                {formatShortDate(trend[trend.length - 1]?.assessed_at)}
              </Text>
            </View>
          </View>
        )}

        <Footer docName={docName} />
      </Page>

      {/* Page 2+: findings at a glance */}
      {!SKIP.has("glance") && (
        <Page size="A4" style={s.page}>
          <Text style={s.h2}>Findings at a glance</Text>
          {report.findings.length === 0 ? (
            <Text style={s.body}>No gaps were found in this document.</Text>
          ) : (
            <View>
              <View style={s.thRow}>
                <Text style={[s.th, s.colId]}>ID</Text>
                <Text style={[s.th, s.colSev]}>SEVERITY</Text>
                <Text style={[s.th, s.colTitle]}>FINDING</Text>
                <Text style={[s.th, s.colLoc]}>LOCATION</Text>
              </View>
              <View style={[s.divider, { backgroundColor: INK }]} />
              {report.findings.map((f) => (
                <View key={f.id}>
                  <View style={s.tr}>
                    <Text style={[s.body, s.colId, { color: MUTED }]}>{f.id}</Text>
                    <Text style={[s.body, s.colSev, { color: SEVERITY_META[f.severity].hex, fontFamily: "Helvetica-Bold" }]}>
                      {SEVERITY_META[f.severity].label}
                    </Text>
                    <Text style={[s.body, s.colTitle]}>{t(f.title)}</Text>
                    <Text style={[s.muted, s.colLoc]}>{t(f.location)}</Text>
                  </View>
                  <View style={s.divider} />
                </View>
              ))}
            </View>
          )}
          <Footer docName={docName} />
        </Page>
      )}

      {/* Detailed findings */}
      {!SKIP.has("findings") && (
        <Page size="A4" style={s.page}>
          <Text style={s.h2}>Detailed findings</Text>
          {report.findings.length === 0 && <Text style={s.body}>No gaps were found in this document.</Text>}
          {report.findings.map((f) => (
            <View key={f.id} style={s.finding}>
              <View style={[s.findingBar, { backgroundColor: SEVERITY_META[f.severity].hex }]} />
              <View style={s.findingBody}>
                <View style={s.findingHead}>
                  <View style={s.headLeft}>
                    <Pill color={SEVERITY_META[f.severity].hex} label={SEVERITY_META[f.severity].label} />
                    {f.missing && (
                      <View style={s.pillMuted}>
                        <Text style={s.pillMutedText}>MISSING CONTENT</Text>
                      </View>
                    )}
                  </View>
                  <Text style={[s.muted, s.headId]}>{f.id}</Text>
                </View>

                <Text style={s.findingTitle}>{t(f.title)}</Text>
                <Text style={[s.muted, s.textInner]}>{t(f.location)} | Confidence {t(f.confidenceLabel)}</Text>

                <Text style={[s.label, s.textInner]}>EVIDENCE</Text>
                <Text style={[s.body, s.textInner]}>{t(f.description)}</Text>

                {f.recommendations.length > 0 && (
                  <View>
                    <Text style={[s.label, s.textInner]}>RECOMMENDATIONS</Text>
                    {f.recommendations.map((r, i) => (
                      <View key={i} style={s.listItem}>
                        <Text style={s.listNum}>{i + 1}.</Text>
                        <Text style={s.listTextInner}>{t(r)}</Text>
                      </View>
                    ))}
                  </View>
                )}

                {f.references.length > 0 && (
                  <View>
                    <Text style={[s.label, s.textInner]}>REFERENCES</Text>
                    {f.references.map((url, i) => (
                      <Text key={i} style={s.link}>{t(url)}</Text>
                    ))}
                  </View>
                )}
              </View>
            </View>
          ))}
          <Footer docName={docName} />
        </Page>
      )}

      {/* Recommendations */}
      {!SKIP.has("recs") && (
        <Page size="A4" style={s.page}>
          <Text style={s.h2}>Recommendations</Text>
          {priorityGroups.length === 0 && <Text style={s.body}>Nothing needs to be fixed.</Text>}
          {priorityGroups.map(({ severity, items }) => (
            <View key={severity} style={{ width: CW, marginBottom: 10 }}>
              <View style={s.row}>
                <Pill color={SEVERITY_META[severity].hex} label={SEVERITY_META[severity].label} />
                <Text style={s.muted}>{SEVERITY_META[severity].priority}</Text>
              </View>
              <View style={{ marginTop: 6 }}>
                {items.map((r, i) => (
                  <View key={i} style={s.listItemOuter}>
                    <Text style={s.listNum}>{i + 1}.</Text>
                    <Text style={s.listTextOuter}>
                      {t(r.text)} ({r.findingIds.join(", ")})
                    </Text>
                  </View>
                ))}
              </View>
            </View>
          ))}

          <Text style={[s.muted, { marginTop: 8, width: CW }]}>
            Score = 100 minus 12 per major, 4 per minor and 1 per observation (minimum 0). Cheshire can make mistakes. Verify important security findings.
          </Text>
          <Footer docName={docName} />
        </Page>
      )}
    </Document>
  )
}