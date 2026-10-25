import type { Chat } from "@/ChatPage"
import { parseTimestamp } from "@/lib/helpers/format_timestamps"

const isActive = (chat: Chat) => chat.status === "processing"
const time = (chat: Chat) => parseTimestamp(chat.latestTimestamp)?.getTime() ?? 0

export function sortChatsByLatest(chats: Chat[]) {
  return [...chats].sort((a, b) => {
    // Processing sessions always float to the top
    const activeA = isActive(a)
    const activeB = isActive(b)
    if (activeA !== activeB) return activeA ? -1 : 1

    return time(b) - time(a)
  })
}