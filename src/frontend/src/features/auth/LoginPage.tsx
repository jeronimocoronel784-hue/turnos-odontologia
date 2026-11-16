import React, { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { loginStaff } from "./api";
import { ErrorApi } from "../../shared/api-client";

export function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const destino = searchParams.get("destino") || "/app/agenda";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantSlug, setTenantSlug] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const emailLimpio = email.trim();
    if (!emailLimpio || !password) {
      setError("Por favor completá tu email y contraseña.");
      return;
    }

    try {
      setCargando(true);
      await loginStaff({
        email: emailLimpio,
        password,
        tenant_slug: tenantSlug.trim() || undefined,
      });
      navigate(destino, { replace: true });
    } catch (err) {
      if (err instanceof ErrorApi) {
        if (err.status === 401) {
          setError("Email o contraseña incorrectos.");
        } else if (err.status === 429) {
          setError("Demasiados intentos. Por favor esperá unos minutos antes de reintentar.");
        } else {
          setError(err.detalle || "Ocurrió un error al iniciar sesión.");
        }
      } else {
        setError("No se pudo conectar con el servidor. Revisá tu conexión.");
      }
    } finally {
      setCargando(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <h2 className="text-center text-3xl font-extrabold text-slate-900 tracking-tight">
          Consultorio Odontológico
        </h2>
        <p className="mt-2 text-center text-sm text-slate-600">
          Ingreso exclusivo para profesionales y personal del consultorio
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10 border border-slate-200">
          <form className="space-y-6" onSubmit={handleSubmit} noValidate>
            {error && (
              <div
                role="alert"
                className="p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-md"
              >
                {error}
              </div>
            )}

            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-slate-700"
              >
                Email
              </label>
              <div className="mt-1">
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={cargando}
                  className="appearance-none block w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm placeholder-slate-400 focus:outline-none focus:ring-emerald-500 focus:border-emerald-500 sm:text-sm"
                  placeholder="ejemplo@consultorio.com"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-slate-700"
              >
                Contraseña
              </label>
              <div className="mt-1">
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={cargando}
                  className="appearance-none block w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm placeholder-slate-400 focus:outline-none focus:ring-emerald-500 focus:border-emerald-500 sm:text-sm"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="tenant_slug"
                className="block text-sm font-medium text-slate-700"
              >
                Identificador de consultorio (opcional)
              </label>
              <div className="mt-1">
                <input
                  id="tenant_slug"
                  name="tenant_slug"
                  type="text"
                  value={tenantSlug}
                  onChange={(e) => setTenantSlug(e.target.value)}
                  disabled={cargando}
                  className="appearance-none block w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm placeholder-slate-400 focus:outline-none focus:ring-emerald-500 focus:border-emerald-500 sm:text-sm"
                  placeholder="Solo si tu email opera en más de uno"
                />
              </div>
            </div>

            <div>
              <button
                type="submit"
                disabled={cargando}
                className="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500 disabled:opacity-50"
              >
                {cargando ? "Ingresando..." : "Ingresar"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
