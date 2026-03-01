import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Upload } from "lucide-react"
import CheshireSidebar from "./components/cheshire-sidebar"
import { Card, CardAction, CardContent } from "./components/ui/card"
import {
  SidebarProvider,
  SidebarTrigger,
  SidebarInset,
} from "./components/ui/sidebar"
import DocumentPreview from "./components/document-preview"
import { NamedFile } from "./types/NamedFile"
import { drawHighlight } from "./lib/helpers/page-highlights"
import { evaluateDocument } from "./lib/helpers/evaluate_document"
import { FindingsDisplay } from "./components/findings-display"
import type { VulnerabilityFinding } from "./types/VulnerabilityFinding"

export function App() {
  const [file, setFile] = useState<NamedFile | null>(null)
  const [findings, setFindings] = useState<VulnerabilityFinding[]>([])

  return (
    <SidebarProvider>
      <CheshireSidebar />
      <SidebarTrigger />
      <SidebarInset>
        <main className="grid grid-cols-4 place-items-center h-dvh overflow-hidden">
          <Card className={`${!file ? "col-span-full" : "col-span-3 size-full"} mt-2`}>
            {!file ? (
              <CardContent className="size-full space-y-6 text-center">
                <p className="font-bold text-xl">
                  Hi! Welcome to Cheshire. Please upload a document to evaluate.
                  <br />
                  Thank you!
                </p>

                <CardAction className="flex justify-center m-auto">
                  <Button asChild className="w-40">
                    <label className="cursor-pointer inline-flex items-center gap-2">
                      <Upload className="h-4 w-4" />
                      Upload
                      <input
                        type="file"
                        accept=".pdf,.docx"
                        className="hidden"
                        onChange={async (e) => {
                          const file = e.target.files?.[0];
                          if (!file) return;
                          if (file.type === "application/pdf") {
                            const _findings = await evaluateDocument(file);
                            setFindings(_findings);

                            const pdfDoc = await drawHighlight(file, _findings);
                            const pdfBytes = await pdfDoc.save();

                            const pdfBlob = new Blob([pdfBytes as BlobPart], { type: "application/pdf" })
                            const newFile = new NamedFile(pdfBlob, file.name)
                            setFile(newFile);
                          } else {
                            // fallback for non-PDF files
                            setFile(new NamedFile(file))
                          }
                        }
                        }
                      />
                    </label>
                  </Button>
                </CardAction>
              </CardContent>
            ) : (
              // -------- PREVIEW STATE --------
              <CardContent className="flex flex-col gap-3 size-full">
                <DocumentPreview src={file} setFile={setFile} setFindings={setFindings} />
              </CardContent>
            )}
          </Card>
          {/* TODO: put chat component below this comment */}
          <FindingsDisplay findings={findings} />
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

export default App