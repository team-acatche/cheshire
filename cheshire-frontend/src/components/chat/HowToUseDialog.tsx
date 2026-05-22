import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { Upload, FileText, MessageCircle } from "lucide-react"

interface HowToUseDialogProps {
  isOpen: boolean
  onClose: () => void
}

export function HowToUseDialog({
  isOpen,
  onClose,
}: HowToUseDialogProps) {
  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="!max-w-none !w-[76vw] !left-[50%] !translate-x-[-50%]">
        <DialogHeader className="text-center gap-1">
          <DialogTitle className="text-2xl">How to Use</DialogTitle>
          <DialogDescription>
            Learn how to get the most out of Cheshire
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-3 gap-4">
          <div className="flex flex-col gap-3 p-4 rounded-lg border border-border bg-card">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded bg-blue-100 shrink-0">
                <Upload className="h-4 w-4 text-blue-600" />
              </div>
              <h3 className="font-semibold text-foreground">Getting Started</h3>
            </div>
            <p className="text-sm text-foreground/70">
              Click the "New Chat" button to start a new conversation for each topic.
            </p>
            <div className="mt-2">
              <img src="/howtouse_start.png" alt="How to Use Guide for Getting Started" className="w-full h-auto rounded-lg" />
            </div>  
          </div>

          <div className="flex flex-col gap-3 p-4 rounded-lg border border-border bg-card">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded bg-blue-100 shrink-0">
                <FileText className="h-4 w-4 text-blue-600" />
              </div>
              <h3 className="font-semibold text-foreground">Document Preview</h3>
            </div>
            <p className="text-sm text-foreground/70">
              Preview your uploaded documents and jump to findings with one click.
            </p>
            <div className="mt-2">
              <img src="/docu_findings.jpg" alt="How to Use Guide for Document Preview" className="w-full h-auto rounded-lg" />
            </div>
          </div>

          <div className="flex flex-col gap-3 p-4 rounded-lg border border-border bg-card">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded bg-blue-100 shrink-0">
                <MessageCircle className="h-4 w-4 text-blue-600" />
              </div>
              <h3 className="font-semibold text-foreground">Chatbot</h3>
            </div>
            <p className="text-sm text-foreground/70">
              Interact with the chatbot and discuss your documents with AI.
            </p>
            <div className="mt-2">
              <img src="/chatbot.JPG" alt="How to Use Guide for Chatbot" className="w-full h-auto rounded-lg" />
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
