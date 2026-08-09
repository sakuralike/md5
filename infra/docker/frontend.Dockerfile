FROM node:22-alpine AS dependencies
ENV COREPACK_HOME=/corepack
WORKDIR /workspace
RUN corepack enable
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY postcss.config.js tailwind.config.js ./
COPY packages ./packages
COPY apps/web ./apps/web
COPY apps/admin ./apps/admin
RUN --mount=type=cache,target=/corepack,sharing=locked \
    --mount=type=cache,target=/pnpm/store,sharing=locked \
    pnpm config set store-dir /pnpm/store && \
    pnpm config set fetch-retries 10 && \
    pnpm config set fetch-timeout 120000 && \
    pnpm config set network-concurrency 4 && \
    pnpm install --frozen-lockfile

FROM dependencies AS build
ARG TARGET_FILTER
ARG TARGET_DIR
ARG VITE_MAX_ARCHIVE_SIZE_BYTES=21474836480
ENV VITE_MAX_ARCHIVE_SIZE_BYTES=${VITE_MAX_ARCHIVE_SIZE_BYTES}
RUN pnpm --filter ${TARGET_FILTER} build
RUN mkdir -p /output && cp -R ${TARGET_DIR}/dist/. /output/

FROM nginx:1.27-alpine
COPY infra/nginx/spa.conf /etc/nginx/conf.d/default.conf
COPY --from=build /output /usr/share/nginx/html
EXPOSE 80
