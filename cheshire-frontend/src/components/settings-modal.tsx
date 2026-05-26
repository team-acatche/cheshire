import { useState, useEffect, useRef } from "react";
import { Wrench, Server, CircleUserRound, X, ChevronDown, Check, Sun, Moon, Monitor } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useTheme } from "@/lib/theme";
import type { Chat } from "@/ChatPage";
import { authFetch } from "@/lib/auth";

import { cn } from "@/lib/utils";


// —————— Primitives ————————————————————————

function Toggle({
    checked,
    onChange,
    disabled = false,
}: {
    checked: boolean,
    onChange: (v: boolean) => void
    disabled?: boolean
}) {
    return (
        <button
            type="button"
            role="switch"
            aria-checked={checked}
            disabled={disabled}
            onClick={() => !disabled && onChange(!checked)}
            className={cn(
                "relative inline-flex h-[22px] w-10 shrink-0 cursor-pointer rounded-full border-2 border-transparent",
                "transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                checked && !disabled ? "bg-primary" : "bg-input",
                disabled && "cursor-not-allowed opacity-40"
            )}
        >
            <span
                className={cn(
                    "pointer-events-none inline-block h-[18px] w-[18px] transform rounded-full bg-white shadow-md ring-0 transition-transform duration-200",
                    checked ? "translate-x-[18px]" : "translate-x-0",
                )}
            />
        </button>
    )
}

function NativeSelect({
    value,
    onChange,
    options,
    disabled,

}: {
    value: string
    onChange: (v: string) => void
    options: { value: string; label: string }[]
    disabled?: boolean
}) {
    return (
        <div className="relative">
            <select
                value={value}
                onChange={(e) => onChange(e.target.value)}
                disabled={disabled}
                className={cn(
                    "h-9 w-full appearance-none rounded-md border border-input bg-transparent px-2.5 py-1 pr-8 text-sm shadow-xs",
                    "transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1",
                    "disabled:cursor-not-allowed disabled:opacity-50",
                )}
            >
                {options.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        </div>
    )
}

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

function SavedBadge({ visible }: { visible: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-1 text-xs font-medium text-green-700",
        "transition-opacity duration-300",
        visible ? "opacity-100" : "opacity-0 pointer-events-none",
      )}
    >
      <Check className="size-3" />
      Saved
    </span>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// Sidebar nav
// ─────────────────────────────────────────────────────────────────────────────

type Tab = "general" | "provider" | "account"

const NAV_ITEMS: { id: Tab, label: string, icon: React.ReactNode }[] = [
  { id: "general", label: "General",   icon: <Wrench className="size-[15px]" /> },
  { id: "provider", label: "Provider", icon: <Server className="size-[15px]" /> },
  { id: "account",  label: "Account",  icon: <CircleUserRound className="size-[15px]" /> },
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

function GeneralPanel({ onSaved }: { onSaved: () => void; onClose: () => void }) {
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">General</h2>

      <Divider />

      <section className="space-y-4">
        <SectionHeading>Appearance</SectionHeading>

        <div className="flex items-center justify-between">
          <div>
            <FieldLabel>Theme</FieldLabel>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Choose between light, dark, or follow your system preference.
            </p>
          </div>
          <ThemeSelector />
        </div>
      </section>

      <Divider />

      <div className="flex justify-end">
        <Button size="sm" onClick={onSaved}>
          Save changes
        </Button>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab — Provider
// ─────────────────────────────────────────────────────────────────────────────

type ProviderMode = "default" | "offline" | "serverless"

function ProviderCard({
  id,
  title,
  desc,
  mode,
  setMode,
  children,
}: {
  id: ProviderMode
  title: string
  desc: string
  mode: ProviderMode
  setMode: (mode: ProviderMode) => void
  children?: React.ReactNode
}) {
  const isActive = mode === id

  return (
    <div
      className={cn(
        "rounded-lg border p-4 transition-all duration-150",
        isActive
          ? "border-primary/50 bg-primary/5 shadow-sm"
          : "border-border opacity-60",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium">{title}</p>
          <p className="text-xs text-muted-foreground">{desc}</p>
        </div>

        <Toggle
          checked={isActive}
          onChange={(on) => on && setMode(id)}
        />
      </div>

      {isActive && children && (
        <div className="mt-4 space-y-3 border-t border-border pt-4">
          {children}
        </div>
      )}
    </div>
  )
}

function ProviderPanel({ onSaved }: { onSaved: () => void }) {
  const [mode, setMode] = useState<ProviderMode>("default")

  /* Offline */
  const [offlineProvider, setOfflineProvider] = useState("ollama")
  const [hostUrl, setHostUrl] = useState("http://localhost:11434")
  const [offlineModel, setOfflineModel] = useState("")

  /* Serverless */
  const [onlineProvider, setOnlineProvider] = useState("together_ai")
  const [apiKey, setApiKey] = useState("")
  const [onlineModel, setOnlineModel] = useState("")

  const tokenLabel: Record<string, string> = {
    together_ai: "Together AI API Key",
    huggingface: "HuggingFace Token",
    openai: "OpenAI API Key",
    anthropic: "Anthropic API Key",
    groq: "Groq API Key",
  }

  const modelPlaceholder: Record<string, string> = {
    together_ai: "e.g. mistralai/Mixtral-8x7B-Instruct-v0.1",
    huggingface: "e.g. HuggingFaceH4/zephyr-7b-beta",
    openai: "e.g. gpt-4o",
    anthropic: "e.g. claude-sonnet-4-20250514",
    groq: "e.g. llama3-70b-8192",
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold">Provider</h2>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Select <span className="font-semibold text-foreground">one</span> provider.
          Activating a provider automatically disables the others.
        </p>
      </div>

      <Divider />

      <div className="space-y-3">
        <ProviderCard
          id="default"
          mode={mode}
          setMode={setMode}
          title="Use default providers"
          desc="Use the built-in models pre-configured by your administrator. No setup needed."
        />

        <ProviderCard
          id="offline"
          mode={mode}
          setMode={setMode}
          title="Link to an offline model"
          desc="Connect to a locally running model server (e.g. Ollama). Fully private — no data leaves your machine."
        >
          <div>
            <FieldLabel>Offline Provider</FieldLabel>
            <NativeSelect
              value={offlineProvider}
              onChange={setOfflineProvider}
              options={[
                { label: "Ollama", value: "ollama" },
                { label: "LM Studio", value: "lm_studio" },
                { label: "LocalAI", value: "localai" },
              ]}
            />
          </div>

          <div>
            <FieldLabel>Host URL</FieldLabel>
            <Input
              value={hostUrl}
              onChange={(e) => setHostUrl(e.target.value)}
              placeholder="http://localhost:11434"
              className="font-mono text-xs"
            />
          </div>

          <div>
            <FieldLabel>
              Model name <span className="font-normal">(optional)</span>
            </FieldLabel>
            <Input
              value={offlineModel}
              onChange={(e) => setOfflineModel(e.target.value)}
              placeholder="e.g. llama3.2"
              className="font-mono text-xs"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Leave blank to use the server&apos;s default model.
            </p>
          </div>
        </ProviderCard>

        <ProviderCard
          id="serverless"
          mode={mode}
          setMode={setMode}
          title="Link to a Serverless Inference provider"
          desc="Use a cloud-hosted model via an API key. Requires a valid account with the provider."
        >
          <div>
            <FieldLabel>Online Provider</FieldLabel>
            <NativeSelect
              value={onlineProvider}
              onChange={(v) => {
                setOnlineProvider(v)
                setApiKey("")
                setOnlineModel("")
              }}
              options={[
                { label: "Together AI", value: "together_ai" },
                { label: "HuggingFace", value: "huggingface" },
                { label: "OpenAI", value: "openai" },
                { label: "Anthropic", value: "anthropic" },
                { label: "Groq", value: "groq" },
              ]}
            />
          </div>

          <div>
            <FieldLabel>{tokenLabel[onlineProvider]}</FieldLabel>
            <Input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Paste your API key here…"
              className="font-mono text-xs"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              API keys are stored securely on the Cheshire server.
            </p>
          </div>

          <div>
            <FieldLabel>
              Model <span className="font-normal">(optional)</span>
            </FieldLabel>
            <Input
              value={onlineModel}
              onChange={(e) => setOnlineModel(e.target.value)}
              placeholder={modelPlaceholder[onlineProvider]}
              className="font-mono text-xs"
            />
          </div>
        </ProviderCard>
      </div>

      <Divider />

      <div className="flex justify-end">
        <Button size="sm" onClick={onSaved}>
          Save changes
        </Button>
      </div>
    </div>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
// Tab — Account
// ─────────────────────────────────────────────────────────────────────────────

function AccountPanel({
  onSaved,
  onClose,
  chats,
  onDeleteAllChats,
}: {
  onSaved: () => void
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

      <Divider />

      <div className="flex justify-end">
        <Button size="sm" onClick={onSaved}>Save changes</Button>
      </div>
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
  const [savedBadge,  setSavedBadge]  = useState(false)
  const timerRef  = useRef<ReturnType<typeof setTimeout> | null>(null)
  const modalRef  = useRef<HTMLDivElement>(null)

  /* Escape to close */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [onClose])

  const handleSaved = () => {
    if (timerRef.current) clearTimeout(timerRef.current)
    setSavedBadge(true)
    timerRef.current = setTimeout(() => setSavedBadge(false), 2500)
  }

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
        className="relative flex h-[650px] max-h-[90vh] w-[700px] max-w-[96vw] overflow-hidden rounded-2xl bg-background shadow-2xl ring-1 ring-foreground/[0.08]"
      >
        {/* ── Left sidebar ─────────────────────────────────────────────── */}
        <div className="flex w-[200px] shrink-0 flex-col border-r border-border bg-muted/20 px-2 py-4">
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

          {/* Saved badge anchored to sidebar bottom */}
          <div className="mt-auto flex justify-center pt-4">
            <SavedBadge visible={savedBadge} />
          </div>
        </div>

        {/* ── Right content ─────────────────────────────────────────────── */}
        <div className="min-h-0 flex-1 overflow-y-auto p-6">
          {activeTab === "general"  && <GeneralPanel  onSaved={handleSaved} onClose={onClose} />}
          {activeTab === "provider" && <ProviderPanel onSaved={handleSaved} />}
          {activeTab === "account"  && (
            <AccountPanel
              onSaved={handleSaved}
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