import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Serve the dev server and the production preview on port 6200.
  server: {
    port: 6200,
    strictPort: true,
    // In development the UI runs here (6200) and the backend on 6500.
    // Forward every "/api" request to the backend so the frontend can use
    // relative URLs — the same ones that work in production.
    proxy: {
      "/api": "http://127.0.0.1:6500",
    },
  },
  preview: { port: 6200, strictPort: true },
})
