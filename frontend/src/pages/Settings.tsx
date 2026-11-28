import { useState, type FormEvent } from 'react'
import { ApiError, deletePlayer, renamePlayer, type Player } from '../services/api'

export default function Settings({ player, onUpdate, onDeleted }: { player: Player; onUpdate: (value: Player) => void; onDeleted: () => void }) {
  const [name, setName] = useState(player.name)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)

  function handleError(err: unknown) {
    if (err instanceof ApiError && err.status === 404) {
      onDeleted()
      return
    }
    setError(err instanceof Error ? err.message : 'Произошла ошибка')
  }
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!name.trim()) { setError('Ник не может быть пустым'); return }
    setBusy(true); setError(''); setNotice('')
    try { const updated = await renamePlayer(player.player_id, name.trim()); onUpdate(updated); setNotice('Ник сохранён') }
    catch (err) { handleError(err) }
    finally { setBusy(false) }
  }
  async function remove() {
    if (!confirmDelete) return
    setBusy(true); setError(''); setNotice('')
    try { await deletePlayer(player.player_id); onDeleted() }
    catch (err) { handleError(err) }
    finally { setBusy(false) }
  }
  return <main className="page settings-page">
    <div className="settings-heading"><span className="brand-mark">67</span><h1>НАСТРОЙКИ</h1><p>Управление твоим профилем</p></div>
    <section className="settings-card">
      <h2>Имя игрока</h2>
      <form onSubmit={save} className="settings-form">
        <label htmlFor="settings-name">Текущий ник</label>
        <input id="settings-name" value={name} maxLength={30} onChange={e => { setName(e.target.value); setError(''); setNotice('') }} />
        <button className="btn btn-primary" type="submit" disabled={busy || !name.trim()}>{busy ? 'Сохраняем…' : 'Сохранить'}</button>
      </form>
      {notice && <p role="status" className="settings-success">{notice}</p>}
    </section>
    <section className="settings-card settings-danger">
      <h2>Удалить мои данные</h2>
      <p className="muted">Удаление профиля необратимо. После удаления ты вернёшься на экран входа.</p>
      {!confirmDelete ? <button type="button" className="btn btn-danger" onClick={() => setConfirmDelete(true)}>Удалить мои данные</button>
        : <div className="delete-confirm"><p>Точно удалить профиль «{player.name}»?</p><div className="delete-actions"><button className="btn btn-danger" disabled={busy} onClick={remove}>Да, удалить навсегда</button><button className="btn btn-secondary" disabled={busy} onClick={() => setConfirmDelete(false)}>Отмена</button></div></div>}
    </section>
    {error && <p className="form-error" role="alert">{error}</p>}
  </main>
}
