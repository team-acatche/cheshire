import { useState, useEffect } from "react"
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
  evaluateDocument,
  getSessionResults,
} from "./lib/helpers/evaluate_document"
import { authFetch, type AuthUser, clearAuth } from "./lib/auth"
import type { VulnerabilityFinding } from "./types/VulnerabilityFinding"
import { Chatbot } from "./components/chatbot"
import ChatPage from "./ChatPage"
import type { Chat } from "./ChatPage"
import { LoadingPage } from "./components/ui/loadingpage"
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

// ─── App ──────────────────────────────────────────────────────────────────────

interface AppProps {
  user: AuthUser
  onLogout: () => void
}

export default function App({ user, onLogout }: AppProps) {
  const [file, setFile] = useState<File | string | null>(null)
  const [findings, setFindings] = useState<VulnerabilityFinding[]>([])
  const [chats, setChats] = useState<Chat[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [processingStatus, setProcessingStatus] = useState<string>("Processing...")
  const [currentFileName, setCurrentFileName] = useState<string>("document.pdf");
  const [page, setPage] = useState<"chat" | "account">("chat")
  const [settingsOpen, setSettingsOpen] = useState(false)

  const [profileImage, setProfileImage] = useState(
    user.avatar_uri ? `/api/v1/${user.avatar_uri}` : "/api/v1/avatars/default.png"
  )

  // Load sessions on mount
  useEffect(() => {
    const loadSessions = async () => {
      const sessions = await fetchSessions()

      const chatsWithTimestamps = await Promise.all(
        sessions.map(async (s: any) => {
          const latestTimestamp = await fetchSessionTimestamp(s.session_id)

          return {
            session_id: s.session_id,
            title: s.title,
            findings: [],
            latestTimestamp,
          }
        })
      )

      chatsWithTimestamps.sort((a, b) => {
        const timeA = a.latestTimestamp
          ? new Date(a.latestTimestamp).getTime()
          : 0

        const timeB = b.latestTimestamp
          ? new Date(b.latestTimestamp).getTime()
          : 0

        return timeB - timeA
      })

      setChats(
        chatsWithTimestamps.map(({ latestTimestamp, ...chat }) => chat)
      )
    }

    loadSessions()
  }, [])

  const handleNewChat = () => {
    setFindings([])
    setPage("chat")
    setCurrentSessionId(null)
    setFile(null)
  }

  const handleSelectChat = async (chat: Chat) => {
    setIsProcessing(true)
    setProcessingStatus("Loading session...")
    setPage("chat")

    try {
      const docUrl = `/api/v1/${chat.session_id}/document`

      const [blob, results] = await Promise.all([
        authFetch(docUrl).then(r => (r.ok ? r.blob() : null)).catch(() => null),
        getSessionResults(chat.session_id),
      ])

      const objectUrl = blob ? URL.createObjectURL(blob) : null

      setFile(objectUrl)
      setFindings(results)
      setCurrentSessionId(chat.session_id)
      setCurrentFileName(chat.title)
    } finally {
      setIsProcessing(false)
    }
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

  // Delete ALL sessions sequentially and reset UI state
  const handleDeleteAllChats = async () => {
    const results = await Promise.allSettled(
      chats.map(chat => deleteSession(chat.session_id))
    )

    // Filter out only the sessions that were successfully deleted
    const deletedIds = new Set(
      chats
        .filter((_, i) => results[i].status === "fulfilled" && (results[i] as PromiseFulfilledResult<boolean>).value)
        .map(c => c.session_id)
    )

    const anyFailed = results.some(
      (r, i) => r.status === "rejected" || !(r as PromiseFulfilledResult<boolean>).value
    )

    setChats(prev => prev.filter(c => !deletedIds.has(c.session_id)))

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

  const handleLogout = () => {
    clearAuth()
    onLogout()
  }

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
          {isProcessing ? (
            <div className="flex h-full items-center justify-center">
              <Card className="w-full max-w-sm rounded-2xl border border-slate-200 shadow-sm">
                <CardContent className="flex flex-col items-center justify-center gap-3 p-6">
                  <LoadingPage />
                  <p className="text-sm text-muted-foreground text-center animate-pulse">
                    {processingStatus}
                  </p>
                </CardContent>
              </Card>
            </div>
          ) : !file ? (
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
                            onChange={async (e) => {
                              const fileInput = e.target.files?.[0]
                              if (!fileInput) return

                              if (fileInput.type !== "application/pdf") {
                                alert("Only PDF files are supported.")
                                return
                              }

                              setIsProcessing(true)
                              setProcessingStatus("Uploading document...")


                              try {
                                const response = await evaluateDocument(
                                  fileInput, 
                                  (event) => {
                                    if (event.type === "status" && event.message) {
                                      setProcessingStatus(event.message)
                                    }
                                  }
                                )

                                const newChat: Chat = {
                                  session_id: response.session_id,
                                  title: fileInput.name,
                                  findings: response.vulnerabilities,
                                }

                                setChats(prev => [newChat, ...prev])
                                setFile(fileInput)
                                setFindings(response.vulnerabilities)
                                setCurrentSessionId(response.session_id)
                                setCurrentFileName(fileInput.name)
                              } catch (err) {
                                alert(`Evaluation failed: ${err instanceof Error ? err.message: "Unknown error"}`)
                              } finally {
                                setIsProcessing(false)
                                setProcessingStatus("Processing...")
                              }
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