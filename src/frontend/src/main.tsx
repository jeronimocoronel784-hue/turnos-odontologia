import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider, RouteObject } from "react-router-dom";
import { HomePage } from "./pages/HomePage";
import { PaginaLegalPage } from "./features/legal/PaginaLegalPage";
import { ReservaPage } from "./features/reserva-publica/ReservaPage";
import { MiTurnoPage } from "./features/autogestion/MiTurnoPage";
import { PagarSenaPage } from "./features/autogestion/PagarSenaPage";
import { FirmarConsentimientoPage } from "./features/autogestion/FirmarConsentimientoPage";
import { AceptarHuecoPage } from "./features/autogestion/AceptarHuecoPage";
import { LoginPage } from "./features/auth/LoginPage";
import { LayoutInterno } from "./shared/LayoutInterno";
import { requerirSesion } from "./shared/authLoader";
import { AgendaPage } from "./features/agenda/AgendaPage";
import { PacientesPage, PacienteDetallePage } from "./features/pacientes/PacientesPage";
import { FichaClinicaPage } from "./features/clinica/FichaClinicaPage";
import { ComunicacionesPage, PlantillasPage } from "./features/comunicaciones/ComunicacionesPage";
import { CajaPage, CierreDetallePage } from "./features/caja/CajaPage";
import { CobroTurnoPage } from "./features/cobros/CobroTurnoPage";
import {
  LiquidacionesPage,
  LiquidacionDetallePage,
} from "./features/os/LiquidacionesPage";
import {
  PrestacionesPage,
  SillonesPage,
  CoberturasPage,
  PoliticasPage,
  UsuariosPage,
} from "./features/admin/AdminPages";
import { PanelPage } from "./features/panel/PanelPage";
import { AuditoriaPage } from "./features/auditoria/AuditoriaPage";
import { BannerOffline } from "./shared/BannerOffline";
import { crearQueryClient } from "./shared/query-client";
import "./index.css";

export const rutasApp: RouteObject[] = [
  // Rutas públicas de C-15: reserva online, autogestión por token opaco y lista
  // de espera. Todas sin sesión de usuario (RN-SE-03).
  { path: "/", element: <HomePage /> },
  { path: "/privacidad", element: <PaginaLegalPage /> },
  { path: "/reservar/:slug", element: <ReservaPage /> },
  { path: "/mis-turnos/:token", element: <MiTurnoPage /> },
  { path: "/pagar/:token", element: <PagarSenaPage /> },
  { path: "/firmar/:token", element: <FirmarConsentimientoPage /> },
  { path: "/lista-espera/:token", element: <AceptarHuecoPage /> },

  // Login de staff
  { path: "/login", element: <LoginPage /> },

  // Shell interno protegido (C-16 + C-17)
  {
    path: "/app",
    element: <LayoutInterno />,
    loader: requerirSesion,
    children: [
      { path: "agenda", element: <AgendaPage /> },
      { path: "pacientes", element: <PacientesPage /> },
      { path: "pacientes/:id", element: <PacienteDetallePage /> },
      { path: "pacientes/:id/clinica", element: <FichaClinicaPage /> },
      { path: "comunicaciones", element: <ComunicacionesPage /> },
      { path: "comunicaciones/plantillas", element: <PlantillasPage /> },

      // Rutas de C-17: Caja, Cobros, Obras Sociales, Administración y Panel
      { path: "caja", element: <CajaPage /> },
      { path: "caja/cierres/:id", element: <CierreDetallePage /> },
      { path: "cobros/turno/:turnoId", element: <CobroTurnoPage /> },
      { path: "os/liquidaciones", element: <LiquidacionesPage /> },
      { path: "os/liquidaciones/:id", element: <LiquidacionDetallePage /> },
      { path: "admin/prestaciones", element: <PrestacionesPage /> },
      { path: "admin/sillones", element: <SillonesPage /> },
      { path: "admin/coberturas", element: <CoberturasPage /> },
      { path: "admin/politicas", element: <PoliticasPage /> },
      { path: "admin/usuarios", element: <UsuariosPage /> },
      { path: "panel", element: <PanelPage /> },
      { path: "auditoria", element: <AuditoriaPage /> },
    ],
  },
];

export function crearRouter() {
  return createBrowserRouter(rutasApp);
}

const queryClient = crearQueryClient();

const raiz = document.getElementById("root");
if (raiz !== null) {
  const router = crearRouter();
  createRoot(raiz).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        <BannerOffline />
      </QueryClientProvider>
    </StrictMode>,
  );
}
