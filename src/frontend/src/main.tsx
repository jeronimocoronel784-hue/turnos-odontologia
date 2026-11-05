import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { HomePage } from "./pages/HomePage";
import { ReservaPage } from "./features/reserva-publica/ReservaPage";
import { MiTurnoPage } from "./features/autogestion/MiTurnoPage";
import { PagarSenaPage } from "./features/autogestion/PagarSenaPage";
import { FirmarConsentimientoPage } from "./features/autogestion/FirmarConsentimientoPage";
import { AceptarHuecoPage } from "./features/autogestion/AceptarHuecoPage";
import { BannerOffline } from "./shared/BannerOffline";
import { crearQueryClient } from "./shared/query-client";
import "./index.css";

// Rutas públicas de C-15: reserva online, autogestión por token opaco y lista
// de espera. Todas sin sesión de usuario (RN-SE-03).
const router = createBrowserRouter([
  { path: "/", element: <HomePage /> },
  { path: "/reservar/:slug", element: <ReservaPage /> },
  { path: "/mis-turnos/:token", element: <MiTurnoPage /> },
  { path: "/pagar/:token", element: <PagarSenaPage /> },
  { path: "/firmar/:token", element: <FirmarConsentimientoPage /> },
  { path: "/lista-espera/:token", element: <AceptarHuecoPage /> },
]);

const queryClient = crearQueryClient();

const raiz = document.getElementById("root");
if (raiz === null) {
  throw new Error("Falta el elemento #root en index.html.");
}
createRoot(raiz).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <BannerOffline />
    </QueryClientProvider>
  </StrictMode>,
);
