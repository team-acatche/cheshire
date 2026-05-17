  export interface AuthUser {
    user_id: string
    email: string
    sessions_folder: string
    username: string | null
    full_name: string | null
    avatar_uri: string
  }

  const USER_KEY = "cheshire_user"

  export function saveAuth(user: AuthUser): void {
    sessionStorage.setItem(USER_KEY, JSON.stringify(user))
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

  export function updateStoredUser(partial: Partial<AuthUser>): void {
    const user = getStoredUser()
    if (!user) return
    saveAuth({ ...user, ...partial })
  }

  export function clearAuth(): void {
    sessionStorage.removeItem(USER_KEY)
  }

  export async function authFetch(
    url: string,
    options: RequestInit = {}
  ): Promise<Response> {
    const res = await fetch(url, {
      ...options,
      credentials: "include",
      headers: {
        ...options.headers,
      },
    })

    if (res.status === 401) {
      clearAuth()
    }

    return res
  }

  export async function loginRequest(email: string, password: string): Promise<AuthUser> {
    const form = new URLSearchParams()
    form.append("username", email)
    form.append("password", password)

    const res = await fetch("/api/v1/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form.toString(),
      credentials: "include",
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(typeof err.detail === "string" ? err.detail : "Login failed")
    }

    const data = await res.json()
    const userData = data.user ?? data
    const user: AuthUser = {
      user_id: userData.user_id,
      email: userData.email,
      sessions_folder: userData.sessions_folder,
      username: userData.username ?? null,
      full_name: userData.full_name ?? null,
      avatar_uri: userData.avatar_uri ?? "avatars/default.png",
    }

    saveAuth(user)
    return user
  }

  export async function logout(): Promise<void> {
    try {
      await fetch("/api/v1/logout", {
        method: "POST",
        credentials: "include",
      })
    } finally {
      clearAuth()
      window.location.reload()
    }
  }