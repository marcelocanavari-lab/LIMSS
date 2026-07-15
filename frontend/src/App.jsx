import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import RequireAuth from './components/RequireAuth';

import LoginPage from './pages/LoginPage';
import MenuPage from './pages/MenuPage';
import EspecificacionesPage from './pages/maestros/EspecificacionesPage';
import EspecificacionFormPage from './pages/maestros/EspecificacionFormPage';
import EspecificacionDetallePage from './pages/maestros/EspecificacionDetallePage';
import TestigosPage from './pages/maestros/TestigosPage';
import TestigoFormPage from './pages/maestros/TestigoFormPage';
import TestigoDetallePage from './pages/maestros/TestigoDetallePage';
import MuestrasPage from './pages/muestras/MuestrasPage';
import MuestraNuevaPage from './pages/muestras/MuestraNuevaPage';
import MuestraDetallePage from './pages/muestras/MuestraDetallePage';
import MuestraEtiquetaPage from './pages/muestras/MuestraEtiquetaPage';
import EnvioFormPage from './pages/muestras/EnvioFormPage';
import RemitoImprimirPage from './pages/muestras/RemitoImprimirPage';
import LaboratoriosPage from './pages/muestras/LaboratoriosPage';
import ResultadosPage from './pages/resultados/ResultadosPage';
import CargaResultadosPage from './pages/resultados/CargaResultadosPage';
import DictamenesPage from './pages/dictamenes/DictamenesPage';
import DictamenDetallePage from './pages/dictamenes/DictamenDetallePage';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />

          <Route
            path="/menu"
            element={
              <RequireAuth>
                <MenuPage />
              </RequireAuth>
            }
          />

          <Route path="/maestros/especificaciones" element={<RequireAuth><EspecificacionesPage /></RequireAuth>} />
          <Route path="/maestros/especificaciones/nueva" element={<RequireAuth><EspecificacionFormPage modo="crear" /></RequireAuth>} />
          <Route path="/maestros/especificaciones/:id" element={<RequireAuth><EspecificacionDetallePage /></RequireAuth>} />
          <Route path="/maestros/especificaciones/:id/revisar" element={<RequireAuth><EspecificacionFormPage modo="revisar" /></RequireAuth>} />

          <Route path="/maestros/testigos" element={<RequireAuth><TestigosPage /></RequireAuth>} />
          <Route path="/maestros/testigos/nuevo" element={<RequireAuth><TestigoFormPage modo="crear" /></RequireAuth>} />
          <Route path="/maestros/testigos/:id" element={<RequireAuth><TestigoDetallePage /></RequireAuth>} />
          <Route path="/maestros/testigos/:id/editar" element={<RequireAuth><TestigoFormPage modo="editar" /></RequireAuth>} />

          <Route path="/muestras/laboratorios" element={<RequireAuth><LaboratoriosPage /></RequireAuth>} />
          <Route path="/muestras/nueva" element={<RequireAuth><MuestraNuevaPage /></RequireAuth>} />
          <Route path="/muestras" element={<RequireAuth><MuestrasPage /></RequireAuth>} />
          <Route path="/muestras/:id" element={<RequireAuth><MuestraDetallePage /></RequireAuth>} />
          <Route path="/muestras/:id/etiqueta" element={<RequireAuth><MuestraEtiquetaPage /></RequireAuth>} />
          <Route path="/muestras/:id/envio" element={<RequireAuth><EnvioFormPage /></RequireAuth>} />
          <Route path="/muestras/:id/remito" element={<RequireAuth><RemitoImprimirPage /></RequireAuth>} />

          <Route path="/resultados" element={<RequireAuth><ResultadosPage /></RequireAuth>} />
          <Route path="/resultados/muestras/:id" element={<RequireAuth><CargaResultadosPage /></RequireAuth>} />

          <Route path="/dictamenes" element={<RequireAuth><DictamenesPage /></RequireAuth>} />
          <Route path="/dictamenes/muestras/:id" element={<RequireAuth><DictamenDetallePage /></RequireAuth>} />

          <Route path="/" element={<Navigate to="/menu" replace />} />
          <Route path="*" element={<Navigate to="/menu" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
