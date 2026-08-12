import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import TopBar from '../components/TopBar';
import { authApi } from '../api/auth';
import { ApiError } from '../api/client';

export default function CambiarPinPage() {
  const { user, marcarPinCambiado } = useAuth();
  const navigate = useNavigate();
  const forzado = !!user?.debe_cambiar_pin;

  const [pinActual, setPinActual] = useState('');
  const [pinNuevo, setPinNuevo] = useState('');
  const [pinConfirmar, setPinConfirmar] = useState('');
  const [error, setError] = useState('');
  const [guardando, setGuardando] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!/^\d{4,6}$/.test(pinNuevo)) {
      setError('El PIN nuevo debe tener entre 4 y 6 dígitos');
      return;
    }
    if (pinNuevo !== pinConfirmar) {
      setError('Los PIN no coinciden');
      return;
    }
    if (pinNuevo === pinActual) {
      setError('El PIN nuevo debe ser distinto del actual');
      return;
    }
    setError('');
    setGuardando(true);
    try {
      await authApi.cambiarPin(pinActual, pinNuevo);
      marcarPinCambiado();
      navigate('/menu', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo cambiar el PIN');
      setPinActual('');
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="screen">
      <TopBar
        titulo="Cambiar mi PIN"
        subtitulo={forzado ? 'Cambio obligatorio' : 'Mi cuenta'}
        onBack={forzado ? undefined : () => navigate(-1)}
      />
      <div className="screen-content" style={{ alignItems: 'center' }}>
        <div className="card-elevated" style={{ width: '100%', maxWidth: 380 }}>
          {forzado && (
            <div className="alert alert-warn" style={{ marginBottom: 'var(--sp-4)' }}>
              Por seguridad, tenés que cambiar tu PIN antes de continuar. No vas a poder usar el
              sistema hasta completar este paso.
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div className="field">
              <label className="field-label" htmlFor="pinActual">PIN actual</label>
              <input
                id="pinActual"
                className="field-input"
                type="password"
                inputMode="numeric"
                maxLength={6}
                value={pinActual}
                onChange={(e) => setPinActual(e.target.value.replace(/\D/g, ''))}
                disabled={guardando}
                autoFocus
              />
            </div>

            <div className="field">
              <label className="field-label" htmlFor="pinNuevo">PIN nuevo (4-6 dígitos)</label>
              <input
                id="pinNuevo"
                className="field-input"
                type="password"
                inputMode="numeric"
                maxLength={6}
                value={pinNuevo}
                onChange={(e) => setPinNuevo(e.target.value.replace(/\D/g, ''))}
                disabled={guardando}
              />
            </div>

            <div className="field" style={{ marginBottom: 0 }}>
              <label className="field-label" htmlFor="pinConfirmar">Confirmar PIN nuevo</label>
              <input
                id="pinConfirmar"
                className="field-input"
                type="password"
                inputMode="numeric"
                maxLength={6}
                value={pinConfirmar}
                onChange={(e) => setPinConfirmar(e.target.value.replace(/\D/g, ''))}
                disabled={guardando}
              />
            </div>

            {error && <div className="alert alert-danger" style={{ marginTop: 'var(--sp-4)' }}>{error}</div>}

            <button type="submit" className="btn btn-primary btn-block btn-lg" style={{ marginTop: 'var(--sp-5)' }} disabled={guardando}>
              {guardando ? <span className="spinner" /> : 'Cambiar PIN'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
