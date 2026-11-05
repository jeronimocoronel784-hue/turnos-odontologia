import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// PWA base (D7): manifest instalable + service worker generado.
// C-15: se cachea el shell para abrir sin conexión y se fuerza red para la API
// (nunca se cachean respuestas de turnos/pacientes: R6/R9).
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icons/icon-192.png", "icons/icon-512.png"],
      manifest: {
        name: "Turnos Odontología",
        short_name: "Turnos",
        description: "Reservá y gestioná tus turnos odontológicos.",
        theme_color: "#0d6e5f",
        background_color: "#ffffff",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,ico,webmanifest}"],
        // SPA: cualquier navegación cae al shell cacheado, salvo las rutas de API.
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          {
            // Network-first para lecturas: si la red responde, manda la red; si no,
            // se usa una copia corta para tolerar conexiones inestables (design §3).
            urlPattern: /\/api\//,
            handler: "NetworkFirst",
            method: "GET",
            options: {
              cacheName: "api-lecturas",
              networkTimeoutSeconds: 5,
              expiration: { maxEntries: 50, maxAgeSeconds: 300 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            // Las escrituras (reservar, pagar, cancelar) nunca se sirven de caché.
            urlPattern: /\/api\//,
            handler: "NetworkOnly",
            method: "POST",
          },
          {
            urlPattern: /^https:\/\/fonts\.(?:googleapis|gstatic)\.com\//,
            handler: "CacheFirst",
            options: {
              cacheName: "google-fonts",
              expiration: { maxEntries: 10, maxAgeSeconds: 60 * 60 * 24 * 365 },
            },
          },
        ],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
