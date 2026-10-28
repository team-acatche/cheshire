// src/components/ui/login.tsx
import React, { useState } from "react"
import { motion, useReducedMotion } from "framer-motion"
import { Eye, EyeOff, OctagonAlert, FileWarning } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { loginRequest, type AuthUser } from "@/lib/auth"

interface LoginFormProps extends React.ComponentProps<"div"> {
  onLogin: (user: AuthUser) => void
}

// Same severity colors the PDF viewer uses for its highlights
const RED = "220 38 38"
const YELLOW = "234 179 8"
const BLUE = "0 51 178"

function Line({ w, mark }: { w: string; mark?: string }) {
  return (
    <div
      className="h-1.5 rounded-full bg-zinc-200"
      style={
        mark
          ? {
              width: w,
              background: `rgb(${mark} / 0.22)`,
              boxShadow: `0 2px 0 0 rgb(${mark} / 0.9)`,
            }
          : { width: w }
      }
    />
  )
}

/** A tilted mock PDF page with highlights, echoing what the app does to real documents. */
function DocumentPeek() {
  const reduce = useReducedMotion()
  const float = (delay: number) =>
    reduce
      ? {}
      : {
          animate: { y: [0, -6, 0] },
          transition: { duration: 5, repeat: Infinity, ease: "easeInOut" as const, delay },
        }

  return (
    <div className="relative mt-10 w-64">
      <div className="-rotate-3 rounded-md bg-white p-5 shadow-2xl shadow-black/30">
        <div className="mb-4 h-2.5 w-24 rounded-full bg-zinc-800" />
        <div className="space-y-2.5">
          <Line w="100%" />
          <Line w="92%" />
          <Line w="78%" mark={RED} />
          <Line w="96%" />
          <Line w="60%" />
          <div className="h-2" />
          <Line w="100%" />
          <Line w="85%" mark={YELLOW} />
          <Line w="94%" />
          <Line w="70%" />
          <div className="h-2" />
          <Line w="98%" />
          <Line w="88%" mark={BLUE} />
          <Line w="52%" />
        </div>
      </div>

      <motion.div
        {...float(0)}
        className="absolute -right-6 top-14 flex items-center gap-1.5 rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold text-red-600 shadow-lg"
      >
        <OctagonAlert className="size-3.5" />
        Major · p. 4
      </motion.div>

      <motion.div
        {...float(1.4)}
        className="absolute -left-8 bottom-10 flex items-center gap-1.5 rounded-full bg-white px-2.5 py-1 text-[11px] font-semibold text-yellow-700 shadow-lg"
      >
        <FileWarning className="size-3.5" />
        Missing section
      </motion.div>
    </div>
  )
}

/** The grin. A thin crescent that sits low in the panel, half out of frame. */
function Grin({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 400 120"
      fill="none"
      aria-hidden
      className={cn("pointer-events-none absolute", className)}
    >
      <path
        d="M10 20 C 90 130, 310 130, 390 20 C 320 82, 80 82, 10 20 Z"
        fill="white"
        fillOpacity={0.12}
      />
    </svg>
  )
}

export function LoginForm({ className, onLogin, ...props }: LoginFormProps) {
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    const data = new FormData(e.currentTarget)
    const email = data.get("email") as string
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
    <div className={cn("flex flex-col", className)} {...props}>
      <Card className="overflow-hidden p-0 shadow-xl ring-1 ring-foreground/10">
        <CardContent className="grid p-0 md:grid-cols-[1fr_1.05fr]">
          {/* ── Form ─────────────────────────────────────────────── */}
          <form
            className="flex flex-col justify-center px-6 py-10 md:px-12 md:py-16"
            onSubmit={handleSubmit}
          >
            <FieldGroup className="gap-5">
              <div className="space-y-2">
                <img
                  src="/cheshire-black.png"
                  alt=""
                  className="mb-4 size-9 object-contain dark:invert md:hidden"
                />
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
                  Cheshire
                </p>
                <h1 className="text-3xl font-semibold tracking-tight">Welcome back.</h1>
                <p className="text-sm text-muted-foreground">
                  Sign in with your Cheshire account.
                </p>
              </div>

              {error && (
                <div
                  role="alert"
                  className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
                >
                  {error}
                </div>
              )}

              <Field className="gap-2">
                <FieldLabel htmlFor="email">Email</FieldLabel>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="username"
                  placeholder="name@example.com"
                  required
                  autoFocus
                  disabled={loading}
                  aria-invalid={!!error}
                />
              </Field>

              <Field className="gap-2">
                <FieldLabel htmlFor="password">Password</FieldLabel>
                <div className="relative">
                  <Input
                    id="password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    disabled={loading}
                    aria-invalid={!!error}
                    className="pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    disabled={loading}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    aria-pressed={showPassword}
                    className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-muted-foreground transition-colors hover:text-foreground focus-visible:text-foreground focus-visible:outline-none disabled:opacity-50"
                  >
                    {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
              </Field>

              <Button type="submit" className="mt-1 w-full" disabled={loading}>
                {loading ? (
                  <>
                    <Spinner />
                    Signing in
                  </>
                ) : (
                  "Sign in"
                )}
              </Button>
            </FieldGroup>
          </form>

          {/* ── Brand panel ──────────────────────────────────────── */}
          <div
            className="relative hidden overflow-hidden md:flex md:flex-col md:items-center md:justify-center md:px-10 md:py-14"
            style={{
              backgroundImage:
                "linear-gradient(150deg, var(--mb-grad-from), var(--mb-grad-to))",
            }}
          >
            {/* faint dot grid */}
            <div
              aria-hidden
              className="absolute inset-0 opacity-[0.18]"
              style={{
                backgroundImage:
                  "radial-gradient(circle, white 1px, transparent 1px)",
                backgroundSize: "22px 22px",
                maskImage:
                  "radial-gradient(ellipse at 30% 20%, black 20%, transparent 75%)",
                WebkitMaskImage:
                  "radial-gradient(ellipse at 30% 20%, black 20%, transparent 75%)",
              }}
            />

            <Grin className="-bottom-6 -left-10 w-[130%] max-w-none" />

            <div className="relative z-10 flex flex-col items-center text-center text-white">
              <img
                src="/cheshire-black.png"
                alt="Cheshire logo"
                className="size-14 object-contain invert"
              />
              <h2 className="mt-4 text-xl font-semibold tracking-tight">
                Every gap, highlighted.
              </h2>
              <p className="mt-1.5 max-w-60 text-sm leading-relaxed text-white/75">
                Upload a design document and see exactly where it falls short.
              </p>

              <DocumentPeek />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}