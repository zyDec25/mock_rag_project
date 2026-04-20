import react from '@vitejs/plugin-react'
import { codeInspectorPlugin } from 'code-inspector-plugin'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig(() => {
  return {
    server: {
      port: 5181,
      host: '0.0.0.0',
    },
    resolve: {
      alias: [
        {
          find: /^@\//,
          replacement: '/src/',
        },
      ],
    },

    plugins: [
      react(),
      codeInspectorPlugin({
        bundler: 'vite',
        editor: 'code', // 指定 IDE 为 vscode
      }),
    ],
  }
})
