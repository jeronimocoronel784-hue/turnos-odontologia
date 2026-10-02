# Descripción General

## Stack tecnológico

| Capa | Tecnologías | Versión mínima |
|---|---|---|
| Frontend | React + TypeScript + Vite (+ Vite PWA plugin) | React 18, TS 5, Vite 5 |
| Backend | Python FastAPI + SQLAlchemy | Python 3.12, FastAPI 0.110+ |
| Base de datos | PostgreSQL (aislación por `tenant_id`; RLS opcional a futuro) | PostgreSQL 15 |
| Colas / caché | Redis + worker (RQ/Celery o ARQ) | Redis 7 |
| Auth | JWT access + refresh con rotación | — |
| Infra local | Docker + Docker Compose | Docker 24 / Compose v2 |
| Pagos | Mercado Pago SDK + webhooks (Checkout/Links/QR) | API v1 vigente |
| Mensajería | WhatsApp Business API oficial + SMTP transaccional | Cloud API v18+ |
| Exportación | CSV/JSON generados en backend | — |

Sin cloud obligatoria: Docker Compose levanta todo en local primero (piloto con 1 consultorio); cloud (VPS) solo cuando el negocio lo pida.

## Arquitectura general

```
Paciente (PWA/móvil) ──┐
Recepción (web/PWA) ───┼──► Frontend React+Vite (SPA + PWA) ──► API FastAPI ──► PostgreSQL
Odontólogo (web/PWA) ──┘                                              │            Redis (colas)
                                                                      ├──► WA Business API (recordatorios)
                                                                      ├──► Mercado Pago (señas/cobros, webhooks)
                                                                      └──► SMTP (email transaccional)
```

Monolito API + front desacoplado: un solo backend FastAPI expone REST para la SPA/PWA y los webhooks públicos; PostgreSQL es la única fuente de verdad; Redis encola mensajes y jobs (recordatorios, expiraciones de seña, reintentos) con idempotencia. **Suposición:** el volumen del piloto y de los primeros tenants cabe holgadamente en un monolito; se parte en servicios solo si una cola o el webhook de pagos lo exige.

Multi-tenant desde el día 1 a nivel lógico: toda tabla de negocio lleva `tenant_id`; el piloto opera con 1 tenant y el flag multi queda elemental pero real (aislación por filtro + tests).

## Integraciones externas

| Servicio | Propósito | Tipo |
|---|---|---|
| WhatsApp Business API (oficial) | Recordatorios, confirmación con botones, avisos de hueco | REST + webhooks entrantes |
| SMTP transaccional | Email de confirmación/recordatorio y comprobantes | SMTP / API |
| Mercado Pago | Señas y cobros (link/QR), conciliación | SDK + webhooks |
| Exportación CSV/JSON | Liquidaciones OS, reportes, portabilidad | Descarga generada por API |
| (v2) AFIP/ARCA | Facturación electrónica nativa | A definir |
| (v2) Google Calendar | Sincronización bidireccional | OAuth + REST |

## API REST (si aplica)

Agrupada por recurso (prefijo `/api/v1`, todo bajo JWT salvo rutas públicas):

- `auth`: login, refresh con rotación, logout, cambio de clave.
- `tenants/config`: prestaciones, duraciones, precios, sillones, horarios, políticas (anticipación, seña), OS/padrón.
- `pacientes`: CRUD + búsqueda por DNI, opt-in WA, adjuntos.
- `agenda`: slots disponibles (público), turnos CRUD, estados, bloqueos, sobreturnos, reprogramación, lista de espera.
- `clinica`: fichas, anamnesis, odontograma (piezas/eventos), evoluciones, presupuestos, consentimientos.
- `caja`: movimientos, cierres, señas, cobros MP (creación + webhook), liquidaciones OS.
- `mensajes`: plantillas, outbox, logs de envío, webhooks WA.
- `auditoria` / `export`: consultas append-only y descargas CSV/JSON.
- Rutas públicas (sin JWT): disponibilidad, reserva, gestión de reserva por token, webhook MP, webhook WA, confirmación por token.
