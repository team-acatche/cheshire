import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
} from "@/components/ui/sidebar"

import {
  Pencil,
  Settings,
  FileText
} from "lucide-react"


import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding"

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
}

export default function ChatPage({
  onNewChat,
  chats,
  onSelectChat,
  onGoAccount,
  profileImage,
  userName
}: ChatPageProps) {
  const safeChats = Array.isArray(chats) ? chats : []

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
              onClick={() => onSelectChat(chat)}
              className="cursor-pointer flex items-center gap-2 p-2 rounded-md hover:bg-gray-100 text-sm"
            >
              <FileText className="h-4 w-4" />
              <span className="truncate">
                {chat.title}
                </span>
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

    </Sidebar>
  )
}