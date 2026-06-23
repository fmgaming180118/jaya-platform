import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
    // Load env variables based on mode (development / production)
    const env = loadEnv(mode, process.cwd(), '')

    const isDev = mode === 'development'
    const apiTarget = env.VITE_API_BASE_URL || (isDev ? 'http://localhost:8000' : '')

    return {
        plugins: [react()],
        resolve: {
            alias: {
                '@': path.resolve(__dirname, './src'),
            },
        },
        define: {
            // Make mode globally accessible for runtime checks
            __APP_MODE__: JSON.stringify(mode),
            __APP_VERSION__: JSON.stringify(env.VITE_APP_VERSION || '2.1.0'),
        },
        server: {
            port: isDev ? 5173 : 5174,
            proxy: {
                '/api': {
                    target: isDev ? 'http://localhost:8000' : apiTarget,
                    changeOrigin: true,
                    rewrite: (path) => path.replace(/^\/api/, ''),
                },
            },
        },
        build: {
            outDir: isDev ? 'dist/dev' : 'dist/prod',
            sourcemap: isDev, // Source maps only in DEV build
            minify: isDev ? false : 'esbuild',
        },
    }
})
