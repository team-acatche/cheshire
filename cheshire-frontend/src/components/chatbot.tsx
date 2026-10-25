import { useState, useRef, useEffect, useCallback, useMemo, type KeyboardEvent, type ReactNode, memo } from "react"
import { Card } from "./ui/card"
import TextareaAutosize from "react-textarea-autosize"
import SentIcon from "./ui/sent-icon"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import remarkBreaks from "remark-breaks"
import type { VulnerabilityFinding } from "@/types/VulnerabilityFinding"
import CodeBlock from "@/components/code-block"
import VulnerabilityFindingComponent from "./vulnerability-finding"
import type { ResponseMessages, ResponseMessage } from "@/lib/chat"
import { EVALUATION_MODE, PROVIDER } from "@/globals"
import { authFetch } from "@/lib/auth"
import { ChevronDown, Square, RotateCw, Copy, Check } from "lucide-react"

type Message = {
  role: "user" | "bot1" | "bot2" | "bot3"
  text: string
}

type ChatPayload = { message: string } | { regenerate: true }

interface ChatbotProps {
  findings: VulnerabilityFinding[]
  sessionId: string
  username: string
  profileImage?: string
  onOpenSettings: () => void
  onActivity?: () => void
  evaluationPending?: boolean
}

function parseFinding(text: string): VulnerabilityFinding | null {
  if (!text.startsWith("{")) return null
  try {
    const o = JSON.parse(text)
    return o && typeof o === "object" && "title" in o && "description" in o
      ? (o as VulnerabilityFinding)
      : null
  } catch {
    return null
  }
}

const isFindingMessage = (text: string) => parseFinding(text) !== null

// ── Module-level so React keeps component identity between renders ───────────
// (Defining these inside Chatbot remounted + re-parsed every message on every
// token / keystroke.)
const markdownComponents = {
  table: ({ children }: { children?: ReactNode }) => (
    <div className="my-4 overflow-x-auto rounded-xl border border-border bg-card shadow-sm">
      <table className="w-full border-collapse text-sm">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }: { children?: ReactNode }) => (
    <thead className="bg-muted text-muted-foreground">
      {children}
    </thead>
  ),
  th: ({ children }: { children?: ReactNode }) => (
    <th className="border border-border px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide md:px-4">
      {children}
    </th>
  ),
  td: ({ children }: { children?: ReactNode }) => (
    <td className="border border-border px-3 py-2 text-sm align-top md:px-4">
      {children}
    </td>
  ),
  tr: ({ children }: { children?: ReactNode }) => (
    <tr className="hover:bg-muted/50">
      {children}
    </tr>
  ),
  p: ({ children }: { children?: ReactNode }) => (
    <p className="mb-3 text-[15px] leading-7 text-foreground">
      {children}
    </p>
  ),
  ul: ({ children }: { children?: ReactNode }) => (
    <ul className="my-3 list-disc space-y-1 pl-6 text-foreground">
      {children}
    </ul>
  ),
  ol: ({ children }: { children?: ReactNode }) => (
    <ol className="my-3 list-decimal space-y-1 pl-6 text-foreground">
      {children}
    </ol>
  ),
  li: ({ children }: { children?: ReactNode }) => (
    <li className="mb-1 wrap-break-word text-foreground">{children}</li>
  ),
  blockquote: ({ children }: { children?: ReactNode }) => (
    <blockquote className="my-2 border-l-4 border-border pl-4 italic text-muted-foreground">
      {children}
    </blockquote>
  ),
  hr: () => (
    <div className="my-8 flex items-center">
      <div className="flex-1 border-t border-border" />
    </div>
  ),
  pre: ({ children }: { children?: ReactNode }) => {
    const codeElement = children as any
    const code = codeElement?.props?.children || ""
    const className = codeElement?.props?.className || ""
    const match = /language-(\w+)/.exec(className || "")
    const language = match ? match[1] : "text"
    return <CodeBlock language={language}>{code}</CodeBlock>
  },
}

const remarkPlugins = [remarkGfm, remarkBreaks]

const MessageBody = memo(function MessageBody({ text, role }: { text: string; role: Message["role"] }) {
  const finding = useMemo(() => parseFinding(text), [text])

  if (finding) {
    return <VulnerabilityFindingComponent finding={finding} />
  }

  const content = (
    <ReactMarkdown remarkPlugins={remarkPlugins} components={markdownComponents}>
      {text}
    </ReactMarkdown>
  )

  return role === "user" ? content : (
    <div className="prose prose-neutral dark:prose-invert max-w-none min-w-0 overflow-hidden wrap-break-word">
      {content}
    </div>
  )
})

export function Chatbot({ findings, sessionId, profileImage, onActivity, evaluationPending = false }: ChatbotProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState<string>("")
  const [typing, setTyping] = useState<boolean>(false)
  const [showScrollDown, setShowScrollDown] = useState(false)
  const [, setUnreadCount] = useState(0)
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const scrollContainerRef = useRef<HTMLDivElement | null>(null)
  const lastEventIdRef = useRef<string | null>(null)
  const isAtBottomRef = useRef(true)
  const abortRef = useRef<AbortController | null>(null)
  const stoppedRef = useRef(false)
  const [copiedMessageIdx, setCopiedMessageIdx] = useState<number | null>(null)

  // Streaming token buffer: flush at most once per animation frame
  const pendingRef = useRef("")
  const rafRef = useRef<number | null>(null)

  // ── Scroll state tracking ──────────────────────────────────────────────────
  const checkScrollPosition = useCallback(() => {
    const container = scrollContainerRef.current
    if (!container) return
    const { scrollTop, scrollHeight, clientHeight } = container
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight
    const atBottom = distanceFromBottom < 80
    isAtBottomRef.current = atBottom
    setShowScrollDown(prev => (prev === !atBottom ? prev : !atBottom))
    if (atBottom) setUnreadCount(0)
  }, [])

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    bottomRef.current?.scrollIntoView({ behavior, block: "end" })
    setUnreadCount(0)
  }, [])

  // ── Load history on session change ────────────────────────────────────────
  useEffect(() => {
    let cancelled = false

    const fetchHistory = async () => {
      try {
        const response = await authFetch(`/api/v1/${sessionId}`)
        if (!response.ok) throw new Error("Failed to fetch history")

        const data = await response.json() as ResponseMessages
        if (cancelled) return
        const backendMessages = data.messages ?? []

        if (backendMessages.length > 0) {
          setMessages(
            backendMessages
              .map((msg: ResponseMessage): Message | null => {
                const text = msg._content.map(c => c.text ?? "").join("\n\n").trim()

                if (
                  text.startsWith("Tool:") ||
                  text.startsWith("Arguments:") ||
                  text === "" ||
                  msg._role === "system"
                ) return null

                return { role: msg._role === "user" ? "user" : "bot1", text }
              })
              .filter((m): m is Message => m !== null)
          )
        } else {
          setMessages([
            ...findings.map((f): Message => ({ role: "bot1", text: JSON.stringify(f) })),
          ])
        }
      } catch {
        if (!cancelled) {
          setMessages([{ role: "bot1", text: "Hello! I'm ready to help you with the document." }])
        }
      }
    }
    fetchHistory()
    // Reset scroll state on session switch
    setShowScrollDown(false)
    setUnreadCount(0)
    isAtBottomRef.current = true

    return () => { cancelled = true }
  }, [sessionId, findings])

  // Cancel any pending frame on unmount
  useEffect(() => () => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
  }, [])

  // ── Message update helpers ────────────────────────────────────────────────
  const appendToLastBotMessage = useCallback((text: string) => {
    setMessages(prev => {
      const updated = [...prev]
      const last = updated[updated.length - 1]
      if (!last || last.role !== "bot1") {
        updated.push({ role: "bot1", text })
      } else {
        updated[updated.length - 1] = { ...last, text: last.text + text }
      }
      return updated
    })
    // If user is scrolled up, increment unread counter
    if (!isAtBottomRef.current) {
      setUnreadCount(prev => prev + 1)
    }
  }, [])

  const replaceLastBotMessage = useCallback((text: string) => {
    setMessages(prev => {
      const updated = [...prev]
      const last = updated[updated.length - 1]
      if (!last || last.role !== "bot1") {
        updated.push({ role: "bot1", text })
      } else {
        updated[updated.length - 1] = { ...last, text }
      }
      return updated
    })
  }, [])

  const flushPending = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    if (!pendingRef.current) return
    const chunk = pendingRef.current
    pendingRef.current = ""
    appendToLastBotMessage(chunk)
  }, [appendToLastBotMessage])

  const queueToken = useCallback((content: string) => {
    pendingRef.current += content
    if (rafRef.current === null) {
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null
        flushPending()
      })
    }
  }, [flushPending])

  const discardPending = () => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    pendingRef.current = ""
  }

  const stopGenerating = () => {
    stoppedRef.current = true
    authFetch(`/api/v1/${sessionId}/stop`, { method: "POST" }).catch(() => {})
    abortRef.current?.abort()
  }

  // ── SSE frame parser ──────────────────────────────────────────────────────
  const processFrame = (frame: string) => {
    if (!frame.trim()) return

    const lines = frame.split("\n")
    let eventType = ""
    const dataLines: string[] = []
    let eventId = ""

    for (const line of lines) {
      if (line.startsWith(":")) {
        return
      } else if (line.startsWith("event:")) {
        eventType = line.slice("event:".length).trim()
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice("data:".length).trim())
      } else if (line.startsWith("id:")) {
        eventId = line.slice("id:".length).trim()
      }
    }

    if (eventId) lastEventIdRef.current = eventId
    if (!eventType || dataLines.length === 0) return

    const dataStr = dataLines.join("\n")

    try {
      const parsed = JSON.parse(dataStr)

      if (eventType === "token" && parsed.content) {
        queueToken(parsed.content)
      } else if (eventType === "done") {
        flushPending()
        if (parsed.content) replaceLastBotMessage(parsed.content)
        lastEventIdRef.current = null
        onActivity?.()
      } else if (eventType === "error") {
        discardPending()
        replaceLastBotMessage(`Error: ${parsed.message ?? "Unknown error"}`)
      }
    } catch (err) {
      console.error("Failed to parse SSE frame:", frame, err)
    }
  }

  // ── SSE consumer ──────────────────────────────────────────────────────────
  const consumeSSE = async (payload: ChatPayload, lastEventId: string | null): Promise<void> => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "Accept": "text/event-stream",
    }
    if (lastEventId !== null) headers["Last-Event-ID"] = lastEventId

    const response = await authFetch(
      `/api/v1/${sessionId}?evaluation_mode=${EVALUATION_MODE}&provider=${PROVIDER}`,
      { method: "POST", headers, body: JSON.stringify(payload), signal: abortRef.current?.signal }
    )

    if (!response.ok) throw new Error("Failed to send message")
    if (!response.body) throw new Error("No response body")

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""

    while (true) {
      const { done, value } = await reader.read()

      if (value) {
        buffer += decoder.decode(value, { stream: true })
        buffer = buffer.replace(/\r\n/g, "\n")

        const frames = buffer.split("\n\n")
        buffer = frames.pop() ?? ""

        for (const frame of frames) {
          processFrame(frame)
        }
      }

      if (done) {
        const remaining = buffer.trim()
        if (remaining) processFrame(remaining)
        break
      }
    }
  }

  // ── Run generation with retry logic ───────────────────────────────────────
  const runGeneration = async (payload: ChatPayload) => {
    setTyping(true)
    onActivity?.()
    setTimeout(() => scrollToBottom("smooth"), 50)

    const MAX_RETRIES = 2
    stoppedRef.current = false
    abortRef.current = new AbortController()
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        await consumeSSE(payload, lastEventIdRef.current)
        break
      } catch {
        flushPending()
        if (stoppedRef.current) {
          // drop the empty placeholder if nothing streamed yet
          setMessages(prev => {
            const last = prev[prev.length - 1]
            return last?.role === "bot1" && last.text === "" ? prev.slice(0, -1) : prev
          })
          break
        }
        if (attempt === MAX_RETRIES) {
          setMessages(prev => {
            const updated = [...prev]
            const last = updated[updated.length - 1]
            if (last?.role === "bot1" && last.text === "") {
              updated[updated.length - 1] = { ...last, text: "Sorry, I encountered an error. Please try again." }
            } else {
              updated.push({ role: "bot1", text: "Sorry, I encountered an error. Please try again." })
            }
            return updated
          })
        } else {
          await new Promise(r => setTimeout(r, 1000 * (attempt + 1)))
        }
      }
    }

    flushPending()
    lastEventIdRef.current = null
    setTyping(false)
    abortRef.current = null
  }

  // ── Send message ──────────────────────────────────────────────────────────
  const sendMessage = async () => {
    if (!input.trim() || typing || evaluationPending) return
    const userText = input
    setMessages(prev => [...prev, { role: "user", text: userText }, { role: "bot1", text: "" }])
    setInput("")
    await runGeneration({ message: userText })
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const copyMessage = async (text: string, index: number) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedMessageIdx(index)

      window.setTimeout(() => {
        setCopiedMessageIdx(current => current === index ? null : current)
      }, 2000)
    } catch (error) {
      console.error("Failed to copy message:", error)
    }
  }

  // ── Auto-scroll only when already at bottom ───────────────────────────────
  // Instant while streaming (smooth scrolling per frame lags and stutters).
  useEffect(() => {
    if (isAtBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: typing ? "auto" : "smooth", block: "end" })
    }
  }, [messages, typing])

  // ── Regenerate ────────────────────────────────────────────────────────────
  const lastUserIdx = messages.map(m => m.role).lastIndexOf("user")
  const lastIdx = messages.length - 1
  const lastMsg = messages[lastIdx]

  // Offered once the last answer has finished (or errored, or was stopped
  // before any text arrived), and never when the last item is a finding card.
  const canRegenerate =
    !typing && !evaluationPending && lastUserIdx !== -1 &&
    (lastMsg?.role === "user" || (lastMsg?.role === "bot1" && !isFindingMessage(lastMsg.text)))

  const regenerate = async () => {
    if (!canRegenerate) return
    setMessages(prev => {
      // drop the old answer, keep finding cards
      const kept = prev.filter((m, i) => i <= lastUserIdx || isFindingMessage(m.text))
      return [...kept, { role: "bot1", text: "" }]
    })
    await runGeneration({ regenerate: true })
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <Card className="h-full w-full min-w-0 flex flex-col overflow-hidden rounded-none pt-3 pb-0 shadow-sm md:pt-6">

      {/* Chat area */}
      <div
        ref={scrollContainerRef}
        onScroll={checkScrollPosition}
        className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden p-3 text-sm scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent md:p-4"
      >
        <div className="flex flex-col gap-6 max-w-4xl mx-auto w-full md:gap-8">
          {messages.map((msg, i) => {
            // Bot copy button: not on finding cards, empty placeholders,
            // or the message that is still streaming.
            const canCopyBot =
              msg.role !== "user" &&
              msg.text !== "" &&
              !isFindingMessage(msg.text) &&
              !(typing && i === lastIdx)

            return (
              <div
                key={i}
                className={`
                  flex items-start gap-2 md:gap-4
                  animate-in fade-in slide-in-from-bottom-2 duration-300
                  ${msg.role === "user" ? "justify-end" : "justify-start"}
                `}
              >
                {msg.role !== "user" && (
                  <div className="w-7 h-7 mt-1 overflow-hidden shrink-0 opacity-80 md:w-8 md:h-8">
                    <img src="/cheshire-black.png" className="w-full h-full object-cover dark:invert" alt="agent" />
                  </div>
                )}

                {msg.role === "user" ? (
                  <div className="group flex min-w-0 max-w-[85%] flex-col items-end gap-1 md:max-w-[80%]">
                    <div className="btn-gradient max-w-full px-4 py-3 rounded-2xl rounded-br-sm text-white text-sm shadow-sm transition-all duration-200 wrap-break-word [&_p]:text-white [&_li]:text-white [&_ol]:text-white [&_ul]:text-white [&_blockquote]:text-white [&_td]:text-white [&_th]:text-white [&_a]:text-white/90">
                      <MessageBody text={msg.text} role={msg.role} />
                    </div>

                    <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 pointer-coarse:opacity-100">
                      <button
                        type="button"
                        onClick={() => copyMessage(msg.text, i)}
                        className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                        title={copiedMessageIdx === i ? "Copied!" : "Copy message"}
                        aria-label={copiedMessageIdx === i ? "Message copied" : "Copy message"}
                      >
                        {copiedMessageIdx === i ? (
                          <Check className="size-3.5" />
                        ) : (
                          <Copy className="size-3.5" />
                        )}
                      </button>

                      {canRegenerate && i === lastUserIdx && (
                        <button
                          type="button"
                          onClick={regenerate}
                          className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                          title="Regenerate response"
                          aria-label="Regenerate response"
                        >
                          <RotateCw className="size-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="group flex min-w-0 flex-1 flex-col gap-1 overflow-hidden text-foreground">
                    <MessageBody text={msg.text} role={msg.role} />

                    {canCopyBot && (
                      <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 pointer-coarse:opacity-100">
                        <button
                          type="button"
                          onClick={() => copyMessage(msg.text, i)}
                          className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                          title={copiedMessageIdx === i ? "Copied!" : "Copy response"}
                          aria-label={copiedMessageIdx === i ? "Response copied" : "Copy response"}
                        >
                          {copiedMessageIdx === i ? (
                            <Check className="size-3.5" />
                          ) : (
                            <Copy className="size-3.5" />
                          )}
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {msg.role === "user" && (
                  <div className="hidden w-8 h-8 rounded-full overflow-hidden shrink-0 ring-1 ring-border sm:block">
                    <img
                      src={profileImage || "/User.png"}
                      onError={(e) => { e.currentTarget.src = "/User.png" }}
                      className="w-full h-full object-cover"
                      alt="user"
                    />
                  </div>
                )}
              </div>
            )
          })}

          {typing && (
            <div className="flex items-start gap-3 animate-in fade-in duration-300">
              <div className="w-6 h-6 mt-1 overflow-hidden shrink-0 opacity-80">
                <img
                  src="/cheshire-black.png"
                  className="w-full h-full object-cover dark:invert"
                  alt="agent"
                />
              </div>

              <div className="flex items-center gap-1 pt-1.5">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.3s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.15s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60" />
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input area — position relative so the scroll button can be anchored to it.
          The bottom padding respects the iPhone home-indicator safe area. */}
      <div className="sticky bottom-0 z-10 bg-linear-to-t from-background via-background/95 to-transparent px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-4 md:px-4 md:pb-4 md:pt-6">

        {/* Scroll-to-bottom button */}
        {showScrollDown && (
          <button
            onClick={() => scrollToBottom("smooth")}
            className="
              absolute -top-12 left-1/2 -translate-x-1/2
              flex h-10 w-10 items-center justify-center
              rounded-full
              hover:bg-background/50
              transition-all duration-200
            "
            aria-label="Scroll to latest message"
          >
            <ChevronDown className="h-7 w-7 drop-shadow-lg" />
          </button>
        )}

        <div className="mx-auto max-w-4xl">
          <div
            className="
              relative
              flex items-end gap-2 md:gap-3
              rounded-[24px] md:rounded-[28px]
              border border-border/60
              bg-background/80
              px-4 py-3 md:px-5 md:py-4
              shadow-[0_8px_30px_rgba(0,0,0,0.06)]
              backdrop-blur-xl
              transition-all duration-200
              focus-within:border-border
              focus-within:shadow-[0_12px_40px_rgba(0,0,0,0.10)]
            "
          >
            <div className="pointer-events-none absolute inset-0 rounded-[24px] ring-1 ring-white/5 md:rounded-[28px]" />

            <TextareaAutosize
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="What would you like to know?"
              disabled={typing || evaluationPending}
              minRows={1}
              maxRows={8}
              // 16px on mobile prevents iOS Safari from zooming into the field on focus
              className="
                max-h-52
                min-w-0
                flex-1
                resize-none
                border-0
                bg-transparent
                p-0
                text-base
                leading-7
                text-foreground
                shadow-none
                outline-none
                focus:outline-none
                focus-visible:ring-0
                disabled:opacity-50
                placeholder:text-muted-foreground/70
                md:text-[15px]
              "
            />
            {typing ? (
              <button
                type="button"
                onClick={stopGenerating}
                aria-label="Stop generating"
                title="Stop generating"
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-foreground text-background transition-all duration-200 hover:scale-105 hover:opacity-90 active:scale-95"
              >
                <Square className="size-4 fill-current" />
              </button>
            ) : (
              <button
                onClick={sendMessage}
                disabled={typing || evaluationPending || !input.trim()}
                aria-label="Send message"
                className="
                  flex h-10 w-10 shrink-0 items-center justify-center
                  rounded-full
                  bg-muted
                  text-muted-foreground
                  transition-all duration-200
                  hover:scale-105
                  hover:bg-muted/80
                  active:scale-95
                  disabled:scale-100
                  disabled:cursor-not-allowed
                  disabled:opacity-50
                "
              >
                <SentIcon size={18} color="currentColor" />
              </button>
            )}

          </div>

          <p className="mt-2 text-center text-[11px] text-muted-foreground/60 md:text-xs">
            Cheshire can make mistakes. Verify important security findings.
          </p>
        </div>
      </div>
    </Card>
  )
}