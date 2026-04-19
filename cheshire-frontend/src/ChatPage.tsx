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
} from "lucide-react"


import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding"
import { useState } from "react"
import { DeleteChatDialog } from "@/components/chat/DeleteChatDialog"

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
}: ChatPageProps) {
  const safeChats = Array.isArray(chats) ? chats : []


  // Rename state
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState("")
  const [chatToDelete, setChatToDelete] = useState<Chat | null>(null)

  const startRename = (chat: Chat) => {
    setRenamingId(chat.session_id)
    setRenameValue(chat.title)
  }

  const commitRename = (sessionId: string) => {
    const trimmed = renameValue.trim()
    if (trimmed && onRenameChat) {
      onRenameChat(sessionId, trimmed)
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
          className="flex items-center gap-3 cursor-pointer hover:bg-gray-100 p-2 rounded-md"
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
          className="cursor-pointer flex items-center gap-2 p-2 rounded-md hover:bg-gray-100"
        >
          <Pencil className="h-4 w-4" />
          <span>New Chat</span>
        </div>

        {/* CHAT HISTORY */}
        <div className="text-xs text-gray-400 mt-4">
          YOUR CHATS
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
              className="flex items-center gap-2 p-2 rounded-md hover:bg-gray-100 text-sm cursor-pointer"
              onClick={() => {
                if (renamingId !== chat.session_id) {
                  onSelectChat(chat)
                }
              }}
            >
              <FileText className="h-4 w-4 shrink-0" />

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
                  className="flex-1 min-w-0 bg-white border border-gray-300 rounded px-1.5 py-0.5 text-sm outline-none focus:ring-1 focus:ring-blue-500"
                />
              ) : (
                <span className="truncate flex-1 leading-none">
                  {chat.title}
                </span>
              )}

              {/* —— Ellipsis Dropdown —— */}
              {renamingId !== chat.session_id && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      onClick={(e) => e.stopPropagation()}
                      className="ml-auto shrink-0 p-1.5 rounded opacity-0 hover:bg-gray-200 transition-all group-hover:opacity-100 data-[state-open]:opacity-100"
                      aria-label="Chat options"
                    >
                      <MoreHorizontal className="h-4 w-4 text-gray-500" />
                    </button>
                  </DropdownMenuTrigger>

                  <DropdownMenuContent
                    className="w-52 rounded-xl border border-gray-200 bg-white p-1 shadow-lg"
                    align="end"
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
                      >
                        <PenLine className="h-4 w-4 mr-2" />
                        Rename
                      </DropdownMenuItem>

                      <DropdownMenuItem
                        onClick={(e) => {
                          e.stopPropagation()
                        }}
                      >
                        <Share2 className="h-4 w-4 mr-2" />
                        Share
                      </DropdownMenuItem>

                      <DropdownMenuSeparator />

                      <DropdownMenuItem
                        variant="destructive"
                        onClick={(e) => {
                          e.stopPropagation()
                          setChatToDelete(chat)
                        }}
                      >
                        <Trash2 className="h-4 w-4 mr-2" />
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

      <SidebarFooter className="p-4 border-t">
        <div className="cursor-pointer flex items-center gap-2 text-sm hover:text-gray-600">
          <Settings className="h-4 w-4" />
          <span>Settings</span>
        </div>
      </SidebarFooter>
      <DeleteChatDialog
        chat={chatToDelete}
        onClose={() => setChatToDelete(null)}
        onConfirm={(sessionId) => {
          onDeleteChat?.(sessionId)
        }}
      />
    </Sidebar>
  )
}