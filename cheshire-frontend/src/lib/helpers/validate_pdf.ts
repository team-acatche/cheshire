import { pdfjs } from "react-pdf"

const MAX_SIZE_BYTES = 100 * 1024 * 1024 // 100 MB
const PDF_MAGIC = [0x25, 0x50, 0x44, 0x46, 0x2d] // "%PDF-"

export type PdfValidation = { ok: true } | { ok: false; error: string }

export async function validatePdf(file: File): Promise<PdfValidation> {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
        return { ok: false, error: "Invalid file type. Only PDF files are supported." }
    }

    if (file.size === 0) {
        return { ok: false, error: "This file is empty." }
    }

    if (file.size > MAX_SIZE_BYTES) {
        return {
            ok: false,
            error: `This file is too large. The maximum allowed size is ${MAX_SIZE_BYTES / (1024 * 1024)} MB.`,
        }
    }

    // The PDF spec allows the header anywhere in the first 1024 bytes
    const head = new Uint8Array(await file.slice(0, 1024).arrayBuffer())
    const hasMagic = head.some((_, i) =>
        PDF_MAGIC.every((byte, j) => head[i + j] === byte)
    )

    if (!hasMagic) {
        return {
            ok: false,
            error: "This file isn't a valid PDF.",
        }
    }

    try {
        const task = pdfjs.getDocument({ data: await file.arrayBuffer() })
        await task.promise
        await task.destroy()
    } catch (err) {
        if ((err as { name?: string })?.name === "PasswordException") {
            return {
                ok: false,
                error: "This PDF is password-protected. Remove the password and upload it again.",
            }
        }
    }

    return { ok: true }
}