export function formatTimestamp(timestamp: string | undefined | null): string {
    if (!timestamp) return "Unknown time"

    try {
        // SQLite CURRENT_TIMESTAMP has no timezone suffix - will treat it as UTC
        const normalized = timestamp.endsWith("Z") || timestamp.includes("+")
            ? timestamp
            : timestamp.replace(" ", "T") + "Z"

        const date = new Date(normalized);
        const now = new Date();
        const diffMs = now.getTime() - date.getTime();
        const diffSec = Math.floor(diffMs / 1000);
        const diffMin = Math.floor(diffSec / 60);
        const diffHour = Math.floor(diffMin / 60);
        const diffDay = Math.floor(diffHour / 24);
        const diffWeek = Math.floor(diffDay / 7);
        const diffMonth = Math.floor(diffDay / 30);
        const diffYear = Math.floor(diffDay / 365);

        if (diffSec < 60) return "Just now";
        if (diffMin < 60) return `${diffMin} minute${diffMin > 1 ? 's' : ''} ago`;
        if (diffHour < 24) return `${diffHour} hour${diffHour > 1 ? 's' : ''} ago`;
        if (diffDay < 7) return `${diffDay} day${diffDay > 1 ? 's' : ''} ago`;
        if (diffWeek < 4) return `${diffWeek} week${diffWeek > 1 ? 's' : ''} ago`;
        if (diffMonth < 12) return `${diffMonth} month${diffMonth > 1 ? 's' : ''} ago`;
        return `${diffYear} year${diffYear > 1 ? 's' : ''} ago`;
    } catch {
        return "Unknown";
    }
 }