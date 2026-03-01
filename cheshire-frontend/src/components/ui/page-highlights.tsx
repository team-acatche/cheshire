import { degrees, grayscale, PDFDocument, rgb } from 'pdf-lib';

export async function drawHighlight(pdf: File): Promise<PDFDocument> {
    // 1. check if file is pdf
    if (pdf.type !== "application/pdf") {
        throw new Error("File must be a PDF");
    }
    // 2. load it as a PDFDocument
    const bytes = await pdf.arrayBuffer();
    const pdfDoc = await PDFDocument.load(bytes);
    // 3. iterate through every page and draw a rectangle
    const pages = pdfDoc.getPages();

    pages.forEach((page) => {
        page.drawRectangle({
            x: 105,
            y: 475,
            width: 550,
            height: 105,
            borderWidth: 5,
            color: rgb(0.75, 0.2, 0.2),
        });
    });
    // 4. return the modified document
    return pdfDoc;
}