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
})
