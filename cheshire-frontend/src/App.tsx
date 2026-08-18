import { useState, useEffect, useRef } from "react"
import { Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { motion } from "framer-motion"
import { Card, CardAction, CardContent } from "./components/ui/card"
import {
  SidebarProvider,
  SidebarTrigger,
  SidebarInset,
} from "./components/ui/sidebar"
import DocumentPreview from "./components/document-preview/DocumentPreview"
import {
  submitEvaluation,
  pollEvaluation,
  getSessionResults,
} from "./lib/helpers/evaluate_document"
import { authFetch, type AuthUser, clearAuth } from "./lib/auth"
import { sortChatsByLatest } from "@/lib/sortChatsByLatest"
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
import SettingsModal from "./components/settings-modal"

// ─── API helpers ──────────────────────────────────────────────────────────────

async function fetchSessions(): Promise<Chat[]> {
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

// ─── App ──────────────────────────────────────────────────────────────────────

interface AppProps {
  user: AuthUser
  onLogout: () => void
}

/**
 * Maps the backend status string to the frontend ChatStatus union.
 * "pending" and "processing" both show a loading spinner in the sidebar.
 */
function toFrontendStatus(backendStatus: string): ChatStatus {
  if (backendStatus === "done") return "done"
  if (backendStatus === "failed") return "failed"
  // "pending" | "processing" → both treated as "processing" in the UI
  return "processing"
}

export default function App({ user, onLogout }: AppProps) {
  const [file, setFile] = useState<File | string | null>(null)
  const [findings, setFindings] = useState<VulnerabilityFinding[]>([])
  const [findingsLoading, setFindingsLoading] = useState(false)
  const [chats, setChats] = useState<Chat[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [currentFileName, setCurrentFileName] = useState<string>("document.pdf")
  const [page, setPage] = useState<"chat" | "account">("chat")
  const [settingsOpen, setSettingsOpen] = useState(false)

  // Track active polling tasks so we can resume them after refresh
  const pollingRef = useRef<Set<string>>(new Set())

  const [profileImage, setProfileImage] = useState(
    user.avatar_uri ? `/api/v1/${user.avatar_uri}` : "/api/v1/avatars/default.png"
  )

  // ── Resume polling for any pending sessions after mount ───────────────────
  const resumePolling = (session_id: string) => {
    if (pollingRef.current.has(session_id)) return
    pollingRef.current.add(session_id)

    pollEvaluation(session_id).then(response => {
      pollingRef.current.delete(session_id)

      if (response === null) {
        setChats(prev =>
          prev.map(c => c.session_id === session_id ? { ...c, status: "failed" } : c)
        )
        setCurrentSessionId(current => {
          if (current === session_id) setFindingsLoading(false)
          return current
        })
        return
      }

      setChats(prev =>
        prev.map(c =>
          c.session_id === session_id
            ? { ...c, findings: response.vulnerabilities, status: "done" }
            : c
        )
      )

      // If user is still on this session, populate findings + fetch the blob
      setCurrentSessionId(current => {
        if (current === session_id) {
          setFindings(response.vulnerabilities)
          setFindingsLoading(false)
          // Fetch the actual document blob now that evaluation is done
          setFile((currentFile) => {
            if (currentFile && typeof currentFile !== "string") return currentFile
            fetchDocumentBlob(session_id).then((url) => {
              if (url) setFile(url)
            })
            return currentFile
          })
        }
        return current
      })
    })
  }

  // Load existing sessions on mount, then merge pending sessions
  useEffect(() => {
    const loadSessions = async () => {
      const rawSessions = await fetchSessions()

      const chatsWithTimestamps = await Promise.all(
        rawSessions.map(async (s: any) => {
          const latestTimestamp = await fetchSessionTimestamp(s.session_id)
          return {
            session_id: s.session_id,
            title: s.title,
            findings: [],
            status: toFrontendStatus(s.status ?? "done"),
            latestTimestamp,
          } satisfies Chat
        })
      )

      setChats(sortChatsByLatest(chatsWithTimestamps))

      //Resume polling for any sessions that isn't done/failed
      for (const chat of chatsWithTimestamps) {
        if (chat.status === "processing") {
          resumePolling(chat.session_id)
        }
      }
    }


    loadSessions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Sidebar helpers ───────────────────────────────────────────────────────

  const handleNewChat = () => {
    setFindings([])
    setFindingsLoading(false)
    setPage("chat")
    setCurrentSessionId(null)
    setFile(null)
  }

  const handleSelectChat = async (chat: Chat) => {
    setPage("chat")
    setCurrentSessionId(chat.session_id)
    setCurrentFileName(chat.title)

    if (chat.status === "processing") {
      setFindings([])
      setFindingsLoading(true)

      const blobUrl = await fetchDocumentBlob(chat.session_id)
      setFile(blobUrl)
      return
    }

    // Done or unknown status — load doc + results
    setFile(null)
    setFindings([])
    setFindingsLoading(true)

    try {
      const [blobUrl, results] = await Promise.all([
        fetchDocumentBlob(chat.session_id),
        getSessionResults(chat.session_id),
      ])
      setFile(blobUrl)
      setFindings(results)
    } finally {
      setFindingsLoading(false)
    }
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
    if (currentSessionId === sessionId) handleNewChat()
  }

  const handleDeleteAllChats = async () => {
    const results = await Promise.allSettled(
      chats.map(chat => deleteSession(chat.session_id))
    )

    const deletedIds = new Set(
      chats
        .filter((_, i) => results[i].status === "fulfilled" && (results[i] as PromiseFulfilledResult<boolean>).value)
        .map(c => c.session_id)
    )

    const anyFailed = results.some(
      (result, _) => result.status === "rejected" || !(result as PromiseFulfilledResult<boolean>).value
    )


    setChats(prev => prev.filter(chat => !deletedIds.has(chat.session_id)))

    if (currentSessionId && deletedIds.has(currentSessionId)) {
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
    if (currentSessionId === sessionId) setCurrentFileName(newTitle)
  }

  // Upload
  const handleFileUpload = async (fileInput: File) => {
    if (fileInput.type !== "application/pdf") {
      alert("Only PDF files are supported.")
      return
    }

    // 1. Submit immediately
    const session_id = await submitEvaluation(fileInput)
    if (!session_id) {
      alert("Failed to submit document for evaluation.")
      return
    }

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
    setFile(fileInput)
    setFindings([])
    setFindingsLoading(true)
    setCurrentSessionId(session_id)
    setCurrentFileName(fileInput.name)
    setPage("chat")

    // 5. Poll in the background
    pollingRef.current.add(session_id)
    pollEvaluation(session_id).then(response => {
      pollingRef.current.delete(session_id) 

      if (response === null) {
        setChats(prev =>
          prev.map(c => c.session_id === session_id ? { ...c, status: "failed" } : c)
        )
        setCurrentSessionId(current => {
          if (current === session_id) setFindingsLoading(false)
          return current
        })
        return
      }

      setChats(prev =>
        prev.map(c =>
          c.session_id === session_id
            ? { ...c, findings: response.vulnerabilities, status: "done" }
            : c
        )
      )

      setCurrentSessionId(current => {
        if (current === session_id) {
          setFindings(response.vulnerabilities)
          setFindingsLoading(false)
          // The File object is already in state from upload; no need to re-fetch blob
        }
        return current
      })
    })
  }

  const handleLogout = () => {
    clearAuth()
    onLogout()
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <SidebarProvider>

      <ChatPage
        onNewChat={handleNewChat}
        chats={chats}
        onSelectChat={handleSelectChat}
        onGoAccount={() => setPage("account")}
        profileImage={profileImage || "/User.png"}
        userName={user.full_name ?? user.username ?? user.email}
        onDeleteChat={handleDeleteChat}
        onRenameChat={handleRenameChat}
        onLogout={handleLogout}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        chats={chats}
        onDeleteAllChats={handleDeleteAllChats}
      />

      <SidebarTrigger />

      <SidebarInset className="min-w-0 overflow-hidden">
        {page === "account" ? (
          <Account
            setProfileImage={setProfileImage}
            user={user}
            chats={chats}
            onClose={() => setPage("chat")}
          />
        ) : (
          <main className={`h-dvh w-full min-w-0 overflow-hidden ${!file ? "p-8" : "p-0"}`}>
            {!file ? (
              <div className="flex h-full flex-col items-center justify-center gap-14">
                <motion.section
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.35, ease: "easeOut" }}
                  className="flex w-full max-w-3xl flex-col items-center text-center"
                >
                  <h1 className="text-5xl font-bold tracking-tight text-slate-950 dark:text-slate-50">
                    Hi, {user.full_name ?? user.username ?? ""}!
                  </h1>

                  <Card className="mt-4 w-full max-w-3xl rounded-2xl border border-slate-200 shadow-sm">
                    <CardContent className="space-y-4 p-2 text-center">
                      <p className="text-lg text-muted-foreground text-center">
                        Welcome to Cheshire. Please upload a PDF document to start the evaluation.
                      </p>

                      <CardAction className="w-full flex items-center justify-center">
                        <Button
                          asChild
                          className="w-40 mx-auto block"
                        >
                          <label className="flex items-center justify-center gap-2 cursor-pointer">
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
                  className="flex w-full max-w-6xl flex-col items-center justify-center gap-10 md:flex-row"
                >
                  <div className="flex flex-col items-center gap-8 md:flex-row">
                    <img
                      src="/cheshire-black.png"
                      alt="Cheshire Logo"
                      className="h-44 w-44 object-contain md:h-52 md:w-52 dark:invert"
                    />

                    <div className="max-w-md text-center md:text-left">
                      <h2 className="mb-2 text-xl font-bold text-slate-800 dark:text-slate-100">
                        About Cheshire
                      </h2>
                      <p className="text-base leading-relaxed text-muted-foreground md:text-justify">
                        Cheshire is an assessment tool designed to identify vulnerabilities
                        in your Technical Document Specification (TDS) using AI analysis.
                        It streamlines the review process by highlighting potential security
                        gaps and ensuring your documentation adheres to industry standards.
                      </p>
                    </div>
                  </div>

                  <div className="hidden h-56 w-px bg-slate-100 md:block" />

                  <div className="w-full max-w-sm">
                    <h3 className="mb-6 text-lg font-semibold uppercase tracking-wider text-slate-400">
                      Features
                    </h3>

                    <div className="grid gap-6">
                      {[
                        ["01", "Document Review", "A preview of your uploaded technical document."],
                        ["02", "Document Findings", "Automatically find security risks and get clear suggestions on how to fix them."],
                        ["03", "Chatbot", "Discuss findings directly with the AI."],
                      ].map(([number, title, description]) => (
                        <div key={number} className="flex gap-4">
                          <div className="font-bold text-slate-400">{number}</div>
                          <div>
                            <h4 className="font-semibold text-slate-800 dark:text-slate-100">{title}</h4>
                            <p className="text-base text-muted-foreground">{description}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </motion.section>
              </div>
            ) : (
              <Card className="size-full min-w-0 overflow-hidden shadow-none">
                <ResizablePanelGroup
                  orientation="horizontal"
                  className="h-full w-full min-w-0 overflow-hidden"
                >
                  <ResizablePanel defaultSize={60} minSize={30} className="min-w-0 overflow-hidden">
                    <CardContent className="flex size-full min-w-0 flex-col gap-3 overflow-hidden">
                      <DocumentPreview
                        src={file}
                        findings={findings}
                        fileName={currentFileName}
                        findingsLoading={findingsLoading}
                      />
                    </CardContent>
                  </ResizablePanel>

                  {!settingsOpen && <ResizableHandle withHandle />}

                  <ResizablePanel defaultSize={40} minSize={25} className="min-w-0 overflow-hidden">
                    {currentSessionId && (
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
                    )}
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