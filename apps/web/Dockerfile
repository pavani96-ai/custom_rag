# Dependencies are installed from the lock file so builds are reproducible.
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# Build stage: type check and production build. `make check` builds this target.
FROM deps AS build
ARG NEXT_PUBLIC_WORKSPACE_ID=""
ENV NEXT_PUBLIC_WORKSPACE_ID=$NEXT_PUBLIC_WORKSPACE_ID
COPY . .
RUN npm test && npm run typecheck && npm run build

FROM node:22-alpine AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
RUN addgroup -S app && adduser -S app -G app
COPY --from=build --chown=app:app /app/.next/standalone ./
COPY --from=build --chown=app:app /app/.next/static ./.next/static
USER app
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
