import { useState, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import Login from './pages/Login'
import Game from './pages/Game'
import Rating from './pages/Rating'
import { createPlayer, type Player } from './services/api'
import './index.css'
import './App.css'

const STORAGE_KEY = 'six-seven-player'
function savedPlayer(): Player | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    if (!value) return null
    const player: unknown = JSON.parse(value)
    if (player && typeof player === 'object' && 'player_id' in player && 'name' in player && typeof player.player_id === 'string' && typeof player.name === 'string') return player as Player
  } catch { /* storage may be unavailable */ }
  return null
}
function Logo({ large = false }: { large?: boolean }) {
  return <span className={`brand ${large ? 'brand--large' : ''}`}><span className="brand-mark">67</span><span className="brand-name">ДЕТЕКТОР</span></span>
}
function Header({ player, logout }: { player: Player; logout: () => void }) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  return <header className="site-header">
    <div className="header-start"><button className="text-link" onClick={() => navigate(pathname === '/rating' ? '/game' : '/rating')}>← {pathname === '/rating' ? 'К игре' : 'Рейтинг'}</button></div>
    <div className="header-center"><Logo /></div>
    <div className="header-end"><div className="player-pill"><span className="avatar">{player.name.slice(0, 1).toUpperCase()}</span><span className="player-name">{player.name}</span></div><button className="logout" onClick={logout} title="Выйти" aria-label="Выйти">↗</button></div>
  </header>
}
function Shell({ player, logout, children }: { player: Player; logout: () => void; children: ReactNode }) {
  return <div className="app-shell"><Header player={player} logout={logout} />{children}</div>
}
function RoutedApp() {
  const [player, setPlayer] = useState<Player | null>(savedPlayer)
  const navigate = useNavigate()
  async function login(name: string) {
    const result = await createPlayer(name)
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(result)) } catch { /* still works this tab */ }
    setPlayer(result)
    navigate('/game', { replace: true })
  }
  function logout() {
    try { localStorage.removeItem(STORAGE_KEY) } catch { /* still works this tab */ }
    setPlayer(null)
    navigate('/login', { replace: true })
  }
  return <Routes>
    <Route path="/login" element={player ? <Navigate to="/game" replace /> : <Login onLogin={login} logo={<Logo large />} />} />
    <Route path="/game" element={player ? <Shell player={player} logout={logout}><Game player={player} /></Shell> : <Navigate to="/login" replace />} />
    <Route path="/rating" element={player ? <Shell player={player} logout={logout}><Rating player={player} /></Shell> : <Navigate to="/login" replace />} />
    <Route path="*" element={<Navigate to={player ? '/game' : '/login'} replace />} />
  </Routes>
}
export default function App() { return <BrowserRouter><RoutedApp /></BrowserRouter> }
