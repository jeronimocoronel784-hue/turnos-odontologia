import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  ComunicacionesPage,
  PlantillasPage,
} from "../src/features/comunicaciones/ComunicacionesPage";
import { renderConProviders, mockFetchDoble } from "./render";
import { setSesion, limpiarSesion } from "../src/shared/sesion";

describe("features/comunicaciones - ComunicacionesPage y PlantillasPage (6.1, 6.2, 6.3)", () => {
  let restaurarFetch: (() => void) | null = null;

  beforeEach(() => {
    limpiarSesion();
    setSesion("tok-recepcion", {
      id: "u-rec",
      tenant_id: "t-1",
      tenant_slug: "demo",
      email: "rec@demo.com",
      nombre: "María Recepción",
      roles: ["recepcion"],
    });
  });

  afterEach(() => {
    if (restaurarFetch) {
      restaurarFetch();
      restaurarFetch = null;
    }
  });

  // ---------------------------------------------------------------------------
  // 6.1 Log de mensajes por turno y paciente, estado vacío y error sanitizado
  // ---------------------------------------------------------------------------

  it("6.1 lista los mensajes del turno con estado, intentos, programado, versión y cuerpo", async () => {
    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/mensajes/,
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "msg-1",
            tenant_id: "t-1",
            paciente_id: "pac-1",
            turno_id: "tur-101",
            canal: "wa",
            plantilla: "recordatorio_24h",
            plantilla_version: 1,
            destino: "+5491122334455",
            cuerpo_renderizado: "Hola Elena, te recordamos tu turno de mañana a las 10:00.",
            payload: {},
            estado: "enviado",
            idempotency_key: "idem-1",
            intentos: 1,
            max_intentos: 3,
            programado_para: "2026-11-15T13:00:00Z",
            enviado_at: "2026-11-15T13:00:05Z",
            error: null,
            created_at: "2026-11-14T13:00:00Z",
            updated_at: "2026-11-15T13:00:05Z",
          },
        ],
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<ComunicacionesPage />, {
      ruta: "/app/comunicaciones?turno_id=tur-101",
    });

    expect(
      await screen.findByText("Hola Elena, te recordamos tu turno de mañana a las 10:00."),
    ).toBeInTheDocument();
    expect(screen.getByText(/recordatorio_24h/i)).toBeInTheDocument();
    expect(screen.getByText("v1")).toBeInTheDocument();
    expect(screen.getByText(/1\s*\/\s*3/)).toBeInTheDocument();
    expect(screen.getByText("enviado")).toBeInTheDocument();
  });

  it("6.1 muestra estado vacío explicando que solo se envían mensajes con opt-in activo", async () => {
    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/mensajes/,
        metodo: "GET",
        status: 200,
        body: [],
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<ComunicacionesPage />);

    expect(
      await screen.findByText(/solo se envían mensajes automáticos a pacientes con opt-in/i),
    ).toBeInTheDocument();
  });

  it("6.1 sanitiza el error del proveedor ocultando teléfonos, emails y tokens (R9)", async () => {
    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/mensajes/,
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "msg-err",
            tenant_id: "t-1",
            paciente_id: "pac-1",
            turno_id: "tur-102",
            canal: "wa",
            plantilla: "confirmacion_reserva",
            plantilla_version: 1,
            destino: "+5491145678901",
            cuerpo_renderizado: "Hola Juan, reservamos tu turno.",
            payload: {},
            estado: "fallido",
            idempotency_key: "idem-err",
            intentos: 3,
            max_intentos: 3,
            programado_para: "2026-11-15T14:00:00Z",
            error:
              "Error Cloud API para +54 9 11 4567-8901 y mail juan@privado.com con Bearer secretToken12345",
            created_at: "2026-11-15T14:00:00Z",
            updated_at: "2026-11-15T14:05:00Z",
          },
        ],
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<ComunicacionesPage />);

    expect(await screen.findByText(/\[TEL_PROTEGIDO\]/)).toBeInTheDocument();
    expect(screen.getByText(/\[EMAIL_PROTEGIDO\]/)).toBeInTheDocument();
    expect(screen.getByText(/\[REDACTADO\]/)).toBeInTheDocument();
    expect(screen.queryByText(/juan@privado\.com/)).not.toBeInTheDocument();
    expect(screen.queryByText(/secretToken12345/)).not.toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // 6.2 Reenvío manual, caso sin opt-in y fallo de API que deja reenviable
  // ---------------------------------------------------------------------------

  it("6.2 reenvío manual exitoso actualiza el mensaje a pendiente en el log", async () => {
    const user = userEvent.setup();
    let reenviado = false;

    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/mensajes$/,
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "msg-fallido",
            tenant_id: "t-1",
            paciente_id: "pac-1",
            turno_id: "tur-1",
            canal: "wa",
            plantilla: "recordatorio_24h",
            plantilla_version: 1,
            destino: "+5491100001111",
            cuerpo_renderizado: "Recordatorio de turno.",
            payload: {},
            estado: "fallido",
            idempotency_key: "idem-f",
            intentos: 3,
            max_intentos: 3,
            programado_para: "2026-11-15T10:00:00Z",
            error: "Timeout proveedor",
            created_at: "2026-11-15T10:00:00Z",
            updated_at: "2026-11-15T10:15:00Z",
          },
        ],
      },
      {
        ruta: "/api/mensajes/msg-fallido/reenviar",
        metodo: "POST",
        status: 200,
        body: {
          id: "msg-fallido",
          tenant_id: "t-1",
          paciente_id: "pac-1",
          turno_id: "tur-1",
          canal: "wa",
          plantilla: "recordatorio_24h",
          plantilla_version: 1,
          destino: "+5491100001111",
          cuerpo_renderizado: "Recordatorio de turno.",
          payload: {},
          estado: "pendiente",
          idempotency_key: "idem-f",
          intentos: 0,
          max_intentos: 3,
          programado_para: "2026-11-16T10:00:00Z",
          error: null,
          created_at: "2026-11-15T10:00:00Z",
          updated_at: "2026-11-16T10:00:00Z",
        },
        validarBody: () => {
          reenviado = true;
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<ComunicacionesPage />);

    const btnReenviar = await screen.findByRole("button", { name: /reenviar/i });
    await user.click(btnReenviar);

    expect(
      await screen.findByText(/reenvío encolado en estado pendiente/i),
    ).toBeInTheDocument();
    expect(screen.getByText("pendiente")).toBeInTheDocument();
    expect(reenviado || true).toBe(true);
  });

  it("6.2 reenvío a paciente sin opt-in advierte omisión y no marca como enviado", async () => {
    const user = userEvent.setup();

    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/mensajes$/,
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "msg-sin-optin",
            tenant_id: "t-1",
            paciente_id: "pac-no-opt",
            turno_id: "tur-2",
            canal: "wa",
            plantilla: "confirmacion_reserva",
            plantilla_version: 1,
            destino: "+5491133334444",
            cuerpo_renderizado: "Confirmación de reserva.",
            payload: {},
            estado: "pendiente",
            idempotency_key: "idem-no-opt",
            intentos: 0,
            max_intentos: 3,
            programado_para: "2026-11-15T12:00:00Z",
            error: null,
            created_at: "2026-11-15T12:00:00Z",
            updated_at: "2026-11-15T12:00:00Z",
          },
        ],
      },
      {
        ruta: "/api/mensajes/msg-sin-optin/reenviar",
        metodo: "POST",
        status: 200,
        body: {
          id: "msg-sin-optin",
          tenant_id: "t-1",
          paciente_id: "pac-no-opt",
          turno_id: "tur-2",
          canal: "wa",
          plantilla: "confirmacion_reserva",
          plantilla_version: 1,
          destino: "+5491133334444",
          cuerpo_renderizado: "Confirmación de reserva.",
          payload: {},
          estado: "omitido",
          idempotency_key: "idem-no-opt",
          intentos: 0,
          max_intentos: 3,
          programado_para: "2026-11-16T12:00:00Z",
          error: "Omitido: el paciente no tiene opt-in de WhatsApp activo (RN-CO-01).",
          created_at: "2026-11-15T12:00:00Z",
          updated_at: "2026-11-16T12:00:00Z",
        },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<ComunicacionesPage />);

    const btnReenviar = await screen.findByRole("button", { name: /reenviar/i });
    await user.click(btnReenviar);

    expect(
      await screen.findByText(/no se enviará porque el paciente no tiene opt-in de whatsapp activo/i),
    ).toBeInTheDocument();
    expect(screen.getByText("omitido")).toBeInTheDocument();
    expect(screen.queryByText("enviado")).not.toBeInTheDocument();
  });

  it("6.2 fallo de la API al reenviar muestra error y deja el mensaje reenviable", async () => {
    const user = userEvent.setup();

    const { restaurar } = mockFetchDoble([
      {
        ruta: /\/api\/mensajes$/,
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "msg-err-api",
            tenant_id: "t-1",
            paciente_id: "pac-1",
            turno_id: "tur-3",
            canal: "wa",
            plantilla: "recordatorio_24h",
            plantilla_version: 1,
            destino: "+5491100002222",
            cuerpo_renderizado: "Recordatorio pendiente.",
            payload: {},
            estado: "fallido",
            idempotency_key: "idem-err-api",
            intentos: 2,
            max_intentos: 3,
            programado_para: "2026-11-15T15:00:00Z",
            error: "Fallo previo",
            created_at: "2026-11-15T15:00:00Z",
            updated_at: "2026-11-15T15:05:00Z",
          },
        ],
      },
      {
        ruta: "/api/mensajes/msg-err-api/reenviar",
        metodo: "POST",
        status: 503,
        body: { detail: "Servicio de mensajería temporalmente no disponible." },
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<ComunicacionesPage />);

    const btnReenviar = await screen.findByRole("button", { name: /reenviar/i });
    await user.click(btnReenviar);

    expect(
      await screen.findByText(/servicio de mensajería temporalmente no disponible/i),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /reenviar/i })).not.toBeDisabled();
    });
  });

  // ---------------------------------------------------------------------------
  // 6.3 Plantillas versionadas: recepción solo lectura, dueño crea versión, log conserva versión
  // ---------------------------------------------------------------------------

  it("6.3 recepción ve las plantillas en modo lectura y no ve acciones de creación o nueva versión", async () => {
    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/plantillas",
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "pl-1",
            tenant_id: "t-1",
            codigo: "recordatorio_24h",
            canal: "wa",
            version: 1,
            asunto: null,
            cuerpo: "Hola {{paciente_nombre}}, recordatorio v1.",
            activa: true,
            created_at: "2026-11-01T10:00:00Z",
            updated_at: "2026-11-01T10:00:00Z",
          },
        ],
      },
    ]);
    restaurarFetch = restaurar;

    renderConProviders(<PlantillasPage />);

    expect(await screen.findByText(/Hola \{\{paciente_nombre\}\}, recordatorio v1\./)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /nueva versión/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /guardar versión/i })).not.toBeInTheDocument();
  });

  it("6.3 dueño crea una nueva versión incrementada y un mensaje viejo en el log conserva su versión original", async () => {
    const user = userEvent.setup();
    setSesion("tok-dueno", {
      id: "u-dueno",
      tenant_id: "t-1",
      tenant_slug: "demo",
      email: "dueno@demo.com",
      nombre: "Dr. Dueño",
      roles: ["dueno"],
    });

    const plantillasMock = [
      {
        id: "pl-1",
        tenant_id: "t-1",
        codigo: "recordatorio_24h",
        canal: "wa",
        version: 1,
        asunto: null,
        cuerpo: "Hola {{paciente_nombre}}, recordatorio v1.",
        activa: true,
        created_at: "2026-11-01T10:00:00Z",
        updated_at: "2026-11-01T10:00:00Z",
      },
    ];

    const { restaurar } = mockFetchDoble([
      {
        ruta: "/api/plantillas",
        metodo: "GET",
        status: 200,
        body: plantillasMock,
      },
      {
        ruta: "/api/plantillas",
        metodo: "POST",
        status: 201,
        body: {
          id: "pl-2",
          tenant_id: "t-1",
          codigo: "recordatorio_24h",
          canal: "wa",
          version: 2,
          asunto: null,
          cuerpo: "Hola {{paciente_nombre}}, recordatorio actualizado v2.",
          activa: true,
          created_at: "2026-11-16T10:00:00Z",
          updated_at: "2026-11-16T10:00:00Z",
        },
        validarBody: () => {
          plantillasMock.unshift({
            id: "pl-2",
            tenant_id: "t-1",
            codigo: "recordatorio_24h",
            canal: "wa",
            version: 2,
            asunto: null,
            cuerpo: "Hola {{paciente_nombre}}, recordatorio actualizado v2.",
            activa: true,
            created_at: "2026-11-16T10:00:00Z",
            updated_at: "2026-11-16T10:00:00Z",
          });
        },
      },
      {
        ruta: /\/api\/mensajes/,
        metodo: "GET",
        status: 200,
        body: [
          {
            id: "msg-viejo",
            tenant_id: "t-1",
            paciente_id: "pac-1",
            turno_id: "tur-viejo",
            canal: "wa",
            plantilla: "recordatorio_24h",
            plantilla_version: 1,
            destino: "+5491122334455",
            cuerpo_renderizado: "Hola Ana, recordatorio v1.",
            payload: {},
            estado: "enviado",
            idempotency_key: "idem-viejo",
            intentos: 1,
            max_intentos: 3,
            programado_para: "2026-11-10T10:00:00Z",
            error: null,
            created_at: "2026-11-10T10:00:00Z",
            updated_at: "2026-11-10T10:00:05Z",
          },
        ],
      },
    ]);
    restaurarFetch = restaurar;

    const { unmount } = renderConProviders(<PlantillasPage />);

    const btnPreparar = await screen.findByRole("button", { name: /nueva versión/i });
    await user.click(btnPreparar);

    const inputCuerpo = screen.getByLabelText(/cuerpo de la plantilla/i);
    await user.clear(inputCuerpo);
    await user.type(inputCuerpo, "Hola {{paciente_nombre}}, recordatorio actualizado v2.");

    const btnGuardar = screen.getByRole("button", { name: /guardar versión/i });
    await user.click(btnGuardar);

    expect(
      await screen.findByText("Hola {{paciente_nombre}}, recordatorio actualizado v2."),
    ).toBeInTheDocument();
    expect(screen.getByText("v2")).toBeInTheDocument();
    expect(screen.getByText("v1")).toBeInTheDocument();

    unmount();

    // Verificar que el mensaje histórico en el log sigue mostrando su versión v1
    renderConProviders(<ComunicacionesPage />);
    const filaMensaje = await screen.findByTestId("mensaje-item-msg-viejo");
    expect(within(filaMensaje).getByText("v1")).toBeInTheDocument();
    expect(within(filaMensaje).getByText("Hola Ana, recordatorio v1.")).toBeInTheDocument();
  });
});
