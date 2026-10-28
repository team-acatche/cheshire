import { useState, useEffect, useRef } from "react"
import { Upload, FileText, MessageSquareText } from "lucide-react"
import { Button } from "@/components/ui/button"
import { motion } from "framer-motion"
import { Card, CardAction, CardContent } from "./components/ui/card"
import {
  SidebarProvider,
  SidebarTrigger,
  SidebarInset,
} from "./components/ui/sidebar"
import { usePanelRef } from "react-resizable-panels"
import DocumentPreview from "./components/document-preview/DocumentPreview"
import {
  submitEvaluation,
  pollEvaluation,
  getSessionResults,
  cancelEvaluation,
  rerunEvaluation,
} from "./lib/helpers/evaluate_document"
import { useEvaluationProgress } from "@/hooks/use-evaluation-progress"
import { useIsMobile } from "@/hooks/use-mobile"
import { validatePdf } from "./lib/helpers/validate_pdf"
import { authFetch, type AuthUser, clearAuth } from "./lib/auth"
import { sortChatsByLatest } from "@/lib/sortChatsByLatest"
import { parseTimestamp } from "@/lib/helpers/format_timestamps"
import { cn } from "@/lib/utils"
import type { VulnerabilityFinding } from "./types/VulnerabilityFinding"
import { Chatbot } from "./components/chatbot"
import ChatPage from "./ChatPage"
import type { Chat, ChatStatus } from "./ChatPage"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"
import Account from "./components/account"
import ReportPage from "./components/report/ReportPage"
import SettingsModal from "./components/settings-modal"
import { toast } from "sonner"
import { CancelEvaluationDialog } from "@/components/chat/CancelEvaluationDialog"

// ─── API helpers ──────────────────────────────────────────────────────────────

interface RawSession {
  session_id: string
  title: string
  status?: string
  created_at?: string | null
}

async function fetchSessions(): Promise<RawSession[]> {
  return authFetch("/api/v1/")
    .then(r => (r.ok ? r.json() : []))
    .catch(() => [])
}

async function deleteSession(sessionId: string): Promise<boolean> {
  return authFetch(`/api/v1/${sessionId}`, { method: "DELETE" })
    .then(r => r.ok || r.status === 204)
    .catch(() => false)
}

async function renameSession(sessionId: string, newTitle: string): Promise<boolean> {
  return authFetch(`/api/v1/${sessionId}/rename`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ new_title: newTitle }),
  })
    .then(r => r.ok)
    .catch(() => false)
}

async function fetchSessionTimestamp(sessionId: string): Promise<string | null> {
  return authFetch(`/api/v1/${sessionId}/latest-timestamp`)
    .then(r => {
      if (r.status === 204) return null
      if (!r.ok) return null
      return r.json().then((d: { latest_timestamp: string }) => d.latest_timestamp)
    })
    .catch(() => null)
}

/** Fetch the document blob for a session, or null if not yet available. */
async function fetchDocumentBlob(sessionId: string): Promise<string | null> {
  return authFetch(`/api/v1/${sessionId}/document`)
    .then((r) => (r.ok ? r.blob().then((b) => URL.createObjectURL(b)) : null))
    .catch(() => null)
}

const revokeIfBlob = (v: File | string | null) => {
  if (typeof v === "string" && v.startsWith("blob:")) URL.revokeObjectURL(v)
}

/** Returns whichever timestamp is later (invalid/missing loses). */
function laterTimestamp(a?: string | null, b?: string | null): string | null {
  const ta = parseTimestamp(a)?.getTime() ?? -Infinity
  const tb = parseTimestamp(b)?.getTime() ?? -Infinity
  if (ta === -Infinity && tb === -Infinity) return null
  return ta >= tb ? (a ?? null) : (b ?? null)
}

// ─── App ──────────────────────────────────────────────────────────────────────

interface AppProps {
  user: AuthUser
  onLogout: () => void
}

type MobileTab = "document" | "chat"
type AppPage = "chat" | "account" | "report"

const MOBILE_TABS: { id: MobileTab; label: string; icon: typeof FileText }[] = [
  { id: "document", label: "Document", icon: FileText },
  { id: "chat", label: "Chat", icon: MessageSquareText },
]

/**
 * Maps the backend status string to the frontend ChatStatus union.
 * "pending" and "processing" both show a loading spinner in the sidebar.
 */
function toFrontendStatus(backendStatus: string): ChatStatus {
  if (backendStatus === "done") return "done"
  if (backendStatus === "failed") return "failed"
  if (backendStatus === "cancelled") return "cancelled"
  return "processing"
}

export default function App({ user, onLogout }: AppProps) {
  const isMobile = useIsMobile()

  const [file, setFile] = useState<File | string | null>(null)
  const [findings, setFindings] = useState<VulnerabilityFinding[]>([])
  const [findingsLoading, setFindingsLoading] = useState(false)
  const [chats, setChats] = useState<Chat[]>([])
  const [chatsLoading, setChatsLoading] = useState(true)
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [currentFileName, setCurrentFileName] = useState<string>("document.pdf")
  const [page, setPage] = useState<AppPage>("chat")
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [chatToCancel, setChatToCancel] = useState<Chat | null>(null)
  const [mobileTab, setMobileTab] = useState<MobileTab>("document")

  // Refs kept in sync with state so async callbacks never read stale values.
  const currentSessionIdRef = useRef<string | null>(null)
  const fileRef = useRef<File | string | null>(null)

  const selectSession = (id: string | null) => {
    currentSessionIdRef.current = id
    setCurrentSessionId(id)
  }

  /** Swap the displayed document, revoking the previous blob URL to avoid leaks. */
  const replaceFile = (next: File | string | null) => {
    const prev = fileRef.current
    if (prev !== next) revokeIfBlob(prev)
    fileRef.current = next
    setFile(next)
  }

  // Revoke the last blob URL on unmount
  useEffect(() => () => revokeIfBlob(fileRef.current), [])

  // ── Chat panel state ─────────────────────────────────────────────────────────
  // Desktop: a collapsible resizable panel. Mobile: a "Chat" tab.
  const [chatOpen, setChatOpen] = useState(false)
  const chatPanelRef = usePanelRef()

  const closeChat = () => {
    chatPanelRef.current?.collapse()
    setChatOpen(false)
    setMobileTab("document")
  }

  const toggleChat = () => {
    const panel = chatPanelRef.current
    if (!panel) return
    if (panel.isCollapsed()) panel.expand()
    else panel.collapse()
  }

  // Track active polling tasks so we can resume them after refresh
  const pollingRef = useRef<Set<string>>(new Set())

  const [profileImage, setProfileImage] = useState(
    user.avatar_uri ? `/api/v1/${user.avatar_uri}` : "/api/v1/avatars/default.png"
  )

  // ── Poll one evaluation to completion (used for uploads, resumes and reruns) ──
  const trackEvaluation = (session_id: string) => {
    if (pollingRef.current.has(session_id)) return
    pollingRef.current.add(session_id)

    pollEvaluation(session_id).then(async (response) => {
      pollingRef.current.delete(session_id)
      const isCurrent = () => currentSessionIdRef.current === session_id

      if (response === null) {
        setChats(prev =>
          prev.map(c => c.session_id === session_id ? { ...c, status: "failed" } : c)
        )
        if (isCurrent()) setFindingsLoading(false)
        return
      }

      if (response.cancelled) {
        setChats(prev =>
          prev.map(c => c.session_id === session_id ? { ...c, status: "cancelled" } : c)
        )
        if (isCurrent()) setFindingsLoading(false)
        return
      }

      setChats(prev =>
        sortChatsByLatest(
          prev.map(c =>
            c.session_id === session_id
              ? {
                  ...c,
                  findings: response.vulnerabilities,
                  status: "done",
                  latestTimestamp: new Date().toISOString(),
                }
              : c
          )
        )
      )

      if (!isCurrent()) return
      setFindings(response.vulnerabilities)
      setFindingsLoading(false)

      // Resumed sessions may not have the document yet (an uploaded File already does)
      if (!fileRef.current) {
        const url = await fetchDocumentBlob(session_id)
        if (!url) return
        if (isCurrent() && !fileRef.current) replaceFile(url)
        else URL.revokeObjectURL(url)
      }
    })
  }

  // Load existing sessions on mount. The list renders immediately; the
  // per-session "latest activity" timestamps are filled in afterwards.
  useEffect(() => {
    let cancelled = false

    const loadSessions = async () => {
      const rawSessions = await fetchSessions()
      if (cancelled) return

      const initial: Chat[] = rawSessions.map((s) => ({
        session_id: s.session_id,
        title: s.title,
        findings: [],
        status: toFrontendStatus(s.status ?? "done"),
        latestTimestamp: s.created_at ?? null,
      }))

      setChats(prev => {
        // keep anything the user already did (e.g. an upload) before the list arrived
        const known = new Set(initial.map(c => c.session_id))
        return sortChatsByLatest([...prev.filter(c => !known.has(c.session_id)), ...initial])
      })
      setChatsLoading(false)

      // Resume polling for any sessions that aren't done/failed/cancelled
      for (const chat of initial) {
        if (chat.status === "processing") trackEvaluation(chat.session_id)
      }

      // Background: fetch real latest-activity timestamps, apply in ONE state update
      const stamps = await Promise.all(initial.map(c => fetchSessionTimestamp(c.session_id)))
      if (cancelled) return
      const byId = new Map(initial.map((c, i) => [c.session_id, stamps[i]]))

      setChats(prev =>
        sortChatsByLatest(
          prev.map(c => {
            if (!byId.has(c.session_id)) return c
            return { ...c, latestTimestamp: laterTimestamp(byId.get(c.session_id), c.latestTimestamp) }
          })
        )
      )
    }

    loadSessions().catch(() => { if (!cancelled) setChatsLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Sidebar helpers ───────────────────────────────────────────────────────

  const handleNewChat = () => {
    setFindings([])
    setFindingsLoading(false)
    setPage("chat")
    selectSession(null)
    replaceFile(null)
    closeChat()
  }

  const handleSelectChat = async (chat: Chat) => {
    setPage("chat")
    selectSession(chat.session_id)
    setCurrentFileName(chat.title)
    closeChat()

    // The user may click another chat while this one is still loading
    const isStale = () => currentSessionIdRef.current !== chat.session_id

    if (chat.status === "processing") {
      setFindings([])
      setFindingsLoading(true)

      const blobUrl = await fetchDocumentBlob(chat.session_id)
      if (!blobUrl) return
      if (isStale()) URL.revokeObjectURL(blobUrl)
      else replaceFile(blobUrl)
      return
    }

    // Done or unknown status — load doc + results
    replaceFile(null)
    setFindings([])
    setFindingsLoading(true)

    try {
      const [blobUrl, results] = await Promise.all([
        fetchDocumentBlob(chat.session_id),
        getSessionResults(chat.session_id),
      ])
      if (isStale()) {
        if (blobUrl) URL.revokeObjectURL(blobUrl)
        return
      }
      replaceFile(blobUrl)
      setFindings(results)
    } finally {
      if (!isStale()) setFindingsLoading(false)
    }
  }

  // Opens the assessment report for a finished document. If it isn't the open
  // document yet, it is loaded first (the report shows a skeleton meanwhile).
  const handleOpenReport = async (chat: Chat) => {
    if (currentSessionIdRef.current === chat.session_id && !findingsLoading) {
      setPage("report")
      return
    }
    const loading = handleSelectChat(chat) // sets page to "chat" synchronously...
    setPage("report")                      // ...so this must come after it
    await loading
  }

  const touchChat = (sessionId: string) => {
    const now = new Date().toISOString()
    setChats(prev =>
      sortChatsByLatest(
        prev.map(chat =>
          chat.session_id === sessionId
            ? { ...chat, latestTimestamp: now }
            : chat
        )
      )
    )
  }

  const handleDeleteChat = async (sessionId: string) => {
    const ok = await deleteSession(sessionId)
    if (!ok) {
      console.error(`Failed to delete session ${sessionId}`)
      return
    }
    setChats(prev => prev.filter(c => c.session_id !== sessionId))
    if (currentSessionIdRef.current === sessionId) handleNewChat()
  }

  const handleDeleteAllChats = async () => {
    const results = await Promise.all(chats.map(chat => deleteSession(chat.session_id)))

    const deletedIds = new Set(chats.filter((_, i) => results[i]).map(c => c.session_id))
    const anyFailed = results.some(ok => !ok)

    setChats(prev => prev.filter(chat => !deletedIds.has(chat.session_id)))

    if (currentSessionIdRef.current && deletedIds.has(currentSessionIdRef.current)) {
      handleNewChat()
    }

    if (anyFailed) {
      throw new Error("Some sessions could not be deleted")
    }
  }

  const handleRenameChat = async (sessionId: string, newTitle: string) => {
    const ok = await renameSession(sessionId, newTitle)
    if (!ok) {
      console.error(`Failed to rename session ${sessionId}`)
      return
    }
    setChats(prev => prev.map(c =>
      c.session_id === sessionId ? { ...c, title: newTitle } : c
    ))
    if (currentSessionIdRef.current === sessionId) setCurrentFileName(newTitle)
  }

  // Upload
  const handleFileUpload = async (fileInput: File) => {
    closeChat()
    // Client-side validation
    const validation = await validatePdf(fileInput)
    if (!validation.ok) {
      toast.error("Invalid file", { description: validation.error })
      return
    }

    // 1. Submit immediately
    const session_id = await submitEvaluation(fileInput, msg =>
      toast.error("Upload failed", { description: msg })
    )
    if (!session_id) return

    // 2. Add to sidebar with status: "processing"
    const pendingChat: Chat = {
      session_id,
      title: fileInput.name,
      findings: [],
      status: "processing",
      latestTimestamp: new Date().toISOString(),
    }
    setChats(prev => [pendingChat, ...prev])

    // 3. Switch main view immediately — user sees the PDF while evaluation runs
    replaceFile(fileInput)
    setFindings([])
    setFindingsLoading(true)
    selectSession(session_id)
    setCurrentFileName(fileInput.name)
    setPage("chat")
    setMobileTab("document")

    // 4. Poll in the background
    trackEvaluation(session_id)
  }

  const handleConfirmCancel = async (sessionId: string) => {
    const result = await cancelEvaluation(sessionId)

    if (result === "cancelled") {
      setChats(prev =>
        sortChatsByLatest(prev.map(c => c.session_id === sessionId ? { ...c, status: "cancelled" } : c))
      )
      if (currentSessionIdRef.current === sessionId) setFindingsLoading(false)
      toast.info("Analysis cancelled")
    } else if (result === "finished") {
      toast.info("Already finished", { description: "This analysis completed before it could be cancelled." })
    } else {
      toast.error("Couldn't cancel the analysis", { description: "Please try again." })
    }
  }

  const handleRerunChat = async (chat: Chat) => {
    const result = await rerunEvaluation(chat.session_id)

    if (result === "busy") {
      toast.info("Still stopping", { description: "The cancelled run is wrapping up. Try again in a moment." })
      return
    }
    if (result === "error") {
      toast.error("Couldn't re-run the analysis", { description: "Please try again." })
      return
    }

    setChats(prev =>
      sortChatsByLatest(
        prev.map(c =>
          c.session_id === chat.session_id
            ? { ...c, status: "processing", findings: [], latestTimestamp: new Date().toISOString() }
            : c
        )
      )
    )
    if (currentSessionIdRef.current === chat.session_id) {
      setFindings([])
      setFindingsLoading(true) // also disables the chatbot input until findings land
    }
    trackEvaluation(chat.session_id)
    toast.info("Re-running analysis")
  }

  const handleLogout = () => {
    clearAuth()
    onLogout()
  }

  const currentChat = chats.find(c => c.session_id === currentSessionId)

  const { progress, events: progressEvents } = useEvaluationProgress(
    currentSessionId,
    currentChat?.status === "processing",
  )

  const mobileTitle =
    page === "account" ? "Account"
    : page === "report" ? "Assessment report"
    : file ? currentFileName : "Cheshire"

  // Shared props for the document viewer (desktop panel and mobile tab)
  const documentPreview = (
    <DocumentPreview
      src={file as File | string}
      findings={findings}
      fileName={currentFileName}
      findingsLoading={findingsLoading}
      chatOpen={chatOpen}
      // On mobile the chat lives in its own tab, so the toggle button is hidden
      onToggleChat={isMobile ? undefined : toggleChat}
      onCancelAnalysis={currentChat?.status === "processing" ? () => setChatToCancel(currentChat) : undefined}
      onRerunAnalysis={currentChat?.status === "cancelled" ? () => handleRerunChat(currentChat) : undefined}
      progress={progress}
      progressEvents={progressEvents}
    />
  )

  const chatbot = currentSessionId ? (
    <Chatbot
      key={currentSessionId}
      findings={findings}
      sessionId={currentSessionId}
      username={user.user_id}
      profileImage={profileImage}
      onOpenSettings={() => setSettingsOpen(true)}
      onActivity={() => touchChat(currentSessionId)}
      evaluationPending={findingsLoading}
    />
  ) : null

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <SidebarProvider>

      <ChatPage
        onNewChat={handleNewChat}
        chats={chats}
        isLoading={chatsLoading}
        onSelectChat={handleSelectChat}
        onGoAccount={() => setPage("account")}
        profileImage={profileImage || "/User.png"}
        userName={user.full_name ?? user.username ?? user.email}
        onDeleteChat={handleDeleteChat}
        onRenameChat={handleRenameChat}
        onLogout={handleLogout}
        onOpenSettings={() => setSettingsOpen(true)}
        onCancelChat={(chat) => setChatToCancel(chat)}
        onRerunChat={handleRerunChat}
        onOpenReport={handleOpenReport}
      />

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        chats={chats}
        onDeleteAllChats={handleDeleteAllChats}
      />

      <CancelEvaluationDialog
        chat={chatToCancel}
        onClose={() => setChatToCancel(null)}
        onConfirm={handleConfirmCancel}
      />

      {/* Desktop: floating trigger next to the sidebar */}
      <SidebarTrigger className="hidden md:inline-flex" />

      <SidebarInset className="h-dvh min-w-0 overflow-hidden md:h-auto">
        {/* Mobile top bar: sidebar toggle + current title */}
        <header className="flex h-12 shrink-0 items-center gap-2 border-b bg-background px-2 md:hidden">
          <SidebarTrigger />
          <span className="min-w-0 flex-1 truncate text-sm font-medium">{mobileTitle}</span>
        </header>

        {page === "account" ? (
          <div className="min-h-0 flex-1 overflow-hidden md:h-dvh md:flex-none">
            <Account
              setProfileImage={setProfileImage}
              user={user}
              chats={chats}
              onSelectChat={handleSelectChat}
              onClose={() => setPage("chat")}
            />
          </div>
        ) : page === "report" && currentSessionId ? (
          <div className="min-h-0 flex-1 overflow-hidden md:h-dvh md:flex-none">
            <ReportPage
              key={currentSessionId}
              sessionId={currentSessionId}
              documentName={currentFileName}
              findings={findings}
              loading={findingsLoading}
              user={user}
              fallbackAssessedAt={currentChat?.latestTimestamp ?? null}
              onClose={() => setPage("chat")}
            />
          </div>
        ) : (
          <main
            className={cn(
              "min-h-0 w-full min-w-0 flex-1 overflow-hidden md:h-dvh md:flex-none",
              !file ? "p-4 md:p-8" : "p-0"
            )}
          >
            {!file ? (
              <div className="h-full overflow-y-auto">
                <div className="flex min-h-full flex-col items-center justify-center gap-10 py-4 md:gap-14">
                  <motion.section
                    initial={{ opacity: 0, y: 14 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.35, ease: "easeOut" }}
                    className="flex w-full max-w-3xl flex-col items-center text-center"
                  >
                    <h1 className="text-3xl font-bold tracking-tight text-slate-950 dark:text-slate-50 sm:text-4xl md:text-5xl">
                      Hi, {user.full_name ?? user.username ?? ""}!
                    </h1>

                    <Card className="mt-4 w-full max-w-3xl rounded-2xl border border-slate-200 shadow-sm">
                      <CardContent className="space-y-4 p-2 text-center">
                        <p className="text-center text-base text-muted-foreground md:text-lg">
                          Welcome to Cheshire. Please upload a PDF document to start the evaluation.
                        </p>

                        <CardAction className="flex w-full items-center justify-center">
                          <Button
                            asChild
                            className="mx-auto block w-40"
                          >
                            <label className="flex cursor-pointer items-center justify-center gap-2">
                              <Upload className="h-4 w-4" />
                              Upload
                              <input
                                type="file"
                                accept=".pdf"
                                className="hidden"
                                onChange={(e) => {
                                  const f = e.target.files?.[0]
                                  if (f) handleFileUpload(f)
                                  e.target.value = ""
                                }}
                              />
                            </label>
                          </Button>
                        </CardAction>
                      </CardContent>
                    </Card>
                  </motion.section>

                  <motion.section
                    initial={{ opacity: 0, y: 18 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.45, delay: 0.08, ease: "easeOut" }}
                    className="flex w-full max-w-6xl flex-col items-center justify-center gap-8 md:flex-row md:gap-10"
                  >
                    <div className="flex flex-col items-center gap-6 md:flex-row md:gap-8">
                      <img
                        src="/cheshire-black.png"
                        alt="Cheshire Logo"
                        className="h-32 w-32 object-contain dark:invert md:h-52 md:w-52"
                      />

                      <div className="max-w-md text-center md:text-left">
                        <h2 className="mb-2 text-xl font-bold text-slate-800 dark:text-slate-100">
                          About Cheshire
                        </h2>
                        <p className="text-sm leading-relaxed text-muted-foreground md:text-justify md:text-base">
                          Cheshire is an assessment tool designed to identify vulnerabilities
                          in your Technical Document Specification (TDS) using AI analysis.
                          It streamlines the review process by highlighting potential security
                          gaps and ensuring your documentation adheres to industry standards.
                        </p>
                      </div>
                    </div>

                    <div className="hidden h-56 w-px bg-slate-100 md:block" />

                    <div className="w-full max-w-sm">
                      <h3 className="mb-4 text-center text-lg font-semibold uppercase tracking-wider text-slate-400 md:mb-6 md:text-left">
                        Features
                      </h3>

                      <div className="grid gap-5 md:gap-6">
                        {[
                          ["01", "Document Review", "A preview of your uploaded technical document."],
                          ["02", "Document Findings", "Automatically find security risks and get clear suggestions on how to fix them."],
                          ["03", "Chatbot", "Discuss findings directly with the AI."],
                        ].map(([number, title, description]) => (
                          <div key={number} className="flex gap-4">
                            <div className="font-bold text-slate-400">{number}</div>
                            <div>
                              <h4 className="font-semibold text-slate-800 dark:text-slate-100">{title}</h4>
                              <p className="text-sm text-muted-foreground md:text-base">{description}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </motion.section>
                </div>
              </div>
            ) : isMobile ? (
              // ── Mobile: Document / Chat tabs (both stay mounted to keep state) ──
              <Card className="size-full min-w-0 gap-0 overflow-hidden rounded-none border-0 py-0 shadow-none ring-0">
                <div role="tablist" className="flex shrink-0 border-b bg-background">
                  {MOBILE_TABS.map(({ id, label, icon: Icon }) => (
                    <button
                      key={id}
                      type="button"
                      role="tab"
                      aria-selected={mobileTab === id}
                      onClick={() => setMobileTab(id)}
                      className={cn(
                        "flex min-h-11 flex-1 items-center justify-center gap-2 border-b-2 px-4 text-sm font-medium transition-colors",
                        mobileTab === id
                          ? "border-primary text-foreground"
                          : "border-transparent text-muted-foreground hover:text-foreground"
                      )}
                    >
                      <Icon className="size-4" />
                      {label}
                    </button>
                  ))}
                </div>

                <div className={cn("min-h-0 flex-1", mobileTab !== "document" && "hidden")}>
                  <CardContent className="flex size-full min-w-0 flex-col gap-3 overflow-hidden px-2 pb-2 pt-2">
                    {documentPreview}
                  </CardContent>
                </div>

                <div className={cn("min-h-0 flex-1", mobileTab !== "chat" && "hidden")}>
                  {chatbot}
                </div>
              </Card>
            ) : (
              // ── Desktop: resizable document | chat panels ──
              <Card className="size-full min-w-0 overflow-hidden shadow-none">
                <ResizablePanelGroup
                  orientation="horizontal"
                  className="h-full w-full min-w-0 overflow-hidden"
                >
                  <ResizablePanel id="doc" defaultSize="100%" minSize="30%" className="min-w-0 overflow-hidden">
                    <CardContent className="flex size-full min-w-0 flex-col gap-3 overflow-hidden">
                      {documentPreview}
                    </CardContent>
                  </ResizablePanel>

                  <ResizableHandle
                    withHandle
                    disabled={!chatOpen || settingsOpen}
                    className={!chatOpen || settingsOpen ? "pointer-events-none opacity-0" : ""}
                  />

                  <ResizablePanel
                    id="chat"
                    panelRef={chatPanelRef}
                    collapsible
                    collapsedSize="0%"
                    defaultSize="0%"
                    minSize="40%"
                    onResize={() => setChatOpen(!chatPanelRef.current?.isCollapsed())}
                    className="min-w-0 overflow-hidden"
                  >
                    {chatbot}
                  </ResizablePanel>
                </ResizablePanelGroup>
              </Card>
            )}
          </main>
        )}
      </SidebarInset>
    </SidebarProvider>
  )
}