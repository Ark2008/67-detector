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

  const [soundEnabled, setSoundEnabled] = useState(() => {
    try { return localStorage.getItem('six-seven-sound') !== 'off' }
    catch { return true }
  })
  const soundEnabledRef = useRef(soundEnabled)
  const [flash, setFlash] = useState(false)
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)

  function gestureEffect() {
    setFlash(true)
    if (flashTimer.current) clearTimeout(flashTimer.current)
    flashTimer.current = setTimeout(() => setFlash(false), 850)
    if (!soundEnabledRef.current) return

    try {
      // Короткий оригинальный сигнал, без сторонней музыкальной записи.
      const ctx = audioContextRef.current ?? new AudioContext()
      audioContextRef.current = ctx
      void ctx.resume()
      for (const [offset, frequency] of [[0, 650], [0.13, 880]]) {
        const oscillator = ctx.createOscillator()
        const gain = ctx.createGain()
        const at = ctx.currentTime + offset
        oscillator.type = 'sine'
        oscillator.frequency.value = frequency
        gain.gain.setValueAtTime(0.0001, at)
        gain.gain.exponentialRampToValueAtTime(0.12, at + 0.015)
        gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.18)
        oscillator.connect(gain)
        gain.connect(ctx.destination)
        oscillator.start(at)
        oscillator.stop(at + 0.19)
      }
    } catch { /* В браузере звук может быть заблокирован */ }
  }

  function toggleSound() {
    setSoundEnabled(previous => {
      const next = !previous
      soundEnabledRef.current = next
      try { localStorage.setItem('six-seven-sound', next ? 'on' : 'off') }
      catch { /* Настройка действует хотя бы до обновления */ }
      return next
    })
  }

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
      if (flashTimer.current) clearTimeout(flashTimer.current)
      void audioContextRef.current?.close()
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
      // Вызов из нажатия кнопки разрешает воспроизведение звука браузером.
      if (soundEnabledRef.current) {
        try {
          audioContextRef.current ??= new AudioContext()
          void audioContextRef.current.resume()
        } catch { /* Без звука игра продолжает работать */ }
      }

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

          if (message.type === 'gesture_detected') {
            gestureEffect()
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
        <div className="camera-effect-wrap">
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
          {flash && (
            <div className="gesture-flash" role="status" aria-live="polite">
              67! <small>+1</small>
            </div>
          )}
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
              <b>Звуковой эффект</b>
              <small>Сигнал при распознавании 67</small>
            </div>
            <button
              type="button"
              className={`toggle ${soundEnabled ? 'toggle--on' : ''}`}
              role="switch"
              aria-checked={soundEnabled}
              aria-label="Звуковые эффекты"
              onClick={toggleSound}
            >
              <span />
            </button>
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
