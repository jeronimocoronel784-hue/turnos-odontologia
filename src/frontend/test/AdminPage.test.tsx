import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  PrestacionesPage,
  SillonesPage,
  CoberturasPage,
  PoliticasPage,
  UsuariosPage,
} from "../src/features/admin/AdminPages";
import { renderConProviders, mockFetchDoble } from "./render";
import { setSesion, limpiarSesion } from "../src/shared/sesion";

describe("features/admin - Prestaciones, Sillones, Coberturas, Políticas y Usuarios (Bloque 5)", () => {
  let restaurarFetch: (() => void) | null = null;

  beforeEach(() => {
    limpiarSesion();
    setSesion("tok-dueno", {
      id: "u-dueno",
      tenant_id: "t-1",
      tenant_slug: "demo",
      email: "dueno@demo.com",
      nombre: "Dr. Dueño",
      roles: ["dueno"],
    });
  });

  afterEach(() => {
    if (restaurarFetch) {
      restaurarFetch();
      restaurarFetch = null;
    }
  });

  // ---------------------------------------------------------------------------
  // 5.2 Prestaciones: alta, validación de seña sin monto y desactivación lógica
  // ---------------------------------------------------------------------------

  it("5.2 ABM de prestaciones valida seña sin monto, crea prestación y desactiva lógicamente", async () => {
    const user = userEvent.setup();
    let llamoPost = false;

    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/prestaciones",
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "pres-1",
            tenant_id: "t-1",
            nombre: "Limpieza",
            duracion_min: 30,
            precio_particular: "15000.00",
            requiere_sena: false,
            monto_sena: null,
            invasiva: false,
            activa: true,
            created_at: "2026-11-01T10:00:00Z",
            updated_at: "2026-11-01T10:00:00Z",
          },
        ],
      },
      {
        ruta: "/api/prestaciones",
        metodo: "POST",
        status: 201,
        body: {
          id: "pres-2",
          tenant_id: "t-1",
          nombre: "Endodoncia Molar",
          duracion_min: 60,
          precio_particular: "60000.00",
          requiere_sena: true,
          monto_sena: "15000.00",
          invasiva: true,
          activa: true,
          created_at: "2026-11-16T10:00:00Z",
          updated_at: "2026-11-16T10:00:00Z",
        },
        validarBody: () => {
          llamoPost = true;
        },
      },
      {
        ruta: "/api/prestaciones/pres-1",
        metodo: "DELETE",
        status: 200,
        body: {
          id: "pres-1",
          tenant_id: "t-1",
          nombre: "Limpieza",
          duracion_min: 30,
          precio_particular: "15000.00",
          requiere_sena: false,
          monto_sena: null,
          invasiva: false,
          activa: false,
          created_at: "2026-11-01T10:00:00Z",
          updated_at: "2026-11-16T10:00:00Z",
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<PrestacionesPage />);
    expect(await screen.findByText("Limpieza")).toBeInTheDocument();

    // 1. Marcar requiere seña sin monto -> validación local
    await user.type(screen.getByLabelText(/nombre de la prestación/i), "Endodoncia Molar");
    await user.clear(screen.getByLabelText(/precio particular/i));
    await user.type(screen.getByLabelText(/precio particular/i), "60000.00");
    await user.click(screen.getByLabelText(/requiere seña/i));
    await user.click(screen.getByRole("button", { name: /crear prestación/i }));

    expect(
      await screen.findByText(/si requiere seña, debés informar un monto de seña mayor a cero/i),
    ).toBeInTheDocument();
    expect(llamoPost).toBe(false);

    // 2. Completar monto seña y enviar -> 201
    await user.type(screen.getByLabelText(/monto de la seña/i), "15000.00");
    await user.click(screen.getByRole("button", { name: /crear prestación/i }));
    expect(await screen.findByText("Endodoncia Molar")).toBeInTheDocument();
    expect(llamoPost).toBe(true);

    // 3. Desactivar Limpieza -> queda visible como Inactiva
    const btnsDesactivar = screen.getAllByRole("button", { name: /desactivar/i });
    await user.click(btnsDesactivar[0]);
    expect(await screen.findByText("Inactiva")).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // 5.3 y 5.4 Sillones (sucursal central default) y Coberturas (vigencia invertida)
  // ---------------------------------------------------------------------------

  it("5.3 y 5.4 Sillones valida nombre y desactiva; Coberturas valida vigencia invertida", async () => {
    const user = userEvent.setup();

    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/sillones",
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "sil-1",
            tenant_id: "t-1",
            nombre: "Box 1",
            sucursal: "central",
            activo: true,
            created_at: "2026-11-01T10:00:00Z",
            updated_at: "2026-11-01T10:00:00Z",
          },
        ],
      },
      {
        ruta: "/api/sillones/sil-1",
        metodo: "DELETE",
        status: 200,
        body: {
          id: "sil-1",
          tenant_id: "t-1",
          nombre: "Box 1",
          sucursal: "central",
          activo: false,
          created_at: "2026-11-01T10:00:00Z",
          updated_at: "2026-11-16T10:00:00Z",
        },
      },
      {
        ruta: "/api/coberturas",
        metodo: "GET",
        status: 200,
        body: [],
      },
    ]);
    restaurarFetch = restaurar;

    const { unmount } = renderConProviders(<SillonesPage />);
    expect(await screen.findByText("Box 1")).toBeInTheDocument();

    // Desactivar sillón -> avisa que no se puede agendar
    await user.click(screen.getByRole("button", { name: /desactivar/i }));
    expect(await screen.findByText(/no disponible para agendar/i)).toBeInTheDocument();
    unmount();

    // Coberturas: vigencia invertida no se envía
    renderConProviders(<CoberturasPage />);
    await user.type(screen.getByLabelText(/obra social del convenio/i), "OSDE");
    await user.type(screen.getByLabelText(/id prestación/i), "pres-1");
    await user.type(screen.getByLabelText(/arancel convenido/i), "20000.00");
    await user.clear(screen.getByLabelText(/vigencia desde/i));
    await user.type(screen.getByLabelText(/vigencia desde/i), "2026-12-01");
    await user.type(screen.getByLabelText(/vigencia hasta/i), "2026-06-01");

    await user.click(screen.getByRole("button", { name: /guardar cobertura/i }));
    expect(
      await screen.findByText(/la fecha de vigencia hasta no puede ser anterior/i),
    ).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // 5.5 Políticas del consultorio: validación de rango y detección de sin cambios
  // ---------------------------------------------------------------------------

  it("5.5 Políticas valida porcentaje 0..100, evita PATCH sin cambios y guarda cambios válidos", async () => {
    const user = userEvent.setup();
    let llamoPatch = false;

    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/tenant/politicas",
        metodo: "GET",
        status: 200,
        body: {
          anticipacion_min_dias: 1,
          sena_default_pct: 30,
          cancelacion_horas: 24,
        },
      },
      {
        ruta: "/api/tenant/politicas",
        metodo: "PATCH",
        status: 200,
        body: {
          anticipacion_min_dias: 1,
          sena_default_pct: 30,
          cancelacion_horas: 48,
        },
        validarBody: () => {
          llamoPatch = true;
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<PoliticasPage />);
    const inputHoras = await screen.findByLabelText(/horas de cancelación sin cargo/i);
    expect(inputHoras).toHaveValue(24);

    // 1. Guardar sin tocar nada -> no dispara PATCH
    await user.click(screen.getByRole("button", { name: /guardar políticas/i }));
    expect(await screen.findByText(/no hay cambios para guardar/i)).toBeInTheDocument();
    expect(llamoPatch).toBe(false);

    // 2. Porcentaje fuera de rango (150) -> validación local
    const inputPct = screen.getByLabelText(/porcentaje de seña por defecto/i);
    await user.clear(inputPct);
    await user.type(inputPct, "150");
    await user.click(screen.getByRole("button", { name: /guardar políticas/i }));
    expect(await screen.findByText(/debe estar entre 0 y 100/i)).toBeInTheDocument();
    expect(llamoPatch).toBe(false);

    // 3. Cambio válido -> PATCH 200
    await user.clear(inputPct);
    await user.type(inputPct, "30");
    await user.clear(inputHoras);
    await user.type(inputHoras, "48");
    await user.click(screen.getByRole("button", { name: /guardar políticas/i }));

    expect(await screen.findByText(/políticas actualizadas correctamente/i)).toBeInTheDocument();
    expect(llamoPatch).toBe(true);
  });

  // ---------------------------------------------------------------------------
  // 5.6 y 5.7 Usuarios (matrícula obligatoria, sin credenciales en DOM, cambio rol) y RBAC
  // ---------------------------------------------------------------------------

  it("5.6 y 5.7 Usuarios exige matrícula para odontólogo, oculta contraseña tras alta, cambia rol y bloquea escritura a recepción", async () => {
    const user = userEvent.setup();

    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/usuarios",
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "u-1",
            tenant_id: "t-1",
            email: "recep@demo.com",
            nombre: "Lucía Recepción",
            rol: "recepcion",
            matricula: null,
            activo: true,
          },
        ],
      },
      {
        ruta: "/api/usuarios",
        metodo: "POST",
        status: 201,
        body: {
          id: "u-2",
          tenant_id: "t-1",
          email: "odonto.nuevo@demo.com",
          nombre: "Dr. Martín",
          rol: "odontologo",
          matricula: "MN-8888",
          activo: true,
        },
      },
      {
        ruta: "/api/usuarios/u-1/rol",
        metodo: "PATCH",
        status: 200,
        body: {
          id: "u-1",
          tenant_id: "t-1",
          email: "recep@demo.com",
          nombre: "Lucía Recepción",
          rol: "dueno",
          matricula: null,
          activo: true,
        },
      },
    ]);
    restaurarFetch = restaurar;

    const { unmount } = renderConProviders(<UsuariosPage />);
    expect(await screen.findByText("Lucía Recepción")).toBeInTheDocument();

    // 1. Odontólogo sin matrícula -> validación local
    await user.type(screen.getByLabelText(/nombre completo/i), "Dr. Martín");
    await user.type(screen.getByLabelText(/correo electrónico/i), "odonto.nuevo@demo.com");
    await user.type(screen.getByLabelText(/contraseña inicial/i), "SuperSecreta99!");
    await user.selectOptions(screen.getByLabelText(/rol en el consultorio/i), "odontologo");

    await user.click(screen.getByRole("button", { name: /crear usuario/i }));
    expect(
      await screen.findByText(/la matrícula profesional es obligatoria para el rol odontólogo/i),
    ).toBeInTheDocument();

    // 2. Completar matrícula y crear -> limpia contraseña y no la muestra en pantalla
    await user.type(screen.getByLabelText(/matrícula profesional/i), "MN-8888");
    await user.click(screen.getByRole("button", { name: /crear usuario/i }));

    expect(await screen.findByText("Dr. Martín")).toBeInTheDocument();
    expect(screen.queryByText("SuperSecreta99!")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/contraseña inicial/i)).toHaveValue("");

    // 3. Recepción ve Prestaciones y Usuarios en modo solo lectura (5.7)
    unmount();
    setSesion("tok-recep", {
      id: "u-rec",
      tenant_id: "t-1",
      tenant_slug: "demo",
      email: "recep@demo.com",
      nombre: "Lucía Recepción",
      roles: ["recepcion"],
    });

    renderConProviders(<UsuariosPage />);
    expect(await screen.findByText(/modo solo lectura/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /crear usuario/i })).not.toBeInTheDocument();
  });
});
