#!/bin/bash
# Crea el rol app restringido (LOGIN) para runtime/CI. Corre en el init de Postgres.
# El password viene de APP_DB_PASSWORD (obligatoria en .env); jamás hardcodeada acá.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  DO \$\$
  BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'turnos_app') THEN
      CREATE ROLE turnos_app WITH LOGIN PASSWORD '${APP_DB_PASSWORD:?Falta APP_DB_PASSWORD}';
    END IF;
  END
  \$\$;
  GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO turnos_app;
  GRANT USAGE ON SCHEMA public TO turnos_app;
EOSQL
