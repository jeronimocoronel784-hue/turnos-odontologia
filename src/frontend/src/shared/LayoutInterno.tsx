import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { getIdentidad } from "./sesion";
import { permite } from "./rbac";
import { logoutStaff } from "../features/auth/api";

export function LayoutInterno() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const usuario = getIdentidad();
  const roles = usuario?.roles || [];

  async function handleLogout() {
    await logoutStaff();
    queryClient.clear();
    navigate("/login", { replace: true });
  }

  const navItems = [
    {
      ruta: "/app/panel",
      etiqueta: "Panel",
      visible: permite(roles, "agenda", "leer"),
    },
    {
      ruta: "/app/agenda",
      etiqueta: "Agenda",
      visible: permite(roles, "agenda", "leer"),
    },
    {
      ruta: "/app/pacientes",
      etiqueta: "Pacientes",
      visible: permite(roles, "pacientes", "leer"),
    },
    {
      ruta: "/app/caja",
      etiqueta: "Caja",
      visible: permite(roles, "caja", "leer"),
    },
    {
      ruta: "/app/os/liquidaciones",
      etiqueta: "Obras Sociales",
      visible: permite(roles, "liquidaciones", "leer"),
    },
    {
      ruta: "/app/comunicaciones",
      etiqueta: "Comunicaciones",
      visible: permite(roles, "mensajes", "leer"),
    },
    {
      ruta: "/app/admin/prestaciones",
      etiqueta: "Administración",
      visible: permite(roles, "configuracion", "leer"),
    },
    {
      ruta: "/app/auditoria",
      etiqueta: "Auditoría",
      visible: permite(roles, "auditoria", "leer"),
    },
  ];

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col">
      {/* Header superior */}
      <header className="bg-slate-900 text-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16 items-center">
            <div className="flex items-center space-x-3">
              <Link
                to="/app/agenda"
                className="text-lg font-bold tracking-tight text-white flex items-center gap-2"
              >
                <span className="w-8 h-8 rounded-lg bg-emerald-500 flex items-center justify-center text-slate-900 font-extrabold text-xl">
                  🦷
                </span>
                <span>Consultorio Odontológico</span>
              </Link>
              {usuario?.tenant_slug && (
                <span className="text-xs bg-slate-800 text-slate-300 px-2 py-0.5 rounded-full border border-slate-700">
                  {usuario.tenant_slug}
                </span>
              )}
            </div>

            <div className="flex items-center space-x-4">
              <div className="text-right hidden sm:block">
                <div className="text-sm font-medium text-slate-200">{usuario?.nombre}</div>
                <div className="text-xs text-slate-400 capitalize">
                  {roles.join(", ")}
                </div>
              </div>
              <button
                type="button"
                onClick={handleLogout}
                className="text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-md border border-slate-700 transition"
              >
                Cerrar sesión
              </button>
            </div>
          </div>
        </div>

        {/* Barra de navegación */}
        <nav className="bg-slate-800 border-t border-slate-700">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex space-x-1 overflow-x-auto py-1">
            {navItems
              .filter((item) => item.visible)
              .map((item) => (
                <NavLink
                  key={item.ruta}
                  to={item.ruta}
                  className={({ isActive }) =>
                    `px-3 py-2 rounded-md text-sm font-medium transition ${
                      isActive
                        ? "bg-slate-950 text-white shadow-inner"
                        : "text-slate-300 hover:bg-slate-700 hover:text-white"
                    }`
                  }
                >
                  {item.etiqueta}
                </NavLink>
              ))}
          </div>
        </nav>
      </header>

      {/* Contenido principal */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 lg:p-8">
        <Outlet />
      </main>

      {/* Pie */}
      <footer className="bg-slate-900 text-slate-400 text-xs py-3 text-center">
        <Link to="/privacidad" className="hover:text-white underline">
          Privacidad
        </Link>
      </footer>
    </div>
  );
}
