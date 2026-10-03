# syntax=docker/dockerfile:1
# Frontend PWA: build Vite + serve estático con nginx. No-root, HEALTHCHECK.

FROM node:22.12.0-alpine AS builder
WORKDIR /srv
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27.3-alpine AS runtime
RUN adduser -D -u 10001 appuser
COPY --from=builder /srv/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
RUN touch /var/run/nginx.pid && chown -R appuser /var/run/nginx.pid /var/cache/nginx /usr/share/nginx/html
USER appuser
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O /dev/null http://localhost:80/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
