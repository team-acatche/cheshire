// src/lib/auth.ts
// Central auth module: token storage, authenticated fetch wrapper, login/logout helpers.
//
// Storage: sessionStorage — token is scoped to the browser tab and is
// automatically cleared when the tab or window is closed. This prevents
// tokens from persisting across browser restarts, which is the key
// improvement over localStorage requested by the PO.

export interface AuthUser {
  user_id: string
  email: string
  sessions_folder: string
  username: string | null
  full_name: string | null
  avatar_uri: string
  access_token: string
}

const TOKEN_KEY = "cheshire_access_token"
const USER_KEY  = "cheshire_user"

// ─── Persistence ─────────────────────────────────────────────────────────────

export function saveAuth(user: AuthUser): void {
  sessionStorage.setItem(TOKEN_KEY, user.access_token)
  sessionStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY)
}

export function getStoredUser(): AuthUser | null {
  const raw = sessionStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as AuthUser
  } catch {
    return null
  }
}

export function clearAuth(): void {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(USER_KEY)
}

// ─── Authenticated fetch ──────────────────────────────────────────────────────

/**
 * Drop-in replacement for `fetch` that automatically attaches the JWT bearer
 * token from storage. If the server responds with 401 the token is cleared so
 * the app can redirect to login.
 */
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken()
  const res = await fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })

  if (res.status === 401) {
    clearAuth()
    window.location.reload() // bump back to login
  }

  return res
}

// ─── Auth actions ─────────────────────────────────────────────────────────────

/**
 * POST /api/v1/login using OAuth2 password-flow form encoding.
 * Stores the returned token and returns the full user object.
 */
export async function loginRequest(email: string, password: string): Promise<AuthUser> {
  const form = new URLSearchParams()
  form.append("username", email)   // FastAPI OAuth2PasswordRequestForm uses "username"
  form.append("password", password)

  const res = await fetch("/api/v1/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form.toString(),
  })

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(typeof err.detail === "string" ? err.detail : "Login failed")
  }

  const data = await res.json()
  const user: AuthUser = {
    user_id:         data.user_id,
    email:           data.email,
    sessions_folder: data.sessions_folder,
    username:        data.username ?? null,
    full_name:       data.full_name ?? null,
    avatar_uri:      data.avatar_uri ?? "avatars/default.png",
    access_token:    data.access_token,
  }
  saveAuth(user)
  return user
}

export function logout(): void {
  clearAuth()
  window.location.reload()
}