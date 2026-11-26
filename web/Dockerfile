FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# Both are baked into the build. The browser calls the API through this
# app's own /api path, proxied to API_PROXY_TARGET (the compose service by
# default). NEXT_PUBLIC_API_BASE stays empty unless the API is served from
# its own host.
ARG NEXT_PUBLIC_API_BASE=
ARG API_PROXY_TARGET=http://api:8000
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
ENV API_PROXY_TARGET=$API_PROXY_TARGET

RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production

COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

# Next.js standalone ships a stock `node` user (uid 1000); the server binds
# 3000 and writes nothing at runtime.
USER node

EXPOSE 3000

CMD ["node", "server.js"]
