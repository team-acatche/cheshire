import { Button } from "@/components/ui/button";
import { FileText } from "lucide-react";
// 1. Import the function

interface DocumentPreviewProps {
  src: File,
  setFile: React.Dispatch<React.SetStateAction<File | null>>
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
              onChange={(e) =>
                // 2. Use the function and set the result using `setFile`
                setFile(e.target.files?.[0] ?? null)
              }
            />
          </label>
        </Button>
      </div>
      {src.type === "application/pdf" && (
        // 3. Embed the PDFDocument
        <iframe
          src={URL.createObjectURL(src)}
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