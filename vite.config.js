import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ command }) => ({
  plugins: [react()],
  // GitHub Pages serves the app under /wpr-river-conditions/, but the dev server
  // (and the Claude preview) lands on "/". Use the subpath only for the build.
  base: command === 'build' ? '/wpr-river-conditions/' : '/',
  // Honor the PORT env var so external launchers (e.g. the Claude preview) can
  // pin the dev server to the port they assign. Falls back to Vite's default.
  server: process.env.PORT ? { port: Number(process.env.PORT), strictPort: true } : undefined,
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
}));
