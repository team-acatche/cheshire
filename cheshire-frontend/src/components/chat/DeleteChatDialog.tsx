    import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"

import type { Chat } from "@/ChatPage"

interface DeleteChatDialogProps {
  chat: Chat | null
  onClose: () => void
  onConfirm: (sessionId: string) => void
}

export function DeleteChatDialog({
  chat,
  onClose,
  onConfirm,
}: DeleteChatDialogProps) {
  return (
    <AlertDialog open={!!chat} onOpenChange={(open) => !open && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete chat?</AlertDialogTitle>
          <AlertDialogDescription>
            This will delete{" "}
            <span className="font-semibold text-foreground">
              {chat?.title}
            </span>
            . This action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <AlertDialogFooter>
          <AlertDialogCancel onClick={onClose}>
            Cancel
          </AlertDialogCancel>

          <AlertDialogAction
            onClick={() => {
              if (chat) {
                onConfirm(chat.session_id)
                onClose()
              }
            }}
            className="bg-red-600 hover:bg-red-700"
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}