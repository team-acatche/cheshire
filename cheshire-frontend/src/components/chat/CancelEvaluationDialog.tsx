import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import type { Chat } from "@/ChatPage"

interface CancelEvaluationDialogProps {
  chat: Chat | null
  onClose: () => void
  onConfirm: (sessionId: string) => void
}

export function CancelEvaluationDialog({ chat, onClose, onConfirm }: CancelEvaluationDialogProps) {
  return (
    <AlertDialog open={!!chat} onOpenChange={(open) => !open && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Cancel analysis?</AlertDialogTitle>
          <AlertDialogDescription>
            Cheshire will stop analyzing{" "}
            <span className="font-semibold text-foreground">{chat?.title}</span>.
            No findings will be saved for this run.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onClose}>Keep running</AlertDialogCancel>
          <AlertDialogAction
            onClick={() => {
              if (chat) onConfirm(chat.session_id)
              onClose()
            }}
          >
            Cancel analysis
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}