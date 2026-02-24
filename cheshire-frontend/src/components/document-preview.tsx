import { Button } from "@/components/ui/button";
import { FileText } from "lucide-react";

interface DocumentPreviewProps {
  src: File,
  setFile: React.Dispatch<React.SetStateAction<File | null>>
}

export function DocumentPreview({ src, setFile }: DocumentPreviewProps) {
  return (
    <>
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center gap-2">
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
                setFile(e.target.files?.[0] ?? null)
              }
            />
          </label>
        </Button>
      </div>
      {src.type === "application/pdf" && (
        <iframe
          src={URL.createObjectURL(src)}
          className="grow"
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