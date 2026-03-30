import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
} from "@/components/ui/sidebar"

import {
  User,
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
}

export default function ChatPage({
  onNewChat,
  chats,
  onSelectChat
}: ChatPageProps) {
  return (
    <Sidebar>

      <SidebarContent className="p-4 space-y-4">

        {/* ACCOUNT */}
        <div className="flex items-center gap-3 text-sm text-black">

          {/* ICON WITH ROUND BORDER */}
          <div className="h-9 w-9 flex items-center justify-center rounded-full border-2 border-black">
            <User className="h-5 w-5" />
          </div>

          <div>
            <div className="font-medium">account name</div>
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
          {chats.length === 0 && (
            <div className="text-xs text-gray-400">
              No chats yet
            </div>
          )}

          {chats.map((chat) => (
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