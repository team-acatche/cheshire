const HAS_TZ = /(Z|[+-]\d{2}:?\d{2})$/i

/**
 * Parses backend timestamps. Strings without a timezone (e.g. SQLite's
 * CURRENT_TIMESTAMP "YYYY-MM-DD HH:MM:SS") are treated as UTC.
 * Returns null for missing/invalid input.
 */
export function parseTimestamp(timestamp: string | undefined | null): Date | null {
  if (!timestamp) return null
  let s = timestamp.trim()
  if (!s) return null
  if (!s.includes("T")) s = s.replace(" ", "T")
  s = s.replace(/(\.\d{3})\d+/, "$1") // Safari chokes on >3 fractional digits
  if (!HAS_TZ.test(s)) s += "Z"
  const date = new Date(s)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatTimestamp(timestamp: string | undefined | null): string {
  const date = parseTimestamp(timestamp)
  if (!date) return "Unknown time"

  const diffSec = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000))
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)
  const diffWeek = Math.floor(diffDay / 7)
  const diffMonth = Math.floor(diffDay / 30)
  const diffYear = Math.floor(diffDay / 365)

  if (diffSec < 60) return "Just now"
  if (diffMin < 60) return `${diffMin} minute${diffMin > 1 ? "s" : ""} ago`
  if (diffHour < 24) return `${diffHour} hour${diffHour > 1 ? "s" : ""} ago`
  if (diffDay < 7) return `${diffDay} day${diffDay > 1 ? "s" : ""} ago`
  if (diffWeek < 4) return `${diffWeek} week${diffWeek > 1 ? "s" : ""} ago`
  if (diffMonth < 12) return `${diffMonth} month${diffMonth > 1 ? "s" : ""} ago`
  return `${Math.max(1, diffYear)} year${diffYear > 1 ? "s" : ""} ago`
}

export function formatChatTimestamp(timestamp: string | undefined | null): string {
  const date = parseTimestamp(timestamp)
  if (!date) return "Unknown time"

  return date.toLocaleString("en-PH", {
    month: "numeric",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  })
}