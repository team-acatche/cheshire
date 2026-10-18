import type { Chat } from "@/ChatPage"

const isActive = (chat: Chat) => chat.status === "processing"

export function sortChatsByLatest(chats: Chat[]) {
  return [...chats].sort((a, b) => {
    // Processing sessions always float to the top
    const activeA = isActive(a)
    const activeB = isActive(b)
    if (activeA !== activeB) return activeA ? -1 : 1

    const timeA = a.latestTimestamp ? new Date(a.latestTimestamp).getTime() : 0
    const timeB = b.latestTimestamp ? new Date(b.latestTimestamp).getTime() : 0

    return timeB - timeA
  })
}