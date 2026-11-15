import { useState, type FormEvent, type ReactNode } from 'react'
export default function Login({ onLogin, logo }: { onLogin: (name: string) => Promise<void>; logo: ReactNode }) {
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!name.trim()) { setError('Введите имя игрока'); return }
    setLoading(true); setError('')
    try { await onLogin(name.trim()) }
    catch (err) { setError(err instanceof Error ? err.message : 'Ошибка входа') }
    finally { setLoading(false) }
  }
  return <main className="login-screen">
    <div className="login-watermark" aria-hidden="true">67</div>
    <section className="login-content">{logo}
      <p className="login-subtitle">Покажи жест «шесть-семь» в камеру — мы посчитаем</p>
      <form className="login-form" onSubmit={submit}>
        <label htmlFor="player-name">Как тебя зовут?</label>
        <input id="player-name" autoFocus placeholder="Твой ник" maxLength={30} autoComplete="nickname" value={name} onChange={e => {setName(e.target.value);setError('')}} aria-invalid={Boolean(error)}/>
        {error && <p role="alert" className="form-error">{error}</p>}
        <button type="submit" className="btn btn-primary" disabled={loading}>{loading ? 'Подключаемся…' : 'Войти'}</button>
        <p className="form-hint">Без пароля: имя сохраняется в этом браузере, данные игрока — на сервере.</p>
      </form>
    </section>
    <p className="login-footer"><span className="status-dot" /> Камера будет подключена отдельным модулем</p>
  </main>
}
