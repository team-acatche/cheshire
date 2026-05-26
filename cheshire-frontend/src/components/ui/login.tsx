// src/components/ui/login.tsx
import React, { useState } from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { loginRequest, type AuthUser } from "@/lib/auth"

interface LoginFormProps extends React.ComponentProps<"div"> {
  onLogin: (user: AuthUser) => void
}

export function LoginForm({ className, onLogin, ...props }: LoginFormProps) {
  const [showPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    const data = new FormData(e.currentTarget)
    const email    = data.get("email")    as string
    const password = data.get("password") as string

    try {
      const user = await loginRequest(email, password)
      onLogin(user)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={cn("flex flex-col gap-6", className)} {...props}>
      <Card className="overflow-hidden p-0">
        <CardContent className="grid p-0 md:grid-cols-2">
          <form className="p-6 md:p-8" onSubmit={handleSubmit}>
            <FieldGroup>
              <div className="flex flex-col items-center gap-2 text-center">
                <h1 className="text-2xl font-bold">Welcome to Cheshire!</h1>
                <p className="text-balance text-muted-foreground">
                  Login using your Active Directory (AD) credentials
                </p>
              </div>

              {error && (
                <div className="rounded-md bg-destructive/10 border border-destructive/30 px-3 py-2 text-sm text-destructive">
                  {error}
                </div>
              )}

              <Field>
                <FieldLabel htmlFor="email">Email</FieldLabel>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  placeholder="name@example.com"
                  required
                  disabled={loading}
                />
              </Field>

              <Field>
                <div className="flex items-center">
                  <FieldLabel htmlFor="password">Password</FieldLabel>
                </div>
                <div className="relative">
                  <Input
                    id="password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    required
                    disabled={loading}
                  />
                  
                </div>
              </Field>

              <Field>
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading ? "Signing in…" : "Login"}
                </Button>
              </Field>
            </FieldGroup>
          </form>

          <div className="relative hidden bg-card md:flex md:items-center md:justify-center border-l">
            <img
              src="/cheshire-black.png"
              alt="Cheshire Logo"
              className="w-60 h-60 object-contain dark:invert"
            />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}