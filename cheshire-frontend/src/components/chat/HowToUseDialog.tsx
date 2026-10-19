import { useState, useEffect } from "react"
import { useTheme } from "@/lib/theme"
import { AnimatePresence, motion } from "framer-motion"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import {
  Upload, Loader2, MousePointerClick, MessageCircle,
  ChevronLeft, ChevronRight, Check, Keyboard,
} from "lucide-react"
import { TONES, TONE_ORDER } from "@/components/document-preview/severity"
import { cn } from "@/lib/utils"

interface HowToUseDialogProps {
  isOpen: boolean
  onClose: () => void
}

function useResolvedTheme(): "light" | "dark" {
  const { theme } = useTheme()
  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches
  )

  useEffect(() => {
    const mql = window.matchMedia("(prefers-color-scheme: dark)")
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches)
    mql.addEventListener("change", onChange)
    return () => mql.removeEventListener("change", onChange)
  }, [])

  if (theme === "system") return systemDark ? "dark" : "light"
  return theme
}

const STEPS = [
  {
    icon: Upload,
    title: "Upload a PDF",
    tagline: "Start with your Technical Design Document.",
    points: [
      "Click New Chat, then Upload.",
      "PDF only, up to 100 MB.",
      "Each document gets its own entry under Your Documents.",
    ],
    image: {light: "/how-to-use/step-1-light.png", dark: "/how-to-use/step-1-dark.png"},
  },
  {
    icon: Loader2,
    title: "Let Cheshire analyze",
    tagline: "You don't have to wait around.",
    points: [
      "Your PDF opens right away while the audit runs.",
      "Look for the “Analyzing document…” pill in the toolbar.",
      "You can wait or switch to other documents. The spinner in the sidebar tells you when it's done.",
    ],
    image: {light: "/how-to-use/step-2-light.png", dark: "/how-to-use/step-2-dark.png"},
  },
  {
    icon: MousePointerClick,
    title: "Explore the findings",
    tagline: "Every issue is highlighted right on the page.",
    points: [
      "Click any highlight to see the description, recommendations and references.",
      "Use the Total Findings badge to jump straight to a page.",
      "Document-wide shows issues that aren't tied to a spot, like missing sections.",
      "Click a legend chip to hide or show that severity.",
    ],
    image: {light: "/how-to-use/step-3-light.png", dark: "/how-to-use/step-3-dark.png"},
    showLegend: true,
  },
  {
    icon: MessageCircle,
    title: "Ask the chatbot",
    tagline: "Talk through the findings with AI.",
    points: [
      "Open it with the chat icon at the top right of the preview.",
      "Ask why something was flagged or how to fix it.",
      "Tell it your team's policies. It saves them and uses them in later answers.",
    ],
    image: {light: "/how-to-use/step-4-light.png", dark: "/how-to-use/step-4-dark.png"},
  },
]

const SHORTCUTS: [string, string][] = [
  ["Ctrl/⌘ + F", "Search the PDF"],
  ["Ctrl/⌘ + / −", "Zoom in / out"],
  ["Ctrl/⌘ + 0", "Reset zoom"],
  ["Shift + Enter", "Previous search match"],
]

export function HowToUseDialog({ isOpen, onClose }: HowToUseDialogProps) {
  const resolvedTheme = useResolvedTheme()
  const [step, setStep] = useState(0)
  const current = STEPS[step]
  const isLast = step === STEPS.length - 1

  useEffect(() => { if (isOpen) setStep(0) }, [isOpen])

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-4xl p-0 gap-0 overflow-hidden flex flex-col h-[min(640px,90vh)]">
        <DialogHeader className="px-6 pt-6 pb-4 text-center gap-1">
          <DialogTitle className="text-2xl font-bold">How to Use Cheshire</DialogTitle>
          <DialogDescription>Four quick steps from PDF to fixes.</DialogDescription>
        </DialogHeader>

        <div className="grid md:grid-cols-[250px_1fr] border-t flex-1 min-h-0">
          {/* Step list */}
          <nav className="flex md:flex-col gap-1 p-3 border-b md:border-b-0 md:border-r bg-muted/30 overflow-x-auto">
            {STEPS.map((s, i) => {
              const Icon = s.icon
              const done = i < step
              return (
                <button
                  key={s.title}
                  onClick={() => setStep(i)}
                  className={cn(
                    "flex items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm whitespace-nowrap transition-colors",
                    i === step ? "bg-background shadow-sm font-medium" : "text-muted-foreground hover:bg-muted"
                  )}
                >
                  <span className={cn(
                    "flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                    i === step ? "btn-gradient" : done ? "bg-primary/15 text-primary" : "bg-muted"
                  )}>
                    {done ? <Check className="size-3.5" /> : i + 1}
                  </span>
                  <Icon className="size-4 shrink-0 hidden md:block" />
                  {s.title}
                </button>
              )
            })}
          </nav>

          {/* Content */}
          <div className="p-6 min-h-0 overflow-y-auto scroll-transparent">
            <AnimatePresence mode="wait">
              <motion.div
                key={step}
                initial={{ opacity: 0, x: 16 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -16 }}
                transition={{ duration: 0.2 }}
                className="flex flex-col gap-4"
              >
                <div>
                  <h3 className="text-lg font-semibold">{current.title}</h3>
                  <p className="text-sm text-muted-foreground">{current.tagline}</p>
                </div>

                <ul className="space-y-2 text-sm">
                  {current.points.map((p) => (
                    <li key={p} className="flex gap-2">
                      <Check className="size-4 mt-0.5 shrink-0 text-primary" />
                      <span className="text-foreground/80">{p}</span>
                    </li>
                  ))}
                </ul>

                {current.showLegend && (
                  <div className="flex flex-wrap gap-2">
                    {TONE_ORDER.map((t) => {
                      const s = TONES[t]
                      const Icon = s.icon
                      return (
                        <span
                          key={t}
                          title={s.hint}
                          className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs"
                          style={{ background: `rgb(${s.rgb} / 0.1)`, borderColor: `rgb(${s.rgb} / 0.4)` }}
                        >
                          <Icon className={cn("size-3.5", s.text)} /> {s.label}
                        </span>
                      )
                    })}
                  </div>
                )}

                {current.image && (
                  <img
                    src={current.image[resolvedTheme]}
                    alt={current.title}
                    className="w-full rounded-lg border"
                  />
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>

        {/* Shortcuts strip */}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 px-6 py-3 border-t bg-muted/30 text-xs text-muted-foreground">
          <Keyboard className="size-4" />
          {SHORTCUTS.map(([k, d]) => (
            <span key={k}><kbd className="rounded border bg-background px-1.5 py-0.5 font-mono text-[10px]">{k}</kbd> {d}</span>
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-3 border-t">
          <Button variant="ghost" size="sm" onClick={onClose}>Skip</Button>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={step === 0} onClick={() => setStep(step - 1)}>
              <ChevronLeft /> Back
            </Button>
            <Button size="sm" onClick={() => (isLast ? onClose() : setStep(step + 1))}>
              {isLast ? "Got it!" : <>Next <ChevronRight /></>}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}