import { cn } from "@/lib/utils"

export const AI_DISCLAIMER = "Cheshire can make mistakes. Verify important security findings."

export function AiDisclaimer({ className }: { className?: string }) {
  return (
    <p className={cn("text-center text-[10px] leading-snug text-muted-foreground/70", className)}>
      {AI_DISCLAIMER}
    </p>
  )
}