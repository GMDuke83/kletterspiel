import { defineConfig } from 'vite';

// Lokal (npm run dev) unter "/", auf GitHub Pages unter "/kletterspiel/".
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/kletterspiel/' : '/',
  build: {
    chunkSizeWarningLimit: 1000, // three.js ist allein schon ~600 KB
  },
}));
