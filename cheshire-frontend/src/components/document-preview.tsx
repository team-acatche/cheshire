import { FileText } from "lucide-react";
import { NamedFile } from "@/types/NamedFile";

interface DocumentPreviewProps {
  src: NamedFile;
}

export function DocumentPreview({ src }: DocumentPreviewProps) {
  return (
    <>
      <div className="inline-flex items-center justify-between text-sm">
        <div className="inline-flex items-center gap-2">
          <FileText className="h-4 w-4" />
          {src.name}
        </div>
      </div>

      {src.contents.type === "application/pdf" && (
        <iframe
          src={URL.createObjectURL(src.contents)}
          className="grow rounded-xl"
        />
      )}

      {src.name.endsWith(".docx") && (
        <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
          Please upload a .pdf file.
        </div>
      )}
    </>
  );
}

export default DocumentPreview;