import { useState, useEffect } from "react"
import { Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent } from "./components/ui/card"
import {
  SidebarProvider,
  SidebarTrigger,
  SidebarInset,
} from "./components/ui/sidebar"
import DocumentPreview from "./components/document-preview"
import { evaluateDocument, saveResult } from "./lib/helpers/evaluate_document"
import type { VulnerabilityFinding } from "./types/VulnerabilityFinding"
import { Chatbot } from "./components/chatbot"
import ChatPage from "./ChatPage"
import { USERNAME } from "./globals"
import type { Chat } from "./ChatPage"
import { LoadingPage } from "./components/ui/loadingpage"

async function getChats(username: string): Promise<Chat[]> {
  return await fetch(`/api/v1/${username}/chat`)
    .then(response => {
      if (!response.ok) {
        throw new Error(`Error getting chats: ${response.statusText}`);
      }
      return response.json() as Promise<Chat[]>
    })
    .catch(error => {
      console.error("Error getting chats:", error);
      return [];
    });
}

export function App() {
  const [file, setFile] = useState<File | string | null>(null)
  const [findings, setFindings] = useState<VulnerabilityFinding[]>([])
  const [chats, setChats] = useState<Chat[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)

  useEffect(() => {
    getChats(USERNAME).then(setChats)
  }, [])

  // Reset to home screen
  const handleNewChat = () => {
    setFile(null)
    setFindings([])
    setCurrentSessionId(null)
  }

  // Restore a previous session — point directly at the API URL, no blob fetch needed
  const handleSelectChat = (chat: Chat) => {
    const url = `/api/v1/${USERNAME}/evaluate/${chat.session_id}/result`;
    setFile(url)
    setFindings(chat.findings || [])
    setCurrentSessionId(chat.session_id)
  }

  return (
    <SidebarProvider>
      <ChatPage
        onNewChat={handleNewChat}
        chats={chats}
        onSelectChat={handleSelectChat}
      />

      <SidebarTrigger />
      <SidebarInset>
        <main className="grid grid-cols-4 place-items-center h-dvh overflow-hidden">

          <Card className={`${!file ? "col-span-full" : "col-span-3 size-full"} mt-2 shadow-none`}>
            {isProcessing ? (
              <CardContent className="col-span-full h-full flex items-center justify-center">
                <LoadingPage />
              </CardContent>
            ) : !file ? (
              <CardContent className="size-full space-y-6 text-center">
                <p className="font-bold text-xl">
                  Hi! Welcome to Cheshire. Please upload a document to evaluate.
                </p>

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
                          if (file !== null) return;

                          const fileInput = e.target.files?.[0];
                          if (!fileInput) return;

                          if (fileInput.type !== "application/pdf") {
                            alert("Only PDF files are supported.");
                            return;
                          }

                          setIsProcessing(true);
                          try {
                            const response = await evaluateDocument(fileInput);
                            if (response === null) {
                              alert("Failed to evaluate document.");
                              return;
                            }

                            // Save the original, unmodified PDF as the stored result.
                            // Highlights are now rendered as overlays — no pdf-lib mutation needed.
                            await saveResult(response.session_id, fileInput);

                            const newChat: Chat = {
                              session_id: response.session_id,
                              title: fileInput.name,
                              findings: response.vulnerabilities,
                            }

                            setChats((prev) => [newChat, ...prev])
                            setFile(fileInput)
                            setFindings(response.vulnerabilities)
                            setCurrentSessionId(response.session_id)
                          } finally {
                            setIsProcessing(false);
                          }
                        }}
                      />
                    </label>
                  </Button>
                </CardAction>
              </CardContent>
            ) : (
              <CardContent className="flex flex-col gap-3 size-full overflow-hidden">
                {/* Pass the original file + findings separately — no burned-in highlights */}
                <DocumentPreview src={file} findings={findings} />
              </CardContent>
            )}
          </Card>

          {file && currentSessionId && (
            <Chatbot
              key={currentSessionId}
              findings={findings}
              sessionId={currentSessionId}
              username={USERNAME}
            />
          )}
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

export default App