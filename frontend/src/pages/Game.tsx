import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getSessionSocketUrl, startSession, stopSession, type GameSession, type Player } from '../services/api'
import { createHandLandmarker, type HandLandmarkerLike } from '../services/handTracking'

type SocketEvent =
  | { type: 'session_ready'; score: number; status: string }
  | { type: 'gesture_detected'; score: number }
  | { type: 'session_state'; score: number; status: string }
  | { type: 'error'; code: string; message?: string }

export default function Game({ player }: { player: Player }) {
  const navigate = useNavigate()

  const [session, setSession] = useState<GameSession | null>(null)
  const sessionRef = useRef<GameSession | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const landmarkerRef = useRef<HandLandmarkerLike | null>(null)
  const animationRef = useRef<number | null>(null)
  const lastFrameAtRef = useRef(0)
  const lastTimestampRef = useRef(0)

  const [score, setScore] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [socketStatus, setSocketStatus] = useState('Не подключён')

  function stopFrameLoop() {
    if (animationRef.current !== null) {
      cancelAnimationFrame(animationRef.current)
      animationRef.current = null
    }
  }

  function stopCamera() {
    stopFrameLoop()

    streamRef.current?.getTracks().forEach(track => track.stop())
    streamRef.current = null

    landmarkerRef.current?.close()
    landmarkerRef.current = null

    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
  }

  function stopSocket() {
    stopFrameLoop()

    const socket = socketRef.current
    socketRef.current = null

    if (socket && socket.readyState < WebSocket.CLOSING) {
      socket.close()
    }
  }

  useEffect(() => {
    return () => {
      stopSocket()
      stopCamera()
    }
  }, [])

  function startFrameLoop(socket: WebSocket) {
    const video = videoRef.current

    if (!video || !landmarkerRef.current) {
      setError('Камера или MediaPipe не готовы')
      return
    }

    function sendFrame(now: number) {
        if (socket.readyState !== WebSocket.OPEN || !video || !landmarkerRef.current) return

      if (now - lastFrameAtRef.current >= 66 && video.readyState >= 2) {
        lastFrameAtRef.current = now

        const result = landmarkerRef.current?.detectForVideo(video, now)

        if (result) {
          const hands = result.landmarks.map((landmarks, index) => ({
            handedness:
              result.handedness[index]?.[0]?.categoryName === 'Left'
                ? 'Left'
                : 'Right',
            score: result.handedness[index]?.[0]?.score ?? 0,
            landmarks: landmarks.map(point => ({
              x: point.x,
              y: point.y,
              z: point.z,
            })),
          }))

          const timestamp = Math.max(
            Math.round(now),
            lastTimestampRef.current + 1,
          )

          lastTimestampRef.current = timestamp

          socket.send(JSON.stringify({
            type: 'frame',
            timestamp_ms: timestamp,
            hands,
          }))
        }
      }

      animationRef.current = requestAnimationFrame(sendFrame)
    }

    animationRef.current = requestAnimationFrame(sendFrame)
  }

  async function begin() {
    setBusy(true)
    setError('')

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: false,
      })

      streamRef.current = stream

      const video = videoRef.current
      if (!video) throw new Error('Видеоэлемент не найден')

      video.srcObject = stream
      await video.play()

      landmarkerRef.current = await createHandLandmarker()

      const result = await startSession(player.player_id)

      sessionRef.current = result
      setSession(result)
      setScore(result.score)

      const socket = new WebSocket(getSessionSocketUrl(result.session_id))
      socketRef.current = socket

      socket.onopen = () => {
        setSocketStatus('Соединение установлено, отправка координат активна')
        lastFrameAtRef.current = 0
        lastTimestampRef.current = 0
        startFrameLoop(socket)
      }

      socket.onmessage = event => {
        try {
          const message = JSON.parse(event.data) as SocketEvent

          if (
            message.type === 'session_ready' ||
            message.type === 'gesture_detected' ||
            message.type === 'session_state'
          ) {
            setScore(message.score)
          }

          if (message.type === 'session_state' && message.status !== 'active') {
            setSession(null)
            sessionRef.current = null
            setSocketStatus('Сессия завершена')
            stopCamera()
          }

          if (message.type === 'error') {
            setError(`Ошибка WebSocket: ${message.message || message.code}`)
          }
        } catch {
          setError('Неверное сообщение от WebSocket')
        }
      }

      socket.onerror = () => setSocketStatus('Ошибка WebSocket')

      socket.onclose = () => {
        stopFrameLoop()
        setSocketStatus('Соединение закрыто')
      }
    } catch (err) {
      stopCamera()
      stopSocket()
      setError(err instanceof Error ? err.message : 'Не удалось начать сессию')
    } finally {
      setBusy(false)
    }
  }

  async function finish() {
    const active = sessionRef.current

    if (!active) {
      navigate('/rating')
      return
    }

    setBusy(true)
    setError('')

    try {
      const result = await stopSession(active.session_id)

      setScore(result.score)
      setSession(null)
      sessionRef.current = null

      stopSocket()
      stopCamera()

      navigate('/rating')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось завершить сессию')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="page game-page">
      <div className="game-layout">
        <div className="camera-panel">
          <span className="camera-label">
            <span className="live-dot" /> Камера · MediaPipe
          </span>

          <video
            ref={videoRef}
            autoPlay
            muted
            playsInline
            style={{ width: '100%', height: 'auto', transform: 'scaleX(-1)' }}
          />

          <span className="camera-caption">
            Координаты рук передаются на сервер через WebSocket.
          </span>
        </div>

        <aside className="game-sidebar">
          <section className="stat-card score-card">
            <span className="eyebrow">СЧЁТ</span>
            <strong className="score-number">{score}</strong>
            <span className="muted">жестов за эту игру</span>
          </section>

          <section className="stat-card small-stats">
            <div>
              <span>Статус игры</span>
              <b>{session ? 'Активна' : 'Не запущена'}</b>
            </div>
            <div>
              <span>Соединение</span>
              <b>{socketStatus}</b>
            </div>
          </section>

          <section className="stat-card sound-card">
            <div>
              <b>Звук и музыка</b>
              <small>Будут добавлены отдельно</small>
            </div>
          </section>

          <div className="side-buttons">
            {!session && (
              <button className="btn btn-primary" disabled={busy} onClick={begin}>
                {busy ? 'Запускаем…' : 'Начать сессию'}
              </button>
            )}

            <button
              className="btn btn-secondary"
              disabled
              title="Сброс счёта не предусмотрен текущим API"
            >
              Сбросить счёт
            </button>

            <button className="btn btn-primary" onClick={finish} disabled={busy}>
              {session ? 'Завершить игру' : 'В рейтинг'}
            </button>
          </div>

          {error && <p role="alert" className="form-error">{error}</p>}

          <p className="sidebar-footnote">
            Камера и MediaPipe передают координаты рук на backend.
          </p>
        </aside>
      </div>
    </main>
  )
}
