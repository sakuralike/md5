FROM node:22-alpine AS build
ARG TARGET_FILTER
ARG TARGET_DIR
WORKDIR /workspace
RUN corepack enable
COPY package.json pnpm-workspace.yaml ./
COPY packages ./packages
COPY apps/web ./apps/web
COPY apps/admin ./apps/admin
RUN pnpm install --no-frozen-lockfile
RUN pnpm --filter ${TARGET_FILTER} build
RUN mkdir -p /output && cp -R ${TARGET_DIR}/dist/. /output/

FROM nginx:1.27-alpine
COPY infra/nginx/spa.conf /etc/nginx/conf.d/default.conf
COPY --from=build /output /usr/share/nginx/html
EXPOSE 80
