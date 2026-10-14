# The web app as a Next.js standalone server.
# Build from the repository root: docker build -f apps/web/Dockerfile .
FROM node:22-trixie-slim AS build
ENV NEXT_TELEMETRY_DISABLED=1 COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
WORKDIR /src
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/api-client/package.json packages/api-client/
RUN pnpm install --frozen-lockfile --filter "@opspilot/web..."
COPY packages/api-client packages/api-client
COPY apps/web apps/web
RUN pnpm --filter @opspilot/web build

FROM node:22-trixie-slim
# The server needs only node: drop the package managers and their dependencies.
RUN rm -rf /usr/local/lib/node_modules /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack /opt/yarn* /usr/local/bin/yarn*
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /app
COPY --from=build /src/apps/web/.next/standalone ./
COPY --from=build /src/apps/web/.next/static ./apps/web/.next/static
# The node image's unprivileged user.
USER 1000
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=2s CMD ["node", "-e", "fetch('http://127.0.0.1:3000/login').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]
CMD ["node", "apps/web/server.js"]
