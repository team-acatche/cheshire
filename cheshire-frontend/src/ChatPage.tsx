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
} from "lucide-react"

import { BadgeQuestionMark } from 'lucide-react';

import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding"
import { useState } from "react"
import { DeleteChatDialog } from "@/components/chat/DeleteChatDialog"
import { HowToUseDialog } from "@/components/chat/HowToUseDialog"

// ✅ Chat type
export type Chat = {
  session_id: string
  title: string
  findings: VulnerabilityFinding[]
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


  // Rename state
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const [chatToDelete, setChatToDelete] = useState<Chat | null>(null)
  const [showHowToUse, setShowHowToUse] = useState(false)

  const startRename = (chat:Chat) => {
    setRenamingId(chat.session_id)
    
    const lastDotIndex = chat.title.lastIndexOf(".")
    if (lastDotIndex !== -1) {
      const nameOnly = chat.title.substring(0, lastDotIndex)
      setRenameValue(nameOnly)
    } else {
      setRenameValue(chat.title)
    }
  }

  const commitRename = (sessionId: string) => {
    const trimmed = renameValue.trim()

    if (trimmed && onRenameChat) {
      const originalChat = chats.find((c) => c.session_id === sessionId)

      if (originalChat) {
        const lastDotIndex = originalChat.title.lastIndexOf(".")
        const extension =
          lastDotIndex !== -1
            ? originalChat.title.substring(lastDotIndex)
            : ""
        const finalName = trimmed + extension
        onRenameChat(sessionId, finalName)
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
          className="flex items-center gap-3 cursor-pointer hover:bg-gray-100 p-2 rounded-md transition-colors"
        >
          <div className="h-9 w-9 rounded-full overflow-hidden border-2 border-black">
            <img src={profileImage} className="h-full w-full object-cover" />
          </div>

          <div>
            <div className="font-medium">{userName}</div>
            <div className="text-xs text-gray-400">account settings</div>
          </div>
        </div>

        {/* NEW CHAT */}
        <div
          onClick={onNewChat}
          className="cursor-pointer flex items-center gap-2 p-2 rounded-md hover:bg-gray-100 transition-colors"
        >
          <Pencil className="h-4 w-4 shrink-0 text-gray-500" />
          <span className="leading-none">New Chat</span>
        </div>

        {/* CHAT HISTORY */}
        <div className="text-xs text-gray-400 mt-4">
          YOUR DOCUMENTS
        </div>

        <div className="flex flex-col gap-1">
          {safeChats.length === 0 && (
            <div className="text-xs text-gray-400">
              No chats yet
            </div>
          )}

          {safeChats.map((chat) => (
            <div
              key={chat.session_id}
              className="group flex items-center gap-2 rounded-md p-2 text-sm hover:bg-gray-100 transition-colors cursor-pointer"
              onClick={() => {
                if (renamingId !== chat.session_id) {
                  onSelectChat(chat)
                }
              }}
            >
              <FileText className="h-4 w-4 shrink-0 text-gray-500" />

              {renamingId === chat.session_id ? (
                <input
                  autoFocus
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitRename(chat.session_id)
                    if (e.key === "Escape") cancelRename()
                  }}
                  onBlur={() => commitRename(chat.session_id)}
                  onClick={(e) => e.stopPropagation()}
                  className="flex-1 min-w-0 rounded border border-gray-300 bg-white px-2 py-1 text-sm outline-none focus:ring-1 focus:ring-blue-500"
                />
              ) : (
                <span className="flex-1 truncate leading-none text-gray-800">
                  {chat.title}
                </span>
              )}

              {renamingId !== chat.session_id && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      onClick={(e) => e.stopPropagation()}
                      className="ml-auto shrink-0 rounded p-1.5 opacity-50 transition hover:bg-gray-200 hover:opacity-100 group-hover:opacity-100 data-[state=open]:bg-gray-200 data-[state=open]:opacity-100"
                      aria-label="Chat options"
                    >
                      <MoreHorizontal className="h-4 w-4 text-gray-500" />
                    </button>
                  </DropdownMenuTrigger>

                  <DropdownMenuContent
                    align="end"
                    className="w-52 rounded-xl border border-gray-200 bg-white p-1 shadow-lg"
                  >
                    <DropdownMenuGroup>
                      <div className="px-2 py-2">
                        <p className="truncate text-sm font-medium text-gray-900">
                          {chat.title}
                        </p>
                      </div>

                      <DropdownMenuSeparator />

                      <DropdownMenuItem
                        onClick={(e) => {
                          e.stopPropagation()
                          startRename(chat)
                        }}
                        className="cursor-pointer rounded-md"
                      >
                        <PenLine className="mr-2 h-4 w-4" />
                        Rename
                      </DropdownMenuItem>

                      <DropdownMenuItem
                        disabled
                        className="cursor-not-allowed rounded-md text-gray-400 focus:bg-transparent"
                      >
                        <Share2 className="mr-2 h-4 w-4" />
                        Share
                        <span className="ml-auto text-[10px] uppercase tracking-wide">
                          Soon
                        </span>
                      </DropdownMenuItem>

                      <DropdownMenuSeparator />

                      <DropdownMenuItem
                        variant="destructive"
                        onClick={(e) => {
                          e.stopPropagation()
                          setChatToDelete(chat)
                        }}
                        className="cursor-pointer rounded-md"
                      >
                        <Trash2 className="mr-2 h-4 w-4" />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuGroup>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
          ))}
        </div>

      </SidebarContent>

      <SidebarFooter className="border-t p-4">
        <div className="flex flex-col gap-2 text-sm text-gray-600">
          <button onClick={onOpenSettings}
            className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left transition-colors hover:bg-gray-100 hover:text-black">
            <Settings className="h-4 w-4 shrink-0" />
            <span>Settings</span>
          </button>

          <button
            type="button"
            onClick={() => setShowHowToUse(true)}
            className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left transition-colors hover:bg-gray-100 hover:text-black"
          >
            <BadgeQuestionMark className="h-4 w-4 shrink-0" />
            <span>How to use?</span>
          </button>

          <button
            type="button"
            onClick={onLogout}
            className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left transition-colors hover:bg-red-50 hover:text-red-600"
          >
            <LogOut className="h-4 w-4 shrink-0" />
            <span>Sign out</span>
          </button>
        </div>
      </SidebarFooter>
      <DeleteChatDialog
        chat={chatToDelete}
        onClose={() => setChatToDelete(null)}
        onConfirm={(sessionId) => {
          onDeleteChat?.(sessionId)
        }}
      />
      <HowToUseDialog
        isOpen={showHowToUse}
        onClose={() => setShowHowToUse(false)}
      />
    </Sidebar>
  )
}