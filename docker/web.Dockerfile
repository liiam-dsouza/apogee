# syntax=docker/dockerfile:1.7
# Static frontend served by nginx, which also proxies /api to the api service.

FROM node:24-slim AS build
ENV PNPM_HOME=/pnpm PATH=/pnpm:$PATH
RUN corepack enable
WORKDIR /web
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile
COPY apps/web/ ./
# The Docs section bundles the repo's documentation (see vite.config.ts).
COPY docs/ /docs/
ENV APOGEE_DOCS_DIR=/docs
ARG VITE_FIELD_MODE=false
ARG VITE_MAP_PMTILES=
RUN pnpm build

FROM nginx:1.29-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
