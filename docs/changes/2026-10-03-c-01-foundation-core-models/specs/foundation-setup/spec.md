# Spec Delta

## Purpose

Provee el esqueleto ejecutable del sistema (API mínima, frontend PWA base e infraestructura local) sobre el que se construyen todos los changes posteriores.

## ADDED Requirements

### Requirement: Health check público de la API

El sistema SHALL exponer `GET /api/health` sin autenticación, que responde el estado de la API y su conectividad con PostgreSQL y Redis.

#### Scenario: API sana responde ok

- **Dado** que la API está corriendo con PostgreSQL y Redis disponibles
- **Cuando** un cliente hace `GET /api/health`
- **Entonces** responde HTTP 200 con estado ok de API, base de datos y Redis

#### Scenario: Base de datos caída se reporta como error de negocio

- **Dado** que PostgreSQL no está reachable
- **Cuando** un cliente hace `GET /api/health`
- **Entonces** responde HTTP 503 con un mensaje en español rioplatense indicando qué revisar, sin exponer stack traces ni datos sensibles

### Requirement: Configuración solo por variables de entorno

El sistema SHALL leer toda configuración sensible (credenciales DB, JWT, MP, WA, SMTP) desde variables de entorno documentadas en `.env.example`; el arranque MUST fallar en forma explícita si falta una variable requerida y NUNCA incluir secretos hardcodeados en código o imágenes.

#### Scenario: Falta variable requerida

- **Dado** que `JWT_SECRET` no está definida en el entorno
- **Cuando** se intenta arrancar la API
- **Entonces** el arranque falla con un mensaje que nombra la variable faltante, sin levantar el servidor a medias

#### Scenario: Sin secretos en el repositorio

- **Dado** el repositorio versionado en git
- **Cuando** se inspeccionan los archivos commiteados
- **Entonces** no existe ningún `.env` con valores reales ni secretos hardcodeados en código, y `.env.example` solo contiene placeholders

### Requirement: Stack completo levantable con un comando

El sistema SHALL proveer un `docker-compose.yml` con api, postgres, redis, worker y mailhog (dev) que levanta el stack completo con un solo comando.

#### Scenario: Levantar el stack piloto

- **Dado** una máquina con Docker Compose y el `.env` configurado
- **Cuando** se ejecuta `docker compose up`
- **Entonces** los servicios api, postgres, redis, worker y mailhog quedan corriendo y `GET /api/health` responde 200

### Requirement: Frontend PWA base instalable

El sistema SHALL servir un frontend con manifest PWA instalable, service worker base, Router y páginas mínimas que consumen la API con TanStack Query.

#### Scenario: Manifest y shell disponibles

- **Dado** que el frontend está corriendo
- **Cuando** un navegador pide el manifest y la página raíz
- **Entonces** recibe un manifest válido con nombre e iconos, y una shell que muestra el estado de la API (conectado / error en rioplatense)

#### Scenario: CI verifica backend y frontend en paralelo

- **Dado** un push o pull request al repositorio
- **Cuando** corre el pipeline de CI
- **Entonces** el job de backend ejecuta pytest contra DB real y el job de frontend ejecuta `tsc` + build, y ambos deben pasar en verde
