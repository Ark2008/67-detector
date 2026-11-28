// Контракт: backend/app/schemas/api.py и backend/app/api/*.py.
const API_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')

export interface Player { player_id: string; name: string; created_at: string }
export interface GameSession { session_id: string; status: string; score: number; started_at: string; ended_at?: string | null }
export interface RatingPlayer { player_id: string; name: string; total_score: number; best_session_score: number }
export interface RatingsResponse { players: RatingPlayer[] }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); this.name = 'ApiError' }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options?.headers },
    })
  } catch {
    throw new Error('Не удалось связаться с сервером. Проверь, запущен ли FastAPI на порту 8000.')
  }
  if (!response.ok) {
    let detail = ''
    try { const data = await response.json(); detail = typeof data?.detail === 'string' ? data.detail : '' } catch { /* plain-text error */ }
    throw new ApiError(response.status, `Сервер вернул ошибку ${response.status}${detail ? `: ${detail}` : ''}`)
  }
  return response.json() as Promise<T>
}

export function createPlayer(name: string) { return request<Player>('/players', { method: 'POST', body: JSON.stringify({ name: name.trim() }) }) }
export function startSession(playerId: string) { return request<GameSession>('/sessions', { method: 'POST', body: JSON.stringify({ player_id: playerId }) }) }
export function stopSession(sessionId: string) { return request<GameSession>(`/sessions/${encodeURIComponent(sessionId)}/stop`, { method: 'POST' }) }
export function getRatings() { return request<RatingsResponse>('/ratings') }
export function getSessionSocketUrl(sessionId: string) {
  const url = new URL(API_URL)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.pathname = `/ws/sessions/${encodeURIComponent(sessionId)}`
  return url.toString()
}

// PATCH/DELETE добавляются в backend отдельно. Сверьте контракт перед отправкой PR.
export function renamePlayer(playerId: string, name: string) {
  return request<Player>(`/players/${encodeURIComponent(playerId)}`, { method: 'PATCH', body: JSON.stringify({ name: name.trim() }) })
}
export async function deletePlayer(playerId: string): Promise<void> {
  const response = await fetch(`${API_URL}/players/${encodeURIComponent(playerId)}`, { method: 'DELETE' }).catch(() => {
    throw new Error('Не удалось связаться с сервером.')
  })
  if (!response.ok) {
    throw new ApiError(response.status, `Не удалось удалить профиль: ${response.status}`)
  }
}
