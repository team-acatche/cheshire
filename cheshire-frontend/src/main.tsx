import { StrictMode, useState } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import LandingPage from "./landingpage.tsx"
import App from "./App.tsx"
import { getStoredUser, type AuthUser } from "./lib/auth"

function Root() {
  // Restore session from localStorage so a page refresh doesn't log the user out.
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser())

  if (!user) {
    return <LandingPage onLogin={(u) => setUser(u)} />
  }

  return <App user={user} onLogout={() => setUser(null)} />
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>
)