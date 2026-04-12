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
import { evaluateDocument } from "./lib/helpers/evaluate_document"
import type { VulnerabilityFinding } from "./types/VulnerabilityFinding"
import { Chatbot } from "./components/chatbot"
import ChatPage from "./ChatPage"
import { USERNAME } from "./globals"
import type { Chat } from "./ChatPage"
import { LoadingPage } from "./components/ui/loadingpage"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"
import Account from "./components/account"

async function getChats(username: string): Promise<Chat[]> {
  return await fetch(`/api/v1/${username}`)
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

export default function App() {
  const [file, setFile] = useState<File | string | null>(null)
  const [findings, setFindings] = useState<VulnerabilityFinding[]>([])
  const [chats, setChats] = useState<Chat[]>([])

  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [currentFileName, setCurrentFileName] = useState<string>("document.pdf");

  const [page, setPage] = useState<"chat" | "account">("chat")

  const [profileImage, setProfileImage] = useState(
    "User.png"
  )

  const [userName, setUserName] = useState("DELA CRUZ, JUAN")
  const [email, setEmail] = useState("delacruz.juan@metrobank.com.ph")

  useEffect(() => {
    const img = localStorage.getItem("profileImage")
    const name = localStorage.getItem("userName")
    const mail = localStorage.getItem("email")

    if (img) setProfileImage(img)
    if (name) setUserName(name)
    if (mail) setEmail(mail)
  }, [])

  useEffect(() => {
    localStorage.setItem("profileImage", profileImage)
    localStorage.setItem("userName", userName)
    localStorage.setItem("email", email)
  }, [profileImage, userName, email])

  
  useEffect(() => {
    getChats(USERNAME).then(setChats)
  }, [])

  const handleNewChat = () => {
    setFindings([])
    setPage("chat")
    setCurrentSessionId(null)
  }

  const handleSelectChat = async (chat: Chat) => {
    const url = `/api/v1/${USERNAME}/${chat.session_id}/document`;
    const findings: VulnerabilityFinding[] = await fetch(
      `/api/v1/${USERNAME}/${chat.session_id}/result`
    )
      .then(r => r.ok ? r.json() : [])
      .catch(() => []);
  
    setFile(url)
    setFindings(findings)
    setCurrentSessionId(chat.session_id)
    setCurrentFileName(chat.title);
  }

  return (
    <SidebarProvider>

      <ChatPage
        onNewChat={handleNewChat}
        chats={chats}
        onSelectChat={handleSelectChat}
        onGoAccount={() => setPage("account")}
        profileImage={profileImage}
        userName={userName}
      />

      <SidebarTrigger />

      <SidebarInset>
        {page === "account" ? (
          <Account
            profileImage={profileImage}
            setProfileImage={setProfileImage}
            userName={userName}
            setUserName={setUserName}
            email={email}
            setEmail={setEmail}
            chats={chats} //Connected
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

                              const newChat: Chat = {
                                session_id: response.session_id,
                                title: fileInput.name,
                                findings: response.vulnerabilities,
                              }

                              setChats((prev) => [newChat, ...prev])
                              setFile(fileInput)
                              setFindings(response.vulnerabilities)
                              setCurrentSessionId(response.session_id)
                              setCurrentFileName(fileInput.name)
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
                <ResizablePanelGroup orientation="horizontal" className="h-full">
                  <ResizablePanel defaultSize={75} minSize={30}>
                    <CardContent className="flex flex-col gap-3 size-full overflow-hidden">
                      {/* Pass the original file + findings separately — no burned-in highlights */}
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
                        username={USERNAME}
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