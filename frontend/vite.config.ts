import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Serve the dev server and the production preview on port 6200.
  server: { port: 6200, strictPort: true },
  preview: { port: 6200, strictPort: true },
})
