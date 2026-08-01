import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
    // Load env variables based on mode (development / production)
    const env = loadEnv(mode, process.cwd(), '')

    const isDev = mode === 'development'
    const apiTarget = env.JAYA_UI_API_TARGET || 'http://127.0.0.1:8000'
    const apiProxy = {
        '/api': {
            target: apiTarget,
            changeOrigin: true,
            rewrite: (requestPath) => requestPath.replace(/^\/api/, ''),
        },
    }

    return {
        plugins: [react()],
        resolve: {
            alias: {
                '@': path.resolve(import.meta.dirname, './src'),
            },
        },
        define: {
            // Make mode globally accessible for runtime checks
            __APP_MODE__: JSON.stringify(mode),
            __APP_VERSION__: JSON.stringify(env.VITE_APP_VERSION || '2.1.0'),
        },
        server: {
            port: isDev ? 5173 : 5174,
            proxy: apiProxy,
        },
        preview: {
            host: '127.0.0.1',
            port: 5174,
            strictPort: true,
            proxy: apiProxy,
        },
        build: {
            outDir: isDev ? 'dist/dev' : 'dist/prod',
            sourcemap: isDev, // Source maps only in DEV build
            minify: !isDev,
        },
    }
})
