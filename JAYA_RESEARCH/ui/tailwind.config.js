/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            fontFamily: {
                sans: ['Inter', 'sans-serif'],
                mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
            },
            colors: {
                // Google Notebook LLM Dark Theme Inspiration
                notebook: {
                    bg: '#0f1014',     // Very dark background
                    sidebar: '#181a1f', // Slightly lighter sidebar
                    card: '#1e2025',    // Card background
                    hover: '#2a2d35',   // Hover state
                    border: '#2e3138',  // Subtle borders
                    text: {
                        primary: '#e3e3e3',
                        secondary: '#a8a8a8',
                        accent: '#8ab4f8', // Google Blue-ish accent
                        success: '#81c995',
                        warning: '#fdd663',
                        error: '#f28b82',
                    }
                }
            },
            boxShadow: {
                'glow': '0 0 20px rgba(138, 180, 248, 0.15)',
                'card': '0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.15)',
            },
            animation: {
                'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
            }
        },
    },
    plugins: [
        require('@tailwindcss/typography'),
    ],
}
