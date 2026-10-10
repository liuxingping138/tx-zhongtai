# syntax=docker/dockerfile:1.7
FROM node:22.12.0-slim AS build
WORKDIR /srv
# 不用 corepack prepare（当前 corepack 版本对 pnpm 签名校验有已知问题），直接用 npm 装固定版本；
# 版本必须与本地生成 pnpm-lock.yaml / pnpm-workspace.yaml 的 pnpm 版本一致，避免格式不兼容。
RUN npm install -g pnpm@12.4.1
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
# pnpm 包缓存挂在 BuildKit 缓存里，锁文件变了也只下载新增的包。
RUN --mount=type=cache,target=/pnpm-store pnpm install --frozen-lockfile --store-dir /pnpm-store
COPY frontend/ ./
RUN pnpm run build

FROM nginx:1.27-alpine3.21 AS runtime
COPY frontend/deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /srv/dist /usr/share/nginx/html
EXPOSE 80
