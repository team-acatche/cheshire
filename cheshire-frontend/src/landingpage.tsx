import { LoginForm } from "@/components/ui/login"
import type { AuthUser } from "@/lib/auth"

interface LandingPageProps {
  onLogin: (user: AuthUser) => void
}

export default function LandingPage({ onLogin }: LandingPageProps) {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center bg-muted p-6 md:p-10">
      <div className="w-full max-w-sm md:max-w-4xl">
        <LoginForm onLogin={onLogin} />
      </div>
    </div>
  )
}
