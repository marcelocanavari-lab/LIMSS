import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5174,
    watch: {
      // El proyecto vive en un recurso de red (SMB); los eventos nativos
      // de FS no llegan ahí, hay que sondear en vez de esperar notificaciones.
      usePolling: true,
      interval: 500,
    },
  },
  // "npm run preview" (usado en el servidor) no hereda el puerto de "server" --
  // sin esto usa el default de Vite (4173) y va derivando al siguiente puerto
  // libre si está ocupado. strictPort hace que falle en vez de derivar, para
  // notar enseguida si quedó un preview viejo corriendo en 5174.
  preview: {
    host: '0.0.0.0',
    port: 5174,
    strictPort: true,
  },
})
