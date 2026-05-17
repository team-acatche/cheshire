import type { Chat } from "@/ChatPage"

export function sortChatsByLatest(chats: Chat[]) {
  return [...chats].sort((a, b) => {
    const timeA = a.latestTimestamp
      ? new Date(a.latestTimestamp).getTime()
      : 0

    const timeB = b.latestTimestamp
      ? new Date(b.latestTimestamp).getTime()
      : 0

    return timeB - timeA
  })
}