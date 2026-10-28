import { pdf } from "@react-pdf/renderer"
import { ReportDocument } from "@/components/report/ReportPdf"
import { reportFileName, type ReportData, type TrendPoint } from "@/lib/report"

/**
 * Renders the report to PDF and downloads it as DocumentName_Assessment_Date.pdf.
 * Returns the file name. Imported dynamically so the renderer stays out of the main bundle.
 */
export async function exportReportPdf(report: ReportData, trend: TrendPoint[]): Promise<string> {
  const blob = await pdf(<ReportDocument report={report} trend={trend} />).toBlob()
  const fileName = reportFileName(report.documentName, report.generatedAt)

  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  setTimeout(() => URL.revokeObjectURL(url), 10_000)

  return fileName
}