import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getSessionSocketUrl, startSession, stopSession, type GameSession, type Player } from '../services/api'

type SocketEvent =
  | { type: 'session_ready'; score: number; status: string }
  | { type: 'gesture_detected'; score: number }
  | { type: 'session_state'; score: number; status: string }
  | { type: 'error'; code: string; message?: string }

function CameraPlaceholder() {
  return <div className="camera-panel"><span className="camera-label"><span className="live-dot" /> Камера · ожидает интеграции CV</span>
    <div className="camera-art" aria-hidden="true"><div className="camera-figure"><div className="figure-head"/><div className="figure-body"/></div><div className="gesture-title">67!</div></div>
    <span className="camera-caption">Это заглушка. Видео и MediaPipe подключает CV-команда.</span>
  </div>
}
export default function Game({ player }: { player: Player }) {
  const navigate = useNavigate()
  const [session, setSession] = useState<GameSession | null>(null)
  const sessionRef = useRef<GameSession | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const [score, setScore] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [socketStatus, setSocketStatus] = useState('Не подключён')
  useEffect(() => () => { socketRef.current?.close() }, [])
  async function begin() {
    setBusy(true); setError('')
    try {
      const result = await startSession(player.player_id)
      sessionRef.current = result; setSession(result); setScore(result.score)
      const socket = new WebSocket(getSessionSocketUrl(result.session_id))
      socketRef.current = socket
      socket.onopen = () => setSocketStatus('Соединение установлено (кадры не отправляются)')
      socket.onmessage = event => {
        try {
          const message = JSON.parse(event.data) as SocketEvent
          if (message.type === 'session_ready' || message.type === 'gesture_detected' || message.type === 'session_state') setScore(message.score)
          if (message.type === 'session_state' && message.status !== 'active') { setSession(null); sessionRef.current = null; setSocketStatus('Сессия завершена') }
          if (message.type === 'error') setError(`Ошибка WebSocket: ${message.message || message.code}`)
        } catch { setError('Неверное сообщение от WebSocket') }
      }
      socket.onerror = () => setSocketStatus('Ошибка WebSocket')
      socket.onclose = () => setSocketStatus('Соединение закрыто')
    } catch (err) { setError(err instanceof Error ? err.message : 'Не удалось начать сессию') }
    finally { setBusy(false) }
  }
  async function finish() {
    const active = sessionRef.current
    if (!active) { navigate('/rating'); return }
    setBusy(true); setError('')
    try {
      const result = await stopSession(active.session_id)
      setScore(result.score); setSession(null); sessionRef.current = null
      socketRef.current?.close()
      navigate('/rating')
    } catch (err) { setError(err instanceof Error ? err.message : 'Не удалось завершить сессию') }
    finally { setBusy(false) }
  }
  return <main className="page game-page">
    <div className="game-layout"><CameraPlaceholder />
      <aside className="game-sidebar">
        <section className="stat-card score-card"><span className="eyebrow">СЧЁТ</span><strong className="score-number">{score}</strong><span className="muted">жестов за эту игру</span></section>
        <section className="stat-card small-stats"><div><span>Статус игры</span><b>{session ? 'Активна' : 'Не запущена'}</b></div><div><span>Соединение</span><b>{socketStatus}</b></div></section>
        <section className="stat-card sound-card"><div><b>Звук и музыка</b><small>Будут добавлены отдельно</small></div></section>
        <div className="side-buttons">
          {!session && <button className="btn btn-primary" disabled={busy} onClick={begin}>{busy ? 'Запускаем…' : 'Начать сессию'}</button>}
          <button className="btn btn-secondary" disabled title="Сброс счёта не предусмотрен текущим API">Сбросить счёт</button>
          <button className="btn btn-primary" onClick={finish} disabled={busy}>{session ? 'Завершить игру' : 'В рейтинг'}</button>
        </div>
        {error && <p role="alert" className="form-error">{error}</p>}
        <p className="sidebar-footnote">Сессии и счёт подключены к backend. Кадры камеры пока не отправляются — их подключит CV-команда. Без кадров backend может завершить сессию по таймауту.</p>
      </aside>
    </div>
  </main>
}
