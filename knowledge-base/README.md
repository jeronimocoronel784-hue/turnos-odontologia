# turnos-odontologia — Base de Conocimiento

Base de conocimiento generada a partir de `discovery/discovery.md` (18 sistemas relevados) + Q&A confirmadas (kb-creator Mode B, source=interactive).

## Índice de Archivos

| Archivo | Contenido |
|---------|-----------|
| [01_vision_y_objetivos.md](01_vision_y_objetivos.md) | Propósito, objetivos por actor, alcance v1.0, fuera de alcance, métricas |
| [02_descripcion_general.md](02_descripcion_general.md) | Stack (FastAPI+React PWA), arquitectura, integraciones, API REST |
| [03_actores_y_roles.md](03_actores_y_roles.md) | 4 actores, matriz RBAC, rutas públicas |
| [04_modelo_de_datos.md](04_modelo_de_datos.md) | 18 entidades, ERD textual, constraints/índices, seeds |
| [05_reglas_de_negocio.md](05_reglas_de_negocio.md) | RN-AG/LE/PA/OS/CL/CO/SE + excepciones globales |
| [06_funcionalidades.md](06_funcionalidades.md) | Épicas 1–7 MVP + Épica 8 postergada (US + criterios) |
| [07_flujos_principales.md](07_flujos_principales.md) | 7 flujos end-to-end (reserva, WA, atención, cobro, OS, espera, auditoría) |
| [08_arquitectura_propuesta.md](08_arquitectura_propuesta.md) | Patrones, directorios, seguridad, env vars |
| [09_decisiones_y_supuestos.md](09_decisiones_y_supuestos.md) | 7 decisiones (DD) + 6 supuestos (SU) |
| [10_preguntas_abiertas.md](10_preguntas_abiertas.md) | 5 de Discovery resueltas + 4 operativas (PO-01..04) |
| [11_pagos_mercadopago.md](11_pagos_mercadopago.md) | Extra: webhooks, idempotencia, conciliación MP |

## Quick Start para Desarrolladores

1. Entender el dominio → [01](01_vision_y_objetivos.md), [03](03_actores_y_roles.md)
2. Entender los datos → [04](04_modelo_de_datos.md)
3. Entender las reglas → [05](05_reglas_de_negocio.md)
4. Entender la arquitectura → [02](02_descripcion_general.md), [08](08_arquitectura_propuesta.md)
5. Implementar → [07](07_flujos_principales.md), [06](06_funcionalidades.md)
6. Antes de codificar → [10](10_preguntas_abiertas.md)

## Resumen Ejecutivo

SaaS multi-tenant (web + PWA) para consultorios odontológicos argentinos que une agenda anti-solapamiento, reserva 24/7 con seña Mercado Pago, WhatsApp automático honesto, HC/odontograma FDI y liquidación OS sin planilla. Diferencial: seña cobrada + OS local + auditoría verificable desde v1; AFIP nativa e IA quedan para v2.
