import type { VulnerabilityFinding } from '@/types/VulnerabilityFinding';
import { PDFDocument, rgb } from 'pdf-lib';

export async function drawHighlight(pdf: File, findings: VulnerabilityFinding[]): Promise<PDFDocument> {
    // 1. check if file is pdf
    if (pdf.type !== "application/pdf") {
        throw new Error("File must be a PDF");
    }
    // 2. load it as a PDFDocument
    const bytes = await pdf.arrayBuffer();
    const pdfDoc = await PDFDocument.load(bytes);
    // 3. iterate through every page and draw a rectangle
    const pages = pdfDoc.getPages();

    findings.forEach((finding) => {
        let page = pages.at(finding.page_no - 1);
        if (!page) return;
        page.drawRectangle({
            x: finding.bbox.l,
            y: finding.bbox.b,
            width: Math.abs(finding.bbox.r - finding.bbox.l),
            height: Math.abs(finding.bbox.t - finding.bbox.b),
            borderWidth: 1,
            color: rgb(212 / 256, 110 / 256, 110 / 256),
            opacity: 0.25,
        });
    });
    // 4. return the modified document
    return pdfDoc;
}
