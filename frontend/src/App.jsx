import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import PrivateRoute from './components/PrivateRoute';

import LoginPage from './pages/LoginPage';
import CambiarPinPage from './pages/CambiarPinPage';
import DashboardPage from './pages/DashboardPage';
import AdminMenuPage from './pages/AdminMenuPage';
import DefinicionesMenuPage from './pages/DefinicionesMenuPage';
import ReportesMenuPage from './pages/ReportesMenuPage';
import LibroIngresosPage from './pages/reportes/LibroIngresosPage';
import MuestrasMenuPage from './pages/MuestrasMenuPage';
import EquiposMenuPage from './pages/EquiposMenuPage';
import NuevaLecturaPage from './pages/equipos/NuevaLecturaPage';
import EditarLecturaPage from './pages/equipos/EditarLecturaPage';
import HistorialLecturasPage from './pages/equipos/HistorialLecturasPage';
import GraficoTendenciaPage from './pages/equipos/GraficoTendenciaPage';
import GraficoTodasVariablesPage from './pages/equipos/GraficoTodasVariablesPage';
import ReporteDesviacionesPage from './pages/equipos/ReporteDesviacionesPage';
import DiasSinRegistrarPage from './pages/equipos/DiasSinRegistrarPage';
import ImpresionEtiquetasPage from './pages/ImpresionEtiquetasPage';
import UsuariosPage from './pages/UsuariosPage';
import ErpConfigPage from './pages/ErpConfigPage';
import SubarticulosConfigPage from './pages/SubarticulosConfigPage';
import AgenteMuestreoPage from './pages/AgenteMuestreoPage';
import AuditoriaPage from './pages/AuditoriaPage';
import SolicitudesMuestreoPage from './pages/SolicitudesMuestreoPage';
import MisSolicitudesPage from './pages/MisSolicitudesPage';
import EspecificacionesPage from './pages/maestros/EspecificacionesPage';
import EspecificacionFormPage from './pages/maestros/EspecificacionFormPage';
import EspecificacionDetallePage from './pages/maestros/EspecificacionDetallePage';
import CatalogoEnsayosPage from './pages/maestros/CatalogoEnsayosPage';
import EquiposPage from './pages/maestros/EquiposPage';
import EquipoVariablesPage from './pages/maestros/EquipoVariablesPage';
import NovedadesEmpaquePage from './pages/maestros/NovedadesEmpaquePage';
import TestigosPage from './pages/maestros/TestigosPage';
import TestigoFormPage from './pages/maestros/TestigoFormPage';
import TestigoDetallePage from './pages/maestros/TestigoDetallePage';
import TestigoCategoriasPage from './pages/maestros/TestigoCategoriasPage';
import TestigoOrigenesPage from './pages/maestros/TestigoOrigenesPage';
import ReporteTestigosPage from './pages/maestros/ReporteTestigosPage';
import RemitosTestigosPage from './pages/maestros/RemitosTestigosPage';
import RemitoTestigoDetallePage from './pages/maestros/RemitoTestigoDetallePage';
import NuevoRemitoTestigoPage from './pages/maestros/NuevoRemitoTestigoPage';
import MuestrasPage from './pages/muestras/MuestrasPage';
import MuestraNuevaPage from './pages/muestras/MuestraNuevaPage';
import MuestraDetallePage from './pages/muestras/MuestraDetallePage';
import MuestraEtiquetaPage from './pages/muestras/MuestraEtiquetaPage';
import EnvioFormPage from './pages/muestras/EnvioFormPage';
import RemitoImprimirPage from './pages/muestras/RemitoImprimirPage';
import LaboratoriosPage from './pages/muestras/LaboratoriosPage';
import ImpresorasConfigPage from './pages/muestras/ImpresorasConfigPage';
import CajasPage from './pages/muestras/CajasPage';
import CajaDetallePage from './pages/muestras/CajaDetallePage';
import BusquedaProductoCajasPage from './pages/muestras/BusquedaProductoCajasPage';
import ConsultaMuestrasPage from './pages/muestras/ConsultaMuestrasPage';
import ConsultaMuestraDetallePage from './pages/muestras/ConsultaMuestraDetallePage';
import ResultadosPage from './pages/resultados/ResultadosPage';
import MuestraEnviosDetallePage from './pages/resultados/MuestraEnviosDetallePage';
import CargaResultadosBandejaPage from './pages/resultados/CargaResultadosBandejaPage';
import CargaResultadosPage from './pages/resultados/CargaResultadosPage';
import CargaResultadosOrdenTrabajoPage from './pages/resultados/CargaResultadosOrdenTrabajoPage';
import DictamenesPage from './pages/dictamenes/DictamenesPage';
import DictamenDetallePage from './pages/dictamenes/DictamenDetallePage';
import FacturasPage from './pages/facturas/FacturasPage';
import FacturaFormPage from './pages/facturas/FacturaFormPage';
import FacturaDetallePage from './pages/facturas/FacturaDetallePage';
import ReporteImportesFacturadosPage from './pages/facturas/ReporteImportesFacturadosPage';

// Roles reutilizados en varias rutas -- mismo criterio que usa el backend
// (require_rol) y el menú v2.0, para que "lo que se ve" y "lo que se puede
// abrir por URL" coincidan siempre.
const TODOS = ['muestreador', 'analista_qc', 'qa', 'admin'];
const GESTION = ['analista_qc', 'qa', 'admin']; // todo salvo muestreador
const QA_ADMIN = ['qa', 'admin'];
const ADMIN = ['admin'];

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />

          <Route path="/menu" element={<PrivateRoute roles={TODOS}><DashboardPage /></PrivateRoute>} />
          <Route path="/cambiar-pin" element={<PrivateRoute><CambiarPinPage /></PrivateRoute>} />

          {/* ── Administración (solo admin) ─────────────────────── */}
          <Route path="/admin" element={<PrivateRoute roles={ADMIN}><AdminMenuPage /></PrivateRoute>} />
          <Route path="/usuarios" element={<PrivateRoute roles={ADMIN}><UsuariosPage /></PrivateRoute>} />
          <Route path="/erp-config" element={<PrivateRoute roles={ADMIN}><ErpConfigPage /></PrivateRoute>} />
          <Route path="/subarticulos-config" element={<PrivateRoute roles={ADMIN}><SubarticulosConfigPage /></PrivateRoute>} />
          <Route path="/agente-muestreo" element={<PrivateRoute roles={QA_ADMIN}><AgenteMuestreoPage /></PrivateRoute>} />
          <Route path="/auditoria" element={<PrivateRoute roles={ADMIN}><AuditoriaPage /></PrivateRoute>} />

          {/* ── Definiciones (analista_qc, qa, admin) ───────────── */}
          <Route path="/menu-definiciones" element={<PrivateRoute roles={GESTION}><DefinicionesMenuPage /></PrivateRoute>} />
          <Route path="/menu-reportes" element={<PrivateRoute roles={GESTION}><ReportesMenuPage /></PrivateRoute>} />
          <Route path="/reportes/libro-ingresos" element={<PrivateRoute roles={GESTION}><LibroIngresosPage /></PrivateRoute>} />
          <Route path="/maestros/testigo-categorias" element={<PrivateRoute roles={GESTION}><TestigoCategoriasPage /></PrivateRoute>} />
          <Route path="/maestros/testigo-origenes" element={<PrivateRoute roles={GESTION}><TestigoOrigenesPage /></PrivateRoute>} />

          {/* ── Muestras (analista_qc, qa, admin) ───────────────── */}
          <Route path="/menu-muestras" element={<PrivateRoute roles={GESTION}><MuestrasMenuPage /></PrivateRoute>} />
          <Route path="/impresion-etiquetas" element={<PrivateRoute roles={GESTION}><ImpresionEtiquetasPage /></PrivateRoute>} />

          {/* ── Equipos: Control de Variables (analista_qc, qa, admin) ── */}
          <Route path="/menu-equipos" element={<PrivateRoute roles={GESTION}><EquiposMenuPage /></PrivateRoute>} />
          <Route path="/equipos/nueva-lectura" element={<PrivateRoute roles={GESTION}><NuevaLecturaPage /></PrivateRoute>} />
          <Route path="/equipos/lecturas/:idLectura/editar" element={<PrivateRoute roles={GESTION}><EditarLecturaPage /></PrivateRoute>} />
          <Route path="/equipos/historial" element={<PrivateRoute roles={GESTION}><HistorialLecturasPage /></PrivateRoute>} />
          <Route path="/equipos/grafico" element={<PrivateRoute roles={GESTION}><GraficoTendenciaPage /></PrivateRoute>} />
          <Route path="/equipos/grafico-todas" element={<PrivateRoute roles={GESTION}><GraficoTodasVariablesPage /></PrivateRoute>} />
          <Route path="/equipos/reporte-desviaciones" element={<PrivateRoute roles={GESTION}><ReporteDesviacionesPage /></PrivateRoute>} />
          <Route path="/equipos/dias-sin-registrar" element={<PrivateRoute roles={GESTION}><DiasSinRegistrarPage /></PrivateRoute>} />

          {/* ── Datos Maestros (analista_qc, qa, admin) ─────────── */}
          <Route path="/maestros/especificaciones" element={<PrivateRoute roles={GESTION}><EspecificacionesPage /></PrivateRoute>} />
          <Route path="/maestros/especificaciones/nueva" element={<PrivateRoute roles={GESTION}><EspecificacionFormPage modo="crear" /></PrivateRoute>} />
          <Route path="/maestros/especificaciones/:id" element={<PrivateRoute roles={GESTION}><EspecificacionDetallePage /></PrivateRoute>} />
          <Route path="/maestros/especificaciones/:id/revisar" element={<PrivateRoute roles={GESTION}><EspecificacionFormPage modo="revisar" /></PrivateRoute>} />
          <Route path="/maestros/ensayos" element={<PrivateRoute roles={GESTION}><CatalogoEnsayosPage /></PrivateRoute>} />
          <Route path="/maestros/equipos" element={<PrivateRoute roles={GESTION}><EquiposPage /></PrivateRoute>} />
          <Route path="/maestros/equipos/:id/variables" element={<PrivateRoute roles={GESTION}><EquipoVariablesPage /></PrivateRoute>} />
          <Route path="/maestros/novedades-empaque" element={<PrivateRoute roles={GESTION}><NovedadesEmpaquePage /></PrivateRoute>} />

          <Route path="/maestros/testigos" element={<PrivateRoute roles={GESTION}><TestigosPage /></PrivateRoute>} />
          <Route path="/maestros/testigos/nuevo" element={<PrivateRoute roles={GESTION}><TestigoFormPage modo="crear" /></PrivateRoute>} />
          <Route path="/maestros/testigos/reporte" element={<PrivateRoute roles={GESTION}><ReporteTestigosPage /></PrivateRoute>} />
          <Route path="/maestros/testigos/remitos" element={<PrivateRoute roles={GESTION}><RemitosTestigosPage /></PrivateRoute>} />
          <Route path="/maestros/testigos/remitos/nuevo" element={<PrivateRoute roles={GESTION}><NuevoRemitoTestigoPage /></PrivateRoute>} />
          <Route path="/maestros/testigos/remitos/:id" element={<PrivateRoute roles={GESTION}><RemitoTestigoDetallePage /></PrivateRoute>} />
          <Route path="/maestros/testigos/:id" element={<PrivateRoute roles={GESTION}><TestigoDetallePage /></PrivateRoute>} />
          <Route path="/maestros/testigos/:id/editar" element={<PrivateRoute roles={GESTION}><TestigoFormPage modo="editar" /></PrivateRoute>} />

          <Route path="/muestras/laboratorios" element={<PrivateRoute roles={GESTION}><LaboratoriosPage /></PrivateRoute>} />
          <Route path="/muestras/impresoras" element={<PrivateRoute roles={GESTION}><ImpresorasConfigPage /></PrivateRoute>} />

          {/* ── Archivo de Contramuestras (analista_qc, qa, admin) ──── */}
          <Route path="/cajas" element={<PrivateRoute roles={GESTION}><CajasPage /></PrivateRoute>} />
          <Route path="/cajas/buscar-producto" element={<PrivateRoute roles={GESTION}><BusquedaProductoCajasPage /></PrivateRoute>} />
          <Route path="/cajas/:id" element={<PrivateRoute roles={GESTION}><CajaDetallePage /></PrivateRoute>} />

          {/* ── Muestras: alta y detalle, accesibles a los 4 roles ── */}
          {/* Solicitudes de Muestreo: gestión (QA crea y asigna) es GESTION;
              el muestreador tiene su propia bandeja en /mis-solicitudes-muestreo */}
          <Route path="/solicitudes-muestreo" element={<PrivateRoute roles={GESTION}><SolicitudesMuestreoPage /></PrivateRoute>} />
          <Route path="/mis-solicitudes-muestreo" element={<PrivateRoute roles={['muestreador']}><MisSolicitudesPage /></PrivateRoute>} />
          <Route path="/muestras/nueva" element={<PrivateRoute roles={TODOS}><MuestraNuevaPage /></PrivateRoute>} />
          <Route path="/muestras" element={<PrivateRoute roles={TODOS}><MuestrasPage /></PrivateRoute>} />
          <Route path="/muestras/:id" element={<PrivateRoute roles={TODOS}><MuestraDetallePage /></PrivateRoute>} />
          <Route path="/muestras/:id/etiqueta" element={<PrivateRoute roles={TODOS}><MuestraEtiquetaPage /></PrivateRoute>} />

          {/* ── Envío de Muestras (analista_qc, qa, admin) ──────── */}
          <Route path="/muestras/:id/envio" element={<PrivateRoute roles={GESTION}><EnvioFormPage /></PrivateRoute>} />
          <Route path="/muestras/:id/envios/:idEnvio/remito" element={<PrivateRoute roles={GESTION}><RemitoImprimirPage /></PrivateRoute>} />
          <Route path="/envios" element={<PrivateRoute roles={GESTION}><ResultadosPage /></PrivateRoute>} />
          <Route path="/envios/muestras/:id" element={<PrivateRoute roles={GESTION}><MuestraEnviosDetallePage /></PrivateRoute>} />

          {/* ── Carga de Resultados (analista_qc, qa, admin) ────── */}
          <Route path="/carga-resultados" element={<PrivateRoute roles={GESTION}><CargaResultadosBandejaPage /></PrivateRoute>} />
          <Route path="/envios/:idEnvio/resultados" element={<PrivateRoute roles={GESTION}><CargaResultadosPage /></PrivateRoute>} />
          <Route path="/solicitudes-muestreo/:idSolicitud/orden-trabajo-digital" element={<PrivateRoute roles={TODOS}><CargaResultadosOrdenTrabajoPage /></PrivateRoute>} />

          {/* ── Consulta de Muestras (analista_qc, qa, admin) ───── */}
          <Route path="/consulta-muestras" element={<PrivateRoute roles={GESTION}><ConsultaMuestrasPage /></PrivateRoute>} />
          <Route path="/consulta-muestras/:id" element={<PrivateRoute roles={GESTION}><ConsultaMuestraDetallePage /></PrivateRoute>} />

          {/* ── Control de Calidad (solo qa, admin) ─────────────── */}
          <Route path="/dictamenes" element={<PrivateRoute roles={QA_ADMIN}><DictamenesPage /></PrivateRoute>} />
          <Route path="/dictamenes/muestras/:id" element={<PrivateRoute roles={QA_ADMIN}><DictamenDetallePage /></PrivateRoute>} />

          {/* ── Facturación de Laboratorios (analista_qc, qa, admin) ── */}
          <Route path="/facturas" element={<PrivateRoute roles={GESTION}><FacturasPage /></PrivateRoute>} />
          <Route path="/facturas/nueva" element={<PrivateRoute roles={GESTION}><FacturaFormPage modo="crear" /></PrivateRoute>} />
          <Route path="/facturas/reporte-importes" element={<PrivateRoute roles={GESTION}><ReporteImportesFacturadosPage /></PrivateRoute>} />
          <Route path="/facturas/:id" element={<PrivateRoute roles={GESTION}><FacturaDetallePage /></PrivateRoute>} />
          <Route path="/facturas/:id/editar" element={<PrivateRoute roles={GESTION}><FacturaFormPage modo="editar" /></PrivateRoute>} />

          <Route path="/" element={<Navigate to="/menu" replace />} />
          <Route path="*" element={<Navigate to="/menu" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
