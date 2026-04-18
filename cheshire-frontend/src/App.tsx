import { useState, useEffect } from "react"
import { Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
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

// ─── API helpers ──────────────────────────────────────────────────────────────

async function fetchSessions(): Promise<Chat[]> {
  // GET /api/v1/  — returns sessions for the authenticated user
  return authFetch("/api/v1/")
    .then(r => (r.ok ? r.json() : []))
    .catch(() => [])
}

// ─── App ──────────────────────────────────────────────────────────────────────

interface AppProps {
  user: AuthUser
  onLogout: () => void
}

export default function App({ user, onLogout }: AppProps) {
  const [file, setFile]                     = useState<File | string | null>(null)
  const [findings, setFindings]             = useState<VulnerabilityFinding[]>([])
  const [chats, setChats]                   = useState<Chat[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [isProcessing, setIsProcessing]     = useState(false)
  const [currentFileName, setCurrentFileName] = useState<string>("document.pdf")
  const [page, setPage]                     = useState<"chat" | "account">("chat")

  // Load sessions on mount
  useEffect(() => {
    fetchSessions().then(sessions =>
      setChats(
        // Backend Session has session_id + title; Chat also needs a findings placeholder
        sessions.map((s: any) => ({
          session_id: s.session_id,
          title: s.title,
          findings: [],
        }))
      )
    )
  }, [])

  const handleNewChat = () => {
    setFindings([])
    setPage("chat")
    setCurrentSessionId(null)
    setPage("chat")
  }

  const handleSelectChat = async (chat: Chat) => {
    // Fetch the stored PDF as an object URL so DocumentPreview can render it
    const docUrl = `/api/v1/${chat.session_id}/document`
    // Use a string URL with authFetch under the hood via DocumentPreview's fetch
    // We pass the URL directly; the browser will use the cached JWT cookie alternative —
    // instead let's fetch it properly and create a blob URL.
    const blob = await authFetch(docUrl)
      .then(r => (r.ok ? r.blob() : null))
      .catch(() => null)

    const objectUrl = blob ? URL.createObjectURL(blob) : null

    const results = await getSessionResults(chat.session_id)

    setFile(objectUrl)
    setFindings(results)
    setCurrentSessionId(chat.session_id)
    setCurrentFileName(chat.title)
    setPage("chat")
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
        profileImage={`/User.png`}
        userName={user.full_name ?? user.username ?? user.email}
        onDeleteChat={(sessionId) => {
          setChats(prev => prev.filter(c => c.session_id !== sessionId))
          if (currentSessionId == sessionId) handleNewChat()
          // TODO: call DELETE /api/v1/{sessionId} when backend endpoint exists
        }}
        onRenameChat={(sessionId, newTitle) => {
          setChats(prev => prev.map (c =>
            c.session_id === sessionId ? {...c, title: newTitle} : c
          ))
          // TODO: call PATCH /api/v1/{sessionId} when backend endpoint exists
        }}
      />

      <SidebarTrigger />

      <SidebarInset>
        {page === "account" ? (
          <Account
            user={user}
            chats={chats}
            onLogout={handleLogout}
          />
        ) : (
          <main className="grid grid-cols-4 place-items-center h-dvh overflow-hidden">
            <Card className={`${!file ? "col-span-full" : "col-span-full size-full"} mt-2 shadow-none`}>
              {isProcessing ? (
                <CardContent className="col-span-full h-full flex items-center justify-center">
                  <LoadingPage />
                </CardContent>
              ) : !file ? (
                <CardContent className="size-full space-y-6 text-center">
                  <div className="space-y-2">
                    <h1 className="text-3xl font-bold tracking-tight">
                      Hi, {user.full_name ?? user.username ?? ""}!
                    </h1>

                    <p className="text-muted-foreground text-sm">
                      Welcome to Cheshire. Please upload a document to evaluate.
                    </p>
                  </div>

                  <CardAction className="flex justify-center m-auto">
                    <Button asChild className="w-40">
                      <label className="cursor-pointer inline-flex items-center gap-2">
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
                            try {
                              const response = await evaluateDocument(fileInput)
                              if (response === null) {
                                alert("Failed to evaluate document.")
                                return
                              }

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
                            } finally {
                              setIsProcessing(false)
                            }
                          }}
                        />
                      </label>
                    </Button>
                  </CardAction>
                </CardContent>
              ) : (
                <ResizablePanelGroup orientation="horizontal" className="h-full">
                  <ResizablePanel defaultSize={75} minSize={30}>
                    <CardContent className="flex flex-col gap-3 size-full overflow-hidden">
                      <DocumentPreview
                        src={file}
                        findings={findings}
                        fileName={currentFileName}
                      />
                    </CardContent>
                  </ResizablePanel>

                  <ResizableHandle withHandle />

                  <ResizablePanel defaultSize={25} minSize={15}>
                    {currentSessionId && (
                      <Chatbot
                        key={currentSessionId}
                        findings={findings}
                        sessionId={currentSessionId}
                        username={user.user_id}
                      />
                    )}
                  </ResizablePanel>
                </ResizablePanelGroup>
              )}
            </Card>
          </main>
        )}
      </SidebarInset>

    </SidebarProvider>
  )
}
