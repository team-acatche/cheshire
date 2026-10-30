import { Circle, Document, Page, Path, Polyline, StyleSheet, Svg, Text, View, Line } from "@react-pdf/renderer"
import {
  SEVERITIES,
  SEVERITY_META,
  STATUS_META,
  arcPath,
  formatReportDate,
  formatShortDate,
  summaryText,
  trendGeometry,
  type ReportData,
  type TrendPoint,
} from "@/lib/report"

const INK = "#18181b"
const MUTED = "#71717a"
const LINE = "#e4e4e7"
const PRIMARY = "#1a47d0"
const MAX_UNSPLIT_CHARS = 2200

const s = StyleSheet.create({
  page: { paddingTop: 40, paddingBottom: 60, paddingHorizontal: 40, fontSize: 10, fontFamily: "Helvetica", color: INK, lineHeight: 1.4 },
  brand: { fontSize: 9, fontFamily: "Helvetica-Bold", letterSpacing: 2, color: PRIMARY, marginBottom: 6 },
  title: { fontSize: 22, fontFamily: "Helvetica-Bold", lineHeight: 1.2, marginBottom: 8 },
  docName: { fontSize: 12, color: MUTED, marginBottom: 16 },
  metaGrid: { flexDirection: "row", flexWrap: "wrap", borderTopWidth: 1, borderBottomWidth: 1, borderColor: LINE, paddingVertical: 8, marginBottom: 18 },
  metaItem: { width: "50%", paddingVertical: 3, paddingRight: 8 },
  metaLabel: { fontSize: 7.5, fontFamily: "Helvetica-Bold", color: MUTED, letterSpacing: 0.8 },
  metaValue: { fontSize: 10 },
  h2: { fontSize: 14, fontFamily: "Helvetica-Bold", marginTop: 6, marginBottom: 8 },
  label: { fontSize: 7.5, fontFamily: "Helvetica-Bold", color: MUTED, letterSpacing: 0.8, marginTop: 10, marginBottom: 3 },
  body: { fontSize: 10 },
  muted: { fontSize: 9, color: MUTED },
  row: { flexDirection: "row", alignItems: "center" },
  statusPill: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2, alignSelf: "flex-start", marginBottom: 6 },
  statusText: { fontSize: 11, fontFamily: "Helvetica-Bold" },
  tiles: { flexDirection: "row", marginTop: 10 },
  tile: { flex: 1, borderWidth: 1, borderColor: LINE, borderRadius: 4, padding: 6, marginRight: 6 },
  tileValue: { fontSize: 16, fontFamily: "Helvetica-Bold" },
  card: { borderWidth: 1, borderColor: LINE, borderRadius: 4, padding: 10, marginBottom: 14 },
  barRow: { flexDirection: "row", alignItems: "center", marginBottom: 6 },
  barLabel: { width: 78, fontSize: 9 },
  barTrack: { flex: 1, height: 8, backgroundColor: "#f4f4f5", borderRadius: 4 },
  barFill: { height: 8, borderRadius: 4 },
  barCount: { width: 52, textAlign: "right", fontSize: 9 },
  pill: { borderRadius: 8, paddingHorizontal: 6, paddingVertical: 1.5, marginRight: 6 },
  pillText: { fontSize: 7.5, fontFamily: "Helvetica-Bold", color: "#ffffff", letterSpacing: 0.5, lineHeight: 1 },
  pillOutline: { borderWidth: 1, borderColor: MUTED, borderRadius: 8, paddingHorizontal: 6, paddingVertical: 1, marginRight: 6 },
  pillOutlineText: { fontSize: 7.5, fontFamily: "Helvetica-Bold", color: MUTED },
  finding: { borderWidth: 1, borderColor: LINE, borderLeftWidth: 4, borderRadius: 4, padding: 12, marginBottom: 10 },
  findingTitle: { fontSize: 11, fontFamily: "Helvetica-Bold", lineHeight: 1.3, marginTop: 5, marginBottom: 3 },
  findingId: { fontSize: 8, color: MUTED, marginLeft: "auto" },
  listItem: { flexDirection: "row", marginBottom: 4 },
  listNum: { width: 16, fontFamily: "Helvetica-Bold" },
  listText: { flex: 1 },
  link: { fontSize: 8.5, color: PRIMARY },
  footer: { position: "absolute", left: 40, right: 40, bottom: 24, flexDirection: "row", justifyContent: "space-between", fontSize: 8, color: MUTED, borderTopWidth: 1, borderColor: LINE, paddingTop: 6 },
})

function Pill({ color, label }: { color: string; label: string }) {
  return (
    <View style={[s.pill, { backgroundColor: color }]}>
      <Text style={s.pillText}>{label.toUpperCase()}</Text>
    </View>
  )
}

function Gauge({ score, color }: { score: number; color: string }) {
  return (
    <View style={{ width: 96, height: 96, marginRight: 18 }}>
      <Svg width={96} height={96} viewBox="0 0 96 96">
        <Circle cx={48} cy={48} r={40} stroke={LINE} strokeWidth={9} fill="none" />
        {score > 0 && <Path d={arcPath(48, 48, 40, score / 100)} stroke={color} strokeWidth={9} fill="none" strokeLinecap="round" />}
      </Svg>
      <View
        style={{
          position: "absolute", top: 0, left: 0, width: 96, height: 96,
          flexDirection: "column", alignItems: "center", justifyContent: "center",
        }}
      >
        <Text style={{ fontSize: 24, fontFamily: "Helvetica-Bold", color, lineHeight: 1 }}>{score}</Text>
        <Text style={{ fontSize: 7, color: MUTED, lineHeight: 1, marginTop: 5 }}>OUT OF 100</Text>
      </View>
    </View>
  )
}

function TrendSvg({ points, currentSessionId }: { points: TrendPoint[]; currentSessionId: string }) {
  const W = 480
  const H = 130
  const coords = trendGeometry(points, W, H, { l: 24, r: 10, t: 8, b: 18 })
  const gridY = (g: number) => 8 + (H - 8 - 18) * (1 - g / 100)
  const showAll = points.length <= 8
  return (
    <Svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
      {[0, 50, 100].map((g) => (
        <Line key={g} x1={24} x2={W - 10} y1={gridY(g)} y2={gridY(g)} stroke={LINE} strokeWidth={0.8} />
      ))}
      <Polyline points={coords.map((c) => `${c.x},${c.y}`).join(" ")} stroke={PRIMARY} strokeWidth={2} fill="none" />
      {coords.map((c) => (
        <Circle
          key={c.point.session_id}
          cx={c.x}
          cy={c.y}
          r={c.point.session_id === currentSessionId ? 4.5 : 3}
          fill={c.point.session_id === currentSessionId ? PRIMARY : "#ffffff"}
          stroke={PRIMARY}
          strokeWidth={1.5}
        />
      ))}
      {coords.map((c, i) =>
        showAll || i === 0 || i === coords.length - 1 ? (
          <Text key={`t-${c.point.session_id}`} x={c.x - 14} y={H - 4} fill={MUTED} style={{ fontSize: 7 }}>
            {formatShortDate(c.point.assessed_at)}
          </Text>
        ) : null
      )}
    </Svg>
  )
}

export function ReportDocument({ report, trend }: { report: ReportData; trend: TrendPoint[] }) {
  const status = STATUS_META[report.status]
  const meta: [string, string][] = [
    ["ASSESSED", formatReportDate(report.assessedAt)],
    ["REPORT GENERATED", formatReportDate(report.generatedAt)],
    ["GENERATED BY", `${report.userName} (${report.userEmail})`],
    ["SESSION ID", report.sessionId],
  ]
  const priorityGroups = SEVERITIES.map((sev) => ({
    severity: sev,
    items: report.recommendations.filter((r) => r.severity === sev),
  })).filter((g) => g.items.length > 0)

  return (
    <Document
      title={`${report.documentName} - Compliance Assessment Report`}
      author={report.userName}
      creator="Cheshire"
      producer="Cheshire"
    >
      <Page size="A4" style={s.page}>
        <Text style={s.brand}>CHESHIRE</Text>
        <Text style={s.title}>Compliance Assessment Report</Text>
        <Text style={s.docName}>{report.documentName}</Text>

        <View style={s.metaGrid}>
          {meta.map(([label, value]) => (
            <View key={label} style={s.metaItem}>
              <Text style={s.metaLabel}>{label}</Text>
              <Text style={s.metaValue}>{value}</Text>
            </View>
          ))}
        </View>

        {/* Executive summary */}
        <Text style={s.h2}>Executive summary</Text>
        <View style={[s.card, s.row, { alignItems: "flex-start" }]} wrap={false}>
          <Gauge score={report.score} color={status.hex} />
          <View style={{ flex: 1 }}>
            <View style={[s.statusPill, { borderColor: status.hex }]}>
              <Text style={[s.statusText, { color: status.hex }]}>{status.label}</Text>
            </View>
            <Text style={s.body}>{summaryText(report)}</Text>
            <View style={s.tiles}>
              <View style={s.tile}>
                <Text style={s.tileValue}>{report.total}</Text>
                <Text style={s.muted}>Total gaps</Text>
              </View>
              {SEVERITIES.map((sev) => (
                <View key={sev} style={s.tile}>
                  <Text style={[s.tileValue, { color: SEVERITY_META[sev].hex }]}>{report.counts[sev]}</Text>
                  <Text style={s.muted}>{SEVERITY_META[sev].label}</Text>
                </View>
              ))}
            </View>
          </View>
        </View>

        {/* Dashboard */}
        <Text style={s.h2}>Compliance dashboard</Text>
        <View style={s.card} wrap={false}>
          <Text style={[s.label, { marginTop: 0, marginBottom: 6 }]}>GAPS BY SEVERITY</Text>
          {SEVERITIES.map((sev) => {
            const n = report.counts[sev]
            const pct = report.total ? Math.round((n / report.total) * 100) : 0
            return (
              <View key={sev} style={s.barRow}>
                <Text style={s.barLabel}>{SEVERITY_META[sev].label}</Text>
                <View style={s.barTrack}>
                  <View style={[s.barFill, { width: `${pct}%`, backgroundColor: SEVERITY_META[sev].hex }]} />
                </View>
                <Text style={s.barCount}>{n} ({pct}%)</Text>
              </View>
            )
          })}
          {report.missingCount > 0 && (
            <Text style={s.muted}>
              {report.missingCount} {report.missingCount === 1 ? "gap is" : "gaps are"} missing required content.
            </Text>
          )}
        </View>

        <View style={s.card} wrap={false}>
          <Text style={[s.label, { marginTop: 0, marginBottom: 6 }]}>COMPLIANCE TREND ACROSS ASSESSMENTS</Text>
          {trend.length >= 2 ? (
            <TrendSvg points={trend} currentSessionId={report.sessionId} />
          ) : (
            <Text style={s.muted}>Not enough completed assessments to show a trend yet.</Text>
          )}
        </View>

        {/* Detailed findings */}
        <Text style={s.h2} break>Detailed findings</Text>
        {report.findings.length === 0 && <Text style={s.body}>No gaps were found in this document.</Text>}
        {report.findings.map((f) => {

          const size = 
            f.description.length +
            f.recommendations.join(" ").length +
            f.references.join(" ").length

            return (
            <View 
              key={f.id}
              wrap={size > MAX_UNSPLIT_CHARS}
              style={[s.finding, { borderLeftColor: SEVERITY_META[f.severity].hex }]}>
              <View style={s.row}>
                <Pill color={SEVERITY_META[f.severity].hex} label={SEVERITY_META[f.severity].label} />
                {f.missing && (
                  <View style={s.pillOutline}>
                    <Text style={s.pillOutlineText}>MISSING CONTENT</Text>
                  </View>
                )}
                <Text style={s.findingId}>{f.id}</Text>
              </View>
              <Text style={s.findingTitle}>{f.title}</Text>
              <Text style={s.muted}>{f.location} | Confidence {f.confidenceLabel}</Text>

              <Text style={s.label}>EVIDENCE</Text>
              <Text style={s.body}>{f.description}</Text>

              {f.recommendations.length > 0 && (
                <View>
                  <Text style={s.label}>RECOMMENDATIONS</Text>
                  {f.recommendations.map((r, i) => (
                    <View key={i} style={s.listItem}>
                      <Text style={s.listNum}>{i + 1}.</Text>
                      <Text style={s.listText}>{r}</Text>
                    </View>
                  ))}
                </View>
              )}

              {f.references.length > 0 && (
                <View>
                  <Text style={s.label}>REFERENCES</Text>
                  {f.references.map((url, i) => (
                    <Text key={i} style={s.link}>{url}</Text>
                  ))}
                </View>
              )}
            </View>
          )
        })}

        {/* Recommendations */}
        <Text style={s.h2} break>Recommendations</Text>
        {priorityGroups.length === 0 && <Text style={s.body}>Nothing needs to be fixed.</Text>}
        {priorityGroups.map(({ severity, items }) => (
          <View key={severity} style={{ marginBottom: 10 }}>
            <View style={s.row} minPresenceAhead={40}>
              <Pill color={SEVERITY_META[severity].hex} label={SEVERITY_META[severity].label} />
              <Text style={s.muted}>{SEVERITY_META[severity].priority}</Text>
            </View>
            <View style={{ marginTop: 6 }}>
              {items.map((r, i) => (
                <View key={i} style={s.listItem} wrap={false}>
                  <Text style={s.listNum}>{i + 1}.</Text>
                  <Text style={s.listText}>
                    {r.text} <Text style={s.muted}>({r.findingIds.join(", ")})</Text>
                  </Text>
                </View>
              ))}
            </View>
          </View>
        ))}

        <Text style={[s.muted, { marginTop: 8 }]}>
          Score = 100 minus 12 per major, 4 per minor and 1 per observation (minimum 0). Cheshire can make mistakes. Verify important security findings.
        </Text>

        <View style={s.footer} fixed>
          <Text>Cheshire | {report.documentName}</Text>
          <Text render={({ pageNumber, totalPages }) => `Page ${pageNumber} of ${totalPages}`} />
        </View>
      </Page>
    </Document>
  )
}