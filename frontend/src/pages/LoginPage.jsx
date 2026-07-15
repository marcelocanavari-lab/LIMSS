import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ApiError } from '../api/client';

const PIN_LENGTH = 4;

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [codigo, setCodigo] = useState('');
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const pinRef = useRef(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (!codigo.trim()) {
      setError('Ingresá tu código de usuario');
      return;
    }
    if (pin.length < 4) {
      setError('El PIN debe tener al menos 4 dígitos');
      pinRef.current?.focus();
      return;
    }

    setLoading(true);
    try {
      await login(codigo.trim().toUpperCase(), pin);
      navigate('/menu', { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError('Código o PIN incorrecto');
      } else {
        setError(err.message || 'No se pudo iniciar sesión');
      }
      setPin('');
      pinRef.current?.focus();
    } finally {
      setLoading(false);
    }
  }

  function handlePinChange(e) {
    const digits = e.target.value.replace(/\D/g, '').slice(0, 6);
    setPin(digits);
  }

  return (
    <div className="screen" style={{ alignItems: 'center', justifyContent: 'center' }}>
      <div
        className="card-elevated"
        style={{ width: '100%', maxWidth: 380, margin: 'auto' }}
      >
        <div style={{ textAlign: 'center', marginBottom: 'var(--sp-6)' }}>
          <div
            style={{
              width: 64,
              height: 64,
              borderRadius: 18,
              background: 'var(--accent)',
              color: 'var(--accent-ink)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto var(--sp-4)',
              fontFamily: 'var(--font-display)',
              fontWeight: 700,
              fontSize: 28,
            }}
          >
            LX
          </div>
          <h1 style={{ fontSize: 'var(--fs-xl)' }}>LIMSS</h1>
          <p style={{ color: 'var(--ink-2)', fontSize: 'var(--fs-sm)', marginTop: 4 }}>
            Ingresá con tu código y PIN
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="field">
            <label className="field-label" htmlFor="codigo">
              Código de usuario
            </label>
            <input
              id="codigo"
              className="field-input"
              type="text"
              autoCapitalize="characters"
              autoComplete="username"
              placeholder="Ej. JPEREZ"
              value={codigo}
              onChange={(e) => setCodigo(e.target.value)}
              disabled={loading}
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="pin">
              PIN
            </label>
            <input
              ref={pinRef}
              id="pin"
              className="field-input field-input-lg"
              type="password"
              inputMode="numeric"
              autoComplete="current-password"
              placeholder="• • • •"
              value={pin}
              onChange={handlePinChange}
              maxLength={PIN_LENGTH + 2}
              disabled={loading}
            />
          </div>

          {error && (
            <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>
              <span>{error}</span>
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary btn-block btn-lg"
            disabled={loading}
          >
            {loading ? <span className="spinner" /> : 'Ingresar'}
          </button>
        </form>
      </div>
    </div>
  );
}
