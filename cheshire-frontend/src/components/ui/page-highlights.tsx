import { degrees, grayscale, PDFDocument, rgb } from 'pdf-lib';

export async function drawHighlight(pdf: File): Promise<PDFDocument> {
    // 1. check if file is pdf
    
    // 2. load it as a PDFDocument
    const bytes = await pdf.arrayBuffer();
    const pdfDoc = await PDFDocument.load(bytes);
    // 3. iterate through every page and draw a rectangle
    const pages = pdfDoc.getPages();

    pages.forEach((page) => {
        page.drawRectangle({
            x: 25,
            y: 75,
            width: 250,
            height: 75,
            rotate: degrees(-15),
            borderWidth: 5,
            borderColor: grayscale(0.5),
            color: rgb(0.75, 0.2, 0.2),
            opacity: 0.5,
            borderOpacity: 0.75,
        });
    });
    // 4. return the modified document
    return pdfDoc;
}