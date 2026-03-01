import { Button } from "@/components/ui/button";
import { FileText } from "lucide-react";
// 1. Import the function
import { drawHighlight } from "@/components/ui/page-highlights";
import { NamedFile } from "@/types/NamedFile";


interface DocumentPreviewProps {
  src: NamedFile,
  setFile: React.Dispatch<React.SetStateAction<NamedFile | null>>
}

export function DocumentPreview({ src, setFile }: DocumentPreviewProps) {
  return (
    <>
      <div className="inline-flex items-center justify-between text-sm">
        <div className="inline-flex items-center gap-2">
          <FileText className="h-4 w-4" />
          {src.name}
        </div>
        <Button variant="outline" size="sm" asChild>
          <label className="cursor-pointer">
            Replace
            <input
              type="file"
              className="hidden"
              accept=".pdf,.docx"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                // 2. Use the function and set the result using `setFile`
                if (file.type === "application/pdf") {
                  const pdfDoc = await drawHighlight(file);
                  const pdfBytes = await pdfDoc.save();

                  const newFile = new Blob([pdfBytes as BlobPart], { type: "application/pdf" });
                  setFile(new NamedFile(newFile, file.name));
                } else {
                  // fallback for non-PDF files
                  setFile(new NamedFile(file));
                }
              }}
            />
          </label>
        </Button>
      </div>
      {src.contents.type === "application/pdf" && (
        // 3. Embed the PDFDocument
        <iframe
          src={URL.createObjectURL(src.contents)}
          className="grow rounded-xl"
        />
      )}
      {src.name.endsWith(".docx") && (
        <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
          DOCX preview will be available after conversion
        </div>
      )}
    </>
  );
}

export default DocumentPreview;