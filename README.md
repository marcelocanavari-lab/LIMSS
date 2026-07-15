# LIMSS — LIMS Simplificado para Gestión de Análisis Externos

Laboratorio Lamar SRL — Control de Calidad / Aseguramiento de la Calidad.

## Stack
- **Backend**: Python 3.11+ / FastAPI / pyodbc
- **Base de datos LIMSS**: SQL Server en LAMARSERVER (lectura/escritura)
- **Base de datos ERP**: GI_LX en LAMARSERVER (solo lectura)
- **Frontend**: React + Vite

## Estructura
```
LIMSS/
├── backend/
│   ├── app/
│   │   ├── api/routes/
│   │   │   └── auth.py       # Login, logout, me, gestión de usuarios
│   │   ├── core/
│   │   │   ├── config.py     # Settings desde .env
│   │   │   └── security.py   # JWT, bcrypt, dependencias auth
│   │   ├── db/
│   │   │   └── connections.py # Conexiones ERP (RO) y LIMSS (RW)
│   │   ├── schemas/
│   │   │   └── auth.py       # Pydantic: login, usuarios
│   │   ├── services/
│   │   │   └── audit.py      # Audit trail inmutable (append-only)
│   │   └── main.py           # App FastAPI + CORS + routers
│   ├── requirements.txt
│   ├── .env.example
│   └── generar_pin_hash.py
└── frontend/
    ├── src/
    │   ├── api/               # Cliente HTTP (fetch) + endpoints por dominio
    │   ├── components/        # TopBar, RequireAuth
    │   ├── context/           # AuthContext
    │   ├── pages/              # LoginPage, MenuPage
    │   └── styles/             # tokens.css, components.css
    ├── package.json
    └── vite.config.js
```

## Roles
- `muestreador` — Operario de depósito/planta: registra muestreo y envío.
- `analista_qc` — Analista de Control de Calidad: carga resultados y protocolos.
- `qa` — Director Técnico / Aseguramiento de la Calidad: revisión y liberación.
- `admin` — Administrador del sistema: usuarios y catálogos maestros.

## Instalación

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate            # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env           # completar con datos reales
uvicorn app.main:app --reload --host 0.0.0.0 --port 8002
```

### Frontend
```bash
cd frontend
npm install
npm run dev                      # sirve en http://localhost:5174
```

## API disponible (Módulo Auth)
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | /api/health | Estado del servidor |
| POST | /api/auth/login | Login con código + PIN |
| POST | /api/auth/logout | Cerrar sesión |
| GET | /api/auth/me | Usuario actual |
| POST | /api/auth/usuarios | Crear usuario (admin) |
| GET | /api/auth/usuarios | Listar usuarios (admin) |
| PUT | /api/auth/usuarios/{id}/estado | Activar/desactivar usuario (admin) |

## Documentación interactiva
Con el servidor corriendo: http://localhost:8002/api/docs

## Base de datos
El esquema se crea con `Docs/LIMSS_crear_BD.sql`. Especificación completa de requisitos
de usuario en `Docs/URS-LIMSS-001.docx`.
