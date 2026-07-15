/* ============================================================
   Cliente API central
   ------------------------------------------------------------
   La URL del backend se resuelve dinámicamente: en producción
   (equipo apuntando al servidor por IP) usamos el mismo host
   donde se sirve la app, puerto 8002. En desarrollo local se
   puede sobreescribir con VITE_API_URL en un .env del frontend.
   ============================================================ */

const API_BASE =
  import.meta.env.VITE_API_URL ||
  `${window.location.protocol}//${window.location.hostname}:8002`;

const TOKEN_KEY = 'limss_token';

export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function request(path, { method = 'GET', body, auth = true } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (auth) {
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new ApiError('No se pudo conectar con el servidor. Verificá la red.', 0, null);
  }

  if (res.status === 204) return null;

  let data = null;
  try {
    data = await res.json();
  } catch {
    // respuesta sin body
  }

  if (!res.ok) {
    if (res.status === 401) {
      clearToken();
    }
    let msg = `Error ${res.status}`;
    if (typeof data?.detail === 'string') {
      msg = data.detail;
    } else if (Array.isArray(data?.detail)) {
      msg = data.detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
    }
    throw new ApiError(msg, res.status, data?.detail);
  }

  return data;
}

async function requestForm(path, formData, { method = 'POST' } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, { method, headers, body: formData });
  } catch (e) {
    throw new ApiError('No se pudo conectar con el servidor. Verificá la red.', 0, null);
  }

  let data = null;
  try {
    data = await res.json();
  } catch {
    // respuesta sin body
  }

  if (!res.ok) {
    if (res.status === 401) clearToken();
    let msg = `Error ${res.status}`;
    if (typeof data?.detail === 'string') {
      msg = data.detail;
    } else if (Array.isArray(data?.detail)) {
      msg = data.detail.map((d) => d.msg || JSON.stringify(d)).join('; ');
    }
    throw new ApiError(msg, res.status, data?.detail);
  }

  return data;
}

async function requestBlob(path) {
  const headers = {};
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, { headers });
  } catch (e) {
    throw new ApiError('No se pudo conectar con el servidor. Verificá la red.', 0, null);
  }
  if (!res.ok) {
    if (res.status === 401) clearToken();
    throw new ApiError(`Error ${res.status}`, res.status, null);
  }
  return res.blob();
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body }),
  put: (path, body) => request(path, { method: 'PUT', body }),
  del: (path) => request(path, { method: 'DELETE' }),
  postPublic: (path, body) => request(path, { method: 'POST', body, auth: false }),
  postForm: (path, formData) => requestForm(path, formData),
  getBlob: (path) => requestBlob(path),
};

export { ApiError };
