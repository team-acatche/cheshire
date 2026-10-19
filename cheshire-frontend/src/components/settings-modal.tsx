import { useState, useEffect, useRef } from "react";
import { Wrench, CircleUserRound, X, Sun, Moon, Monitor } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/lib/theme";
import type { Chat } from "@/ChatPage";

import { cn } from "@/lib/utils";



function FieldLabel({ children } : { children: React.ReactNode }) {
    return <p className="text-sm font-medium leading-none text-foreground">{children}</p>
}

function SectionHeading({ children } : { children: React.ReactNode }) {
    return (
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {children}
        </p>
    )
}

function Divider() {
    return <hr className="border-border" />
}




// ─────────────────────────────────────────────────────────────────────────────
// Sidebar nav
// ─────────────────────────────────────────────────────────────────────────────

type Tab = "general" | "provider" | "account"

const NAV_ITEMS: { id: Tab, label: string, icon: React.ReactNode }[] = [
  { id: "general", label: "General",   icon: <Wrench className="size-3.75" /> },
  { id: "account",  label: "Account",  icon: <CircleUserRound className="size-3.75" /> },
]


function NavItem({
    icon, label, active, onClick,
}: {
    icon: React.ReactNode; label: string; active: boolean; onClick: () => void
}) {
    return (
        <button
            type="button"
            onClick={onClick}
            className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                active
                ? "bg-muted font-medium text-foreground"
                : "font-normal text-muted-foreground hover:bg-muted/50 hover:text-foreground"
            )}
        >
            {icon}
            {label}
        </button>
    )
}


// ─────────────────────────────────────────────────────────────────────────────
// Theme selector button group
// ─────────────────────────────────────────────────────────────────────────────

type ThemeOption = { value: "light" | "dark" | "system"; label: string; icon: React.ReactNode }

const THEME_OPTIONS: ThemeOption[] = [
  { value: "light",  label: "Light",  icon: <Sun  className="size-4" /> },
  { value: "dark",   label: "Dark",   icon: <Moon className="size-4" /> },
  { value: "system", label: "System", icon: <Monitor className="size-4" /> },
]

function ThemeSelector() {
  const { theme, setTheme } = useTheme()

  return (
    <div className="flex rounded-md border border-input overflow-hidden w-fit">
      {THEME_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => setTheme(opt.value)}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 text-sm transition-colors",
            theme === opt.value
              ? "bg-primary text-primary-foreground"
              : "bg-transparent text-muted-foreground hover:bg-muted hover:text-foreground",
            // borders between segments
            "not-first:border-l not-first:border-input"
          )}
        >
          {opt.icon}
          {opt.label}
        </button>
      ))}
    </div>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// General panel
// ─────────────────────────────────────────────────────────────────────────────

function GeneralPanel() {
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">General</h2>

      <Divider />

      <section className="space-y-4">
        <SectionHeading>Appearance</SectionHeading>

        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <FieldLabel>Theme</FieldLabel>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Choose between light, dark, or follow your system preference.
            </p>
          </div>
          <ThemeSelector />
        </div>
      </section>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab — Account
// ─────────────────────────────────────────────────────────────────────────────

function AccountPanel({
  onClose,
  chats,
  onDeleteAllChats,
}: {
  onClose: () => void
  chats: Chat[]
  onDeleteAllChats: () => Promise<void>
}) {
  const [confirm, setConfirm] = useState<null | "sessions">(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const handleDeleteAll = async () => {
    setDeleting(true)
    setDeleteError(null)
    try {
      await onDeleteAllChats()
      setConfirm(null)
      onClose()
    } catch {
      setDeleteError("Failed to delete some sessions. Please try again.")
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Account</h2>

      <Divider />

      <section className="space-y-3">
        <SectionHeading><span className="text-destructive">Danger Zone</span></SectionHeading>
        <p className="text-xs text-muted-foreground">These actions are permanent and cannot be undone.</p>

        {deleteError && (
          <div className="rounded-md bg-destructive/10 border border-destructive/30 px-3 py-2 text-sm text-destructive">
            {deleteError}
          </div>
        )}

        {/* Delete sessions */}
        <div className="flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3">
          <div>
            <p className="text-sm font-medium">Delete all sessions</p>
            <p className="text-xs text-muted-foreground">
              Remove all {chats.length} uploaded document{chats.length !== 1 ? "s" : ""} and their chat history.
            </p>
          </div>

          {confirm === "sessions" ? (
            <div className="flex shrink-0 items-center gap-2">
              <span className="text-xs text-muted-foreground">Are you sure?</span>
              <Button
                size="xs"
                variant="destructive"
                onClick={handleDeleteAll}
                disabled={deleting}
              >
                {deleting ? "Deleting…" : "Yes, delete all"}
              </Button>
              <Button
                size="xs"
                variant="outline"
                onClick={() => setConfirm(null)}
                disabled={deleting}
              >
                Cancel
              </Button>
            </div>
          ) : (
            <Button
              size="sm"
              variant="destructive"
              onClick={() => setConfirm("sessions")}
              disabled={chats.length === 0}
            >
              Delete
            </Button>
          )}
        </div>
      </section>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export interface SettingsModalProps {
  open: boolean
  onClose: () => void
  chats?: Chat[]
  onDeleteAllChats?: () => Promise<void>
}

export function SettingsModal({ open, onClose, chats = [], onDeleteAllChats }: SettingsModalProps) {
  const [activeTab,   setActiveTab]   = useState<Tab>("general")
  const modalRef  = useRef<HTMLDivElement>(null)

  /* Escape to close */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [onClose])


  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/25 backdrop-blur-[2px]"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
      aria-modal="true"
      role="dialog"
      aria-label="Settings"
    >
      <div
        ref={modalRef}
        className="relative flex h-162.5 max-h-[90vh] w-215 max-w-[96vw] overflow-hidden rounded-2xl bg-background shadow-2xl ring-1 ring-foreground/80"
      >
        {/* ── Left sidebar ─────────────────────────────────────────────── */}
        <div className="flex w-50 shrink-0 flex-col border-r border-border bg-muted/20 px-2 py-4">
          {/* Close button */}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close settings"
            className="mb-3 ml-1 flex size-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <X className="size-3.5" />
          </button>

          <nav className="flex flex-col gap-0.5">
            {NAV_ITEMS.map((item) => (
              <NavItem
                key={item.id}
                icon={item.icon}
                label={item.label}
                active={activeTab === item.id}
                onClick={() => setActiveTab(item.id)}
              />
            ))}
          </nav>
        </div>

        {/* ── Right content ─────────────────────────────────────────────── */}
        <div className="min-h-0 flex-1 overflow-y-auto p-6">
          {activeTab === "general" && <GeneralPanel />}
          {activeTab === "account"  && (
            <AccountPanel
              onClose={onClose}
              chats={chats}
              onDeleteAllChats={onDeleteAllChats ?? (async () => {})}
            />
          )}
        </div>
      </div>
    </div>
  )
}

export default SettingsModal