# Preguntas Abiertas

## Inconsistencias detectadas

Ninguna pendiente entre Discovery y Q&A: las 5 preguntas del Anexo §11 quedaron resueltas por las respuestas confirmadas (ver abajo). No hay `[DISCOVERY]` bloqueante.

## Preguntas abiertas (priorizadas)

| Prioridad | Pregunta | Bloquea | Decisor | Resolución adoptada |
|---|---|---|---|---|
| Alta | ¿Mono-consultorio vs multi-sucursal desde día 1? | Modelo de datos | Dueño | Resuelta: mono + flag multi elemental (multi-tenant lógico, campo `sucursal`, piloto con 1). |
| Alta | ¿Paciente sin login (DNI+tel) vs cuenta? | Reserva pública | Producto | Resuelta: sin login en v1 (token de gestión por turno). |
| Alta | ¿Seña obligatoria siempre o por prestación/primera vez? | Pagos | Dueño | Resuelta: configurable por prestación (`requiere_sena` + `monto_sena`). |
| Media | ¿Alcance OS v1: solo cálculo + liquidación exportable? | Módulo OS | Producto | Resuelta: sí, sin presentación electrónica (v2). |
| Media | ¿Stack y hosting? | Sprint 1 | Tech Lead | Resuelta: FastAPI + SQLAlchemy + Postgres + Redis + React/TS/Vite PWA + Docker Compose; Docker local primero, cloud sin definir (ver PO-01). |
| Media | PO-01 — ¿Hosting definitivo (VPS AR vs Docker en consultorio)? | Deploy piloto | Dueño + Tech | Abierta: arrancar Docker local; decidir VPS antes del segundo tenant. |
| Baja | PO-02 — ¿Costo WA por mensaje y quién lo absorbe? | Pricing | Dueño | Abierta: relevar tarifa Cloud API AR y definir si se traslada o incluye. |
| Baja | PO-03 — ¿Plazo de retención legal exacto de HC/auditoría? | Legal | Asesor | Abierta: se adoptan 5 años por prudencia hasta dictamen. |
| Baja | PO-04 — ¿Precios ARS del SaaS y plan por sillón/profesional? | Comercial | Dueño | Abierta: definir antes del piloto con referencia Odontoly/Clinic Cloud. |
