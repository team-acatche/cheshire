// cheshire-frontend/src/ChatPage.tsx

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
} from "@/components/ui/sidebar"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

import {
  Pencil,
  Settings,
  FileText,
  MoreHorizontal,
  Trash2,
  PenLine,
  Share2,
  LogOut,
  Loader2,
} from "lucide-react"

import { BadgeQuestionMark } from "lucide-react"

import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding"
import { useState } from "react"
import { DeleteChatDialog } from "@/components/chat/DeleteChatDialog"
import { HowToUseDialog } from "@/components/chat/HowToUseDialog"
import { formatChatTimestamp, formatTimestamp } from "./lib/helpers/format_timestamps"

export type ChatStatus = "processing" | "done" | "failed"

export type Chat = {
  session_id: string
  title: string
  findings: VulnerabilityFinding[]
  status?: ChatStatus   // undefined = legacy/done
  latestTimestamp?: string | null
}

interface ChatPageProps {
  onNewChat: () => void
  chats: Chat[]
  onSelectChat: (chat: Chat) => void
  onGoAccount: () => void
  profileImage: string
  userName: string
  onDeleteChat?: (sessionId: string) => void
  onRenameChat?: (sessionId: string, newTitle: string) => void
  onLogout: () => void
  onOpenSettings: () => void
}

export default function ChatPage({
  onNewChat,
  chats,
  onSelectChat,
  onGoAccount,
  profileImage,
  userName,
  onDeleteChat,
  onRenameChat,
  onLogout,
  onOpenSettings,
}: ChatPageProps) {
  const safeChats = Array.isArray(chats) ? chats : []

  const [renamingId, setRenamingId]   = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const [chatToDelete, setChatToDelete] = useState<Chat | null>(null)
  const [showHowToUse, setShowHowToUse] = useState(false)

  const startRename = (chat: Chat) => {
    setRenamingId(chat.session_id)
    const lastDotIndex = chat.title.lastIndexOf(".")
    setRenameValue(lastDotIndex !== -1 ? chat.title.substring(0, lastDotIndex) : chat.title)
  }

  const commitRename = (sessionId: string) => {
    const trimmed = renameValue.trim()
    if (trimmed && onRenameChat) {
      const originalChat = chats.find((c) => c.session_id === sessionId)
      if (originalChat) {
        const lastDotIndex = originalChat.title.lastIndexOf(".")
        const extension = lastDotIndex !== -1 ? originalChat.title.substring(lastDotIndex) : ""
        onRenameChat(sessionId, trimmed + extension)
      }
    }
    setRenamingId(null)
    setRenameValue("")
  }

  const cancelRename = () => {
    setRenamingId(null)
    setRenameValue("")
  }

  return (
    <Sidebar>
      <SidebarContent className="p-4 space-y-4">

        {/* ACCOUNT */}
        <div
          onClick={onGoAccount}
          className="flex items-center gap-3 cursor-pointer hover:bg-muted p-2 rounded-md transition-colors"
        >
          <div className="h-9 w-9 rounded-full overflow-hidden border-2 border-border shrink-0">
            <img src={profileImage} className="h-full w-full object-cover" alt="profile" />
          </div>
          <div>
            <div className="font-medium text-foreground">{userName}</div>
            <div className="text-xs text-muted-foreground">account settings</div>
          </div>
        </div>

        {/* NEW CHAT */}
        <div
          onClick={onNewChat}
          className="cursor-pointer flex items-center gap-2 p-2 rounded-md hover:bg-muted transition-colors"
        >
          <Pencil className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="leading-none text-foreground">New Chat</span>
        </div>

        {/* CHAT HISTORY */}
        <div className="text-xs text-muted-foreground mt-4 px-1 uppercase tracking-wide">
          Your Documents
        </div>

        <div className="flex flex-col gap-1">
          {safeChats.length === 0 && (
            <div className="text-xs text-muted-foreground px-1">No chats yet</div>
          )}

          {safeChats.map((chat) => {
            const isProcessing = chat.status === "processing"
            const isFailed     = chat.status === "failed"

            return (
              <div
                key={chat.session_id}
                className={`group flex items-center gap-2 rounded-md p-2 text-sm transition-colors
                  ${isProcessing
                    ? "opacity-70 cursor-default"
                    : isFailed
                      ? "opacity-60 cursor-default"
                      : "hover:bg-muted cursor-pointer"
                  }`}
                onClick={() => {
                  if (!isProcessing && !isFailed && renamingId !== chat.session_id) {
                    onSelectChat(chat)
                  }
                }}
              >
                {/* Icon */}
                {isProcessing ? (
                  <Loader2 className="h-4 w-4 shrink-0 text-muted-foreground animate-spin" />
                ) : (
                  <FileText className={`h-4 w-4 shrink-0 ${isFailed ? "text-destructive" : "text-muted-foreground"}`} />
                )}

                {/* Title / rename input */}
                {renamingId === chat.session_id ? (
                  <input
                    autoFocus
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter")  commitRename(chat.session_id)
                      if (e.key === "Escape") cancelRename()
                    }}
                    onBlur={() => commitRename(chat.session_id)}
                    onClick={(e) => e.stopPropagation()}
                    className="flex-1 min-w-0 rounded border border-input bg-background text-foreground px-2 py-1 text-sm outline-none focus:ring-1 focus:ring-ring"
                  />
                ) : (
                  <div className="flex-1 min-w-0">
                    <span className={`block truncate leading-none ${isFailed ? "text-destructive" : "text-foreground"}`}>
                      {chat.title}
                    </span>
                    {isProcessing && (
                      <span className="block text-[10px] text-muted-foreground mt-0.5">
                        Analyzing…
                      </span>
                    )}
                    {isFailed && (
                      <span className="block text-[10px] text-destructive mt-0.5">
                        Evaluation failed
                      </span>
                    )}
                  </div>
                )}

                {/* Actions — hidden while processing */}
                {!isProcessing && renamingId !== chat.session_id && (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button
                        type="button"
                        onClick={(e) => e.stopPropagation()}
                        className="ml-auto shrink-0 rounded p-1.5 opacity-0 transition hover:bg-muted group-hover:opacity-100 data-[state=open]:bg-muted data-[state=open]:opacity-100"
                        aria-label="Chat options"
                      >
                        <MoreHorizontal className="h-4 w-4 text-muted-foreground" />
                      </button>
                    </DropdownMenuTrigger>

                    <DropdownMenuContent align="end" className="w-52">
                      <DropdownMenuGroup>
                        <div className="px-2 py-2">
                          <p className="truncate text-sm font-medium text-foreground">
                            {chat.title}
                          </p>
                        </div>

                        <DropdownMenuSeparator />

                        <DropdownMenuItem
                          onClick={(e) => { e.stopPropagation(); startRename(chat) }}
                          className="cursor-pointer"
                        >
                          <PenLine className="mr-2 h-4 w-4" />
                          Rename
                        </DropdownMenuItem>

                        <DropdownMenuItem disabled className="cursor-not-allowed">
                          <Share2 className="mr-2 h-4 w-4" />
                          Share
                          <span className="ml-auto text-[10px] uppercase tracking-wide text-muted-foreground">
                            Soon
                          </span>
                        </DropdownMenuItem>

                        <DropdownMenuSeparator />

                        <DropdownMenuItem
                          variant="destructive"
                          onClick={(e) => { e.stopPropagation(); setChatToDelete(chat) }}
                          className="cursor-pointer"
                        >
                          <Trash2 className="mr-2 h-4 w-4" />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuGroup>
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
              </div>
            )
          })}
        </div>

      </SidebarContent>

      <SidebarFooter className="border-t border-border p-4">
        <div className="flex flex-col gap-1 text-sm text-muted-foreground">
          <button
            onClick={onOpenSettings}
            className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left transition-colors hover:bg-muted hover:text-foreground"
          >
            <Settings className="h-4 w-4 shrink-0" />
            <span>Settings</span>
          </button>

          <button
            type="button"
            onClick={() => setShowHowToUse(true)}
            className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left transition-colors hover:bg-muted hover:text-foreground"
          >
            <BadgeQuestionMark className="h-4 w-4 shrink-0" />
            <span>How to use?</span>
          </button>

          <button
            type="button"
            onClick={onLogout}
            className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left transition-colors hover:bg-destructive/10 hover:text-destructive"
          >
            <LogOut className="h-4 w-4 shrink-0" />
            <span>Sign out</span>
          </button>
        </div>
      </SidebarFooter>

      <DeleteChatDialog
        chat={chatToDelete}
        onClose={() => setChatToDelete(null)}
        onConfirm={(sessionId) => onDeleteChat?.(sessionId)}
      />
      <HowToUseDialog
        isOpen={showHowToUse}
        onClose={() => setShowHowToUse(false)}
      />
    </Sidebar>
  )
}