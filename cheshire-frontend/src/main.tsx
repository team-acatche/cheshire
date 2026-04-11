import { StrictMode, useState } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import LandingPage from "./landingpage.tsx"
import App from "./App.tsx"

function Root() {
  const [isLoggedIn, setIsLoggedIn] = useState(false)
  return isLoggedIn
    ? <App />
    : <LandingPage onLogin={() => setIsLoggedIn(true)} />
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>
)