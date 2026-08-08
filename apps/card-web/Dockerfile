FROM node:26.6.0-alpine3.24 AS build

ARG PNPM_VERSION=11.7.0
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_PUBLIC_BASE=/
ARG VITE_ENABLE_BLANK_ENTERPRISE_TEMPLATE=false

WORKDIR /workspace
RUN corepack enable && corepack prepare "pnpm@${PNPM_VERSION}" --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/card-web/package.json apps/card-web/package.json
COPY apps/admin-web/package.json apps/admin-web/package.json
COPY packages/card-page-renderer/package.json packages/card-page-renderer/package.json
RUN pnpm install --frozen-lockfile --filter @cf/card-web...

COPY apps/card-web apps/card-web
COPY packages/card-page-renderer packages/card-page-renderer
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_PUBLIC_BASE=${VITE_PUBLIC_BASE}
ENV VITE_ENABLE_BLANK_ENTERPRISE_TEMPLATE=${VITE_ENABLE_BLANK_ENTERPRISE_TEMPLATE}
RUN pnpm --filter @cf/card-web exec vite build --base "${VITE_PUBLIC_BASE}"

FROM nginx:1.31.2-alpine3.23 AS runtime
RUN apk upgrade --no-cache
COPY apps/card-web/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /workspace/apps/card-web/dist /usr/share/nginx/html
RUN chmod 0644 /etc/nginx/nginx.conf \
  && find /usr/share/nginx/html -type d -exec chmod 0755 {} + \
  && find /usr/share/nginx/html -type f -exec chmod 0644 {} +
USER nginx
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=10 \
  CMD wget -q -O - http://127.0.0.1:8080/healthz || exit 1
