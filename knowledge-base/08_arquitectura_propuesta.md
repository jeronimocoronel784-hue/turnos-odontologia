# Arquitectura Propuesta

## Patrones aplicados

| Patrón | Dónde se usa | Por qué |
|---|---|---|
| Monolito modular | API FastAPI única (routers por dominio) | Velocidad de entrega; un equipo chico, un deploy |
| Outbox + worker | Mensajes WA/email, vencimientos de seña, reintentos | Sin doble envío/cobro; tolera caídas del proveedor |
| Idempotency keys | Webhooks MP/WA, recordatorios, lista de espera | Reintentos seguros; red y proveedores fallan |
| Máquina de estados explícita | Turno, Seña, Liquidación, Mensaje | Reglas auditables en vez de flags sueltos |
| Append-only audit | Tabla Auditoría + HC/evoluciones inmutables | Cumplimiento Ley 25.326/HCE y confianza |
| Multi-tenant lógico | `tenant_id` en toda tabla de negocio | Piloto con 1 + flag multi real desde día 1 |
| Token público por recurso | Gestión de reserva, pago, firma | Paciente sin login opera seguro |

## Estructura de directorios

```
turnos-odontologia/
├── backend/
│   └── app/
│       ├── domain/            # entidades, máquinas de estado, reglas RN
│       ├── application/       # casos de uso (reservar, confirmar, liquidar...)
│       ├── infrastructure/    # db, repositories, mp_client, wa_client, mailer
│       ├── api/               # routers REST + webhooks + auth JWT
│       ├── workers/           # jobs Redis (mensajes, vencimientos, reintentos)
│       └── tests/
├── frontend/
│   └── src/
│       ├── features/          # agenda, reserva-publica, clinica, caja, os, config
│       ├── shared/            # ui, api-client, auth, pwa
│       └── pages/
├── docker-compose.yml         # api + postgres + redis + worker (+ mailhog dev)
└── knowledge-base/            # este KB
```

**Suposición:** esta estructura se ajusta al crear el repo; lo que no se negocia es la separación domain/application/infrastructure en backend.

## Seguridad

- Autenticación: JWT access corto + refresh con rotación (reúso = revocación); login solo usuarios internos; paciente opera por token público vencible.
- Autorización: RBAC simple rol→permisos enforced en API (no solo UI); tests por matriz §03.
- Validación de input: schemas estrictos (Pydantic v2) en API y webhooks (firma HMAC MP/WA verificada antes de procesar).
- Secrets management: solo variables de entorno (`.env` local, secretos del host en prod); jamás en código/logs; backups cifrados.
- Datos de salud: cifrado en tránsito (TLS), acceso por rol, auditoría total, exportación del paciente, página legal (Ley 25.326 + HCE). **Suposición:** hosting inicial en VPS/Docker local del consultorio o VPS AR a definir (ver 10_preguntas_abiertas).

## Variables de entorno

| Variable | Descripción | Ejemplo | Sensible |
|---|---|---|---|
| `DATABASE_URL` | Conexión PostgreSQL | `postgresql://user:pass@db:5432/turnos` | Y |
| `REDIS_URL` | Conexión Redis | `redis://redis:6379/0` | N |
| `JWT_SECRET` | Firma de tokens | (aleatorio 32+) | Y |
| `JWT_ACCESS_MIN` / `JWT_REFRESH_DAYS` | Vidas útiles | `15` / `30` | N |
| `MP_ACCESS_TOKEN` | Credencial Mercado Pago | `APP_USR-...` | Y |
| `MP_WEBHOOK_SECRET` | Firma webhook MP | (aleatorio) | Y |
| `WA_API_TOKEN` | Token Cloud API WhatsApp | `EAAB...` | Y |
| `WA_PHONE_ID` | ID número emisor | `123456789` | N |
| `WA_WEBHOOK_TOKEN` | Verificación webhook WA | (aleatorio) | Y |
| `SMTP_URL` | Servidor de email | `smtp://...` | Y |
| `FRONT_URL` | URL pública del front (links) | `https://turnos.ejemplo.com` | N |
| `TENANT_SLUG_DEFAULT` | Slug del piloto | `consultorio-piloto` | N |
