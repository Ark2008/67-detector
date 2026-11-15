import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getRatings, type Player, type RatingPlayer } from '../services/api'
export default function Rating({ player }: { player: Player }) {
  const navigate = useNavigate()
  const [items, setItems] = useState<RatingPlayer[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => {
    let alive = true
    getRatings().then(result => { if (alive) setItems(result.players) })
      .catch(err => { if (alive) setError(err instanceof Error ? err.message : 'Ошибка загрузки') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])
  return <main className="page rating-page">
    <div className="rating-title"><h1>ЛИДЕРБОРД</h1><p>Рейтинг по сумме очков завершённых сессий</p><span className="music-pill"><span className="status-dot" /> 67 детектор</span></div>
    {loading ? <div className="empty-leaderboard">Загружаем рейтинг…</div>
      : error ? <div className="empty-leaderboard"><h2>Не удалось загрузить рейтинг</h2><p role="alert">{error}</p><button className="btn btn-secondary" onClick={() => window.location.reload()}>Повторить</button></div>
      : items.length === 0 ? <div className="empty-leaderboard"><div className="empty-podium" aria-hidden="true"><span>2</span><span>1</span><span>3</span></div><h2>Рейтинг пока пуст</h2><p>Когда игроки завершат сессии, здесь появятся их результаты.</p></div>
      : <div className="ranking-list">{items.map((item, i) => <div key={item.player_id} className={`ranking-row ${item.player_id === player.player_id ? 'ranking-row--me' : ''}`}><span className="ranking-place">{i + 1}</span><span className="ranking-avatar">{item.name.charAt(0).toUpperCase()}</span><span className="ranking-name">{item.name}{item.player_id === player.player_id ? ' (ты)' : ''}</span><strong className="ranking-score">{item.total_score}</strong></div>)}</div>}
    <div className="rating-actions"><button className="btn btn-primary" onClick={() => navigate('/game')}>Играть ещё</button><button className="btn btn-secondary" onClick={() => navigate('/game')}>В меню</button></div>
  </main>
}
