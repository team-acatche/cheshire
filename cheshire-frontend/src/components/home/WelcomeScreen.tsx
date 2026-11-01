import { useMemo, useCallback, useEffect, useRef, useState, type DragEvent } from "react"
import { AnimatePresence, motion, useReducedMotion } from "framer-motion"
import { ChevronLeft, ChevronRight, Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"

interface WelcomeScreenProps {
  userName: string
  onUpload: (file: File) => void
}

type Slide = { label: string; title: string; body: string; logo?: boolean }

const SLIDES: Slide[] = [
  {
    label: "About",
    title: "About Cheshire",
    body: "Cheshire audits your Technical Design Document against company standards using AI. It flags security gaps and missing sections right on the page, ranks them by severity, and summarizes everything in a compliance report before the InfoSec review.",
    logo: true,
  },
  { label: "01", title: "Document Review", body: "Preview your PDF with search, zoom and full screen while the audit runs." },
  { label: "02", title: "Document Findings", body: "Gaps are highlighted on the page by severity, with recommendations and references." },
  { label: "03", title: "Assessment Report", body: "Get a compliance score and trend, then export the report as a PDF." },
  { label: "04", title: "Chatbot", body: "Discuss the findings directly with the AI." },
]

const AUTOPLAY_MS = 6000
const SWIPE_PX = 50

function getGreeting(date = new Date()) {
  const h = date.getHours()
  if (h < 5) return "Burning the midnight oil"
  if (h < 12) return "Good morning"
  if (h < 18) return "Good afternoon"
  return "Good evening"
}

export default function WelcomeScreen({ userName, onUpload }: WelcomeScreenProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const reduceMotion = useReducedMotion()
  const greeting = useMemo(() => getGreeting(), [])

  // carousel state: [index, direction]
  const [[index, direction], setPage] = useState<[number, number]>([0, 1])
  const [paused, setPaused] = useState(false)

  const go = useCallback((step: number) => {
    setPage(([i]) => [(i + step + SLIDES.length) % SLIDES.length, step])
  }, [])

  const goTo = (target: number) => setPage(([i]) => [target, target >= i ? 1 : -1])

  // Auto-advance; restarts whenever the slide changes, pauses on hover/focus
  useEffect(() => {
    if (paused || reduceMotion) return
    const t = setTimeout(() => go(1), AUTOPLAY_MS)
    return () => clearTimeout(t)
  }, [index, paused, reduceMotion, go])

  const slide = SLIDES[index]

  const pick = (file: File | undefined) => {
    if (file) onUpload(file)
  }

  const onDragOver = (e: DragEvent<HTMLElement>) => {
    e.preventDefault()
    setDragging(true)
  }
  const onDragLeave = (e: DragEvent<HTMLElement>) => {
    if (e.currentTarget.contains(e.relatedTarget as Node | null)) return
    setDragging(false)
  }
  const onDrop = (e: DragEvent<HTMLElement>) => {
    e.preventDefault()
    setDragging(false)
    pick(e.dataTransfer.files?.[0])
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="flex min-h-full flex-col items-center justify-center gap-6 py-4 md:gap-8">
        <motion.section
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: "easeOut" }}
          className="flex w-full max-w-3xl flex-col items-center text-center"
        >
          <h1 className="text-3xl font-bold tracking-tight text-slate-950 dark:text-slate-50 sm:text-4xl md:text-5xl">
            {greeting}, {userName}!
          </h1>

          <Card
            onDragOver={onDragOver}
            onDragEnter={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            className={cn(
              "mt-4 w-full max-w-3xl rounded-2xl border border-slate-200 shadow-sm transition-colors",
              dragging && "border-primary bg-primary/5"
            )}
          >
            <CardContent className="space-y-4 p-2 text-center">
              <p className="text-center text-base text-muted-foreground md:text-lg">
                {dragging
                  ? "Release to start the evaluation."
                  : "Welcome to Cheshire. Please upload a PDF document to start the evaluation."}
              </p>

              <CardAction className="flex w-full items-center justify-center">
                <Button className="mx-auto block w-40" onClick={() => inputRef.current?.click()}>
                  <span className="flex items-center justify-center gap-2">
                    <Upload className="h-4 w-4" />
                    Upload
                  </span>
                </Button>
                <input
                  ref={inputRef}
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={(e) => {
                    pick(e.target.files?.[0])
                    e.target.value = ""
                  }}
                />
              </CardAction>
            </CardContent>
          </Card>
        </motion.section>

        {/* ── Carousel: About + Features ─────────────────────────────── */}
        <motion.section
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.08, ease: "easeOut" }}
          aria-roledescription="carousel"
          aria-label="About Cheshire and features"
          className="w-full max-w-3xl"
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
          onFocus={() => setPaused(true)}
          onBlur={() => setPaused(false)}
        >
          <div className="relative h-60 overflow-hidden rounded-2xl border border-slate-200 bg-card sm:h-52">
            <AnimatePresence initial={false} custom={direction} mode="popLayout">
              <motion.div
                key={index}
                custom={direction}
                role="group"
                aria-roledescription="slide"
                aria-label={`${index + 1} of ${SLIDES.length}`}
                variants={{
                  enter: (d: number) => ({ x: reduceMotion ? 0 : d * 60, opacity: 0 }),
                  center: { x: 0, opacity: 1 },
                  exit: (d: number) => ({ x: reduceMotion ? 0 : d * -60, opacity: 0 }),
                }}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{ duration: 0.35, ease: "easeOut" }}
                drag="x"
                dragConstraints={{ left: 0, right: 0 }}
                dragElastic={0.2}
                onDragEnd={(_, info) => {
                  if (info.offset.x < -SWIPE_PX) go(1)
                  else if (info.offset.x > SWIPE_PX) go(-1)
                }}
                className="absolute inset-0 flex cursor-grab items-center gap-5 px-12 py-6 active:cursor-grabbing md:px-16"
              >
                {slide.logo && (
                  <img
                    src="/cheshire-black.png"
                    alt=""
                    draggable={false}
                    className="hidden size-20 shrink-0 object-contain dark:invert sm:block md:size-24"
                  />
                )}
                <div className="min-w-0 text-left">
                  {!slide.logo && (
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                      Feature {slide.label}
                    </span>
                  )}
                  <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100 md:text-xl">
                    {slide.title}
                  </h2>
                  <p className="mt-1 text-sm leading-relaxed text-muted-foreground md:text-base">
                    {slide.body}
                  </p>
                </div>
              </motion.div>
            </AnimatePresence>

            <button
              type="button"
              onClick={() => go(-1)}
              aria-label="Previous slide"
              className="absolute left-2 top-1/2 z-10 flex size-8 -translate-y-1/2 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <ChevronLeft className="size-5" />
            </button>
            <button
              type="button"
              onClick={() => go(1)}
              aria-label="Next slide"
              className="absolute right-2 top-1/2 z-10 flex size-8 -translate-y-1/2 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <ChevronRight className="size-5" />
            </button>
          </div>

          {/* Dots */}
          <div className="mt-3 flex items-center justify-center gap-2">
            {SLIDES.map((s, i) => (
              <button
                key={s.title}
                type="button"
                onClick={() => goTo(i)}
                aria-label={`Go to ${s.title}`}
                aria-current={i === index}
                className={cn(
                  "h-1.5 rounded-full transition-all duration-300",
                  i === index ? "w-6 bg-primary" : "w-1.5 bg-muted-foreground/30 hover:bg-muted-foreground/60"
                )}
              />
            ))}
          </div>
        </motion.section>
      </div>
    </div>
  )
}