/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            fontFamily: {
                sans: ['Plus Jakarta Sans', 'Inter', 'sans-serif'],
                display: ['Plus Jakarta Sans', 'sans-serif'],
                mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
            },
            colors: {
                notebook: {
                    bg: '#0b0c10',        // Deep Charcoal Black
                    sidebar: '#0e1017',   // Sidebar surface
                    card: '#12141d',      // Card surface
                    hover: '#181b27',     // Hover state
                    border: 'rgba(255, 255, 255, 0.08)',
                    text: {
                        primary: '#f8fafc',
                        secondary: '#94a3b8',
                        accent: '#38bdf8',
                        success: '#34d399',
                        warning: '#fbbf24',
                        error: '#f87171',
                    }
                }
            },
            boxShadow: {
                'subtle': '0 4px 20px 0 rgba(0, 0, 0, 0.35)',
                'linear': '0 10px 30px -10px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255, 255, 255, 0.08)',
            }
        },
    },
    plugins: [
        require('@tailwindcss/typography'),
    ],
}
