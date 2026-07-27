import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TopBar from '../components/TopBar';
import { erpConfigApi } from '../api/erpConfig';
import { ApiError } from '../api/client';

export default function ErpConfigPage() {
  const navigate = useNavigate();

  const [config, setConfig] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [editandoId, setEditandoId] = useState(null);
  const [valorEdit, setValorEdit] = useState('');
  const [guardando, setGuardando] = useState(false);
  const [errorFila, setErrorFila] = useState('');

  function cargar() {
    setLoading(true);
    erpConfigApi
      .listar()
      .then(setConfig)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'No se pudo cargar la configuración'))
      .finally(() => setLoading(false));
  }

  useEffect(cargar, []);

  function abrirEdicion(item) {
    setEditandoId(item.id);
    setValorEdit(item.valor);
    setErrorFila('');
  }

  function cancelarEdicion() {
    setEditandoId(null);
    setValorEdit('');
    setErrorFila('');
  }

  async function guardarFila(item) {
    if (!valorEdit.trim()) {
      setErrorFila('El valor no puede estar vacío');
      return;
    }
    setErrorFila('');
    setGuardando(true);
    try {
      await erpConfigApi.actualizar(item.id, {
        valor: valorEdit.trim(),
        descripcion: item.descripcion,
      });
      cancelarEdicion();
      cargar();
    } catch (err) {
      setErrorFila(err instanceof ApiError ? err.message : 'No se pudo guardar el valor');
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="screen">
      <TopBar titulo="Configuración ERP" subtitulo="Administración" onBack={() => navigate('/menu')} />
      <div className="screen-content">
        <p style={{ color: 'var(--ink-2)', marginBottom: 'var(--sp-4)' }}>
          Parámetros de la relación entre LIMSS y el ERP (mapeo de tipos de material a códigos CODSAR).
          Cambiarlos afecta cómo LIMSS busca materiales en el ERP — solo editá esto si sabés lo que estás haciendo.
        </p>

        {error && <div className="alert alert-danger" style={{ marginBottom: 'var(--sp-4)' }}>{error}</div>}

        {loading ? (
          <div className="state-block"><span className="spinner" /></div>
        ) : config.length === 0 ? (
          <div className="state-block"><span className="state-block-title">Sin parámetros configurados</span></div>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Clave</th>
                  <th>Descripción</th>
                  <th>Valor</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {config.map((item) => {
                  const editando = editandoId === item.id;
                  return (
                    <tr key={item.id}>
                      <td style={{ fontFamily: 'var(--font-mono)' }}>{item.clave}</td>
                      <td>{item.descripcion || '—'}</td>
                      <td>
                        {editando ? (
                          <div>
                            <input
                              className="field-input"
                              style={{ maxWidth: 160 }}
                              value={valorEdit}
                              onChange={(e) => setValorEdit(e.target.value)}
                              disabled={guardando}
                              autoFocus
                            />
                            {errorFila && <div className="field-error" style={{ marginTop: 4 }}>{errorFila}</div>}
                          </div>
                        ) : (
                          <span style={{ fontFamily: 'var(--font-mono)' }}>{item.valor}</span>
                        )}
                      </td>
                      <td style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
                        {editando ? (
                          <>
                            <button className="btn btn-ghost" onClick={cancelarEdicion} disabled={guardando}>
                              Cancelar
                            </button>
                            <button className="btn btn-primary" onClick={() => guardarFila(item)} disabled={guardando}>
                              {guardando ? <span className="spinner" /> : 'Guardar'}
                            </button>
                          </>
                        ) : item.editable ? (
                          <button className="btn btn-ghost" onClick={() => abrirEdicion(item)}>Editar</button>
                        ) : (
                          <span className="badge badge-neutral">No editable</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
