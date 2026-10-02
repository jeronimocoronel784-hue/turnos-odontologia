# Turnos Consultorio Odontología

SaaS de gestión odontológica con foco en **turnos y agenda de pacientes** para
consultorios y clínicas de Argentina y Latinoamérica.

> 📌 Este README evoluciona con el proyecto: a medida que avancemos se amplía
> con instalación, uso y documentación de cada entrega.

## El problema

Los consultorios gestionan agenda, historia clínica/odontograma, cobros/obras
sociales y comunicación con herramientas desconectadas (WhatsApp manual,
Excel/papel, sistemas legacy o SaaS extranjeros sin OS, AFIP/ARCA ni Mercado
Pago). Eso genera dobles reservas, ausentismo sin recupero, huecos sin
rellenar, doble carga administrativa y pérdida de trazabilidad clínica y
financiera.

## La oportunidad

El análisis competitivo (`discovery/discovery.md`, 18 sistemas relevados)
muestra que **nadie combina** obras sociales/prepagas + facturación AFIP/ARCA +
Mercado Pago + WhatsApp automático + precio en ARS. Ese combo es el hueco a
ocupar.

## MVP (alcance v1)

- Agenda multi-profesional / multi-sillón con anti-solapamiento, sobreturnos
  explícitos y bloqueos
- Reserva online 24/7 + confirmación / cancelación / reprogramación + lista
  de espera
- Recordatorios y confirmación automática por WhatsApp Business API + email
- Ficha clínica + anamnesis + odontograma FDI + presupuestos y planes
- Caja diaria + señas vinculadas al turno + Mercado Pago + cálculo de
  cobertura OS vs particular + liquidación exportable
- Roles y permisos + auditoría append-only + exportación de datos

Para v2: facturación electrónica AFIP/ARCA nativa, periodontograma avanzado,
recepcionista IA por voz, campañas de recuperación, push/in-app.

## Stack

| Capa | Tecnología |
|------|------------|
| Backend | Python + FastAPI + JWT + SQLAlchemy |
| Base de datos | PostgreSQL (multi-tenant) |
| Colas / async | Redis |
| Frontend | React + TypeScript + Vite (PWA instalable en móvil y desktop) |
| Infra | Docker / Docker Compose |

## Estructura del repo

```text
discovery/            Análisis competitivo y de mercado (18 sistemas)
knowledge-base/       Base de conocimiento canónica (visión, datos, reglas, flujos…)
CHANGES.md            Índice operativo de implementación (17 changes, 7 fases)
openspec/             Specs y changes de OpenSpec
.atl/skill-registry.md  Skills disponibles y sus reglas compactas
```

## Roadmap

`CHANGES.md` organiza la implementación en **17 changes** en 7 fases, con
camino crítico de 9 changes:

`C-01 foundation → C-02 modelos core → C-03 auth/RBAC → C-05 pacientes →
C-06 agenda → C-09 HC/odontograma → C-11 caja/señas → C-12 Mercado Pago →
C-15 reserva pública PWA`

Primer change: `/opsx:propose C-01-foundation-setup`

## Estado actual

Fundación en curso (orquestador `active-orchestrator`):

- [x] Discovery de mercado
- [x] Knowledge base
- [x] Roadmap (`CHANGES.md`)
- [x] Skills + registry
- [ ] Reglas del proyecto (`CLAUDE.md`/`AGENTS.md`) — siguiente paso
- [ ] Implementación C-01 en adelante

## Gobierno de datos sensibles

Auditoría append-only en turnos/HC/caja, historia clínica sin borrado físico,
consentimiento firmado antes de prestaciones invasivas y opt-in obligatorio
para WhatsApp (Ley 25.326 + HCE).
