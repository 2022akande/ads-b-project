FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# NEXT_PUBLIC_* vars are compiled into the client bundle, so the WebSocket URL
# must be supplied at build time (see docker-compose.yml build args).
ARG NEXT_PUBLIC_WS_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL

# next.config.mjs's rewrites() is baked into routes-manifest.json at build time,
# so BACKEND_URL must also be supplied here — setting it only as a runtime
# `environment:` var (docker-compose.yml) is too late and silently falls back
# to the 127.0.0.1:8000 default, which never reaches the backend container.
ARG BACKEND_URL
ENV BACKEND_URL=$BACKEND_URL

RUN npm run build

EXPOSE 3000
CMD ["npm", "start"]
