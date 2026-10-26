# ─────────────────────────────────────────────────────────────
# Stage 1: Dependencies
# ─────────────────────────────────────────────────────────────
FROM node:22-alpine AS deps

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci


# ─────────────────────────────────────────────────────────────
# Stage 2: Development (used by docker-compose.yml)
# ─────────────────────────────────────────────────────────────
FROM node:22-alpine AS development

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

EXPOSE 5173
ENV BACKEND_URI=http://localhost:8000
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]


# ─────────────────────────────────────────────────────────────
# Stage 3: Build — static production bundle in /app/dist
# ─────────────────────────────────────────────────────────────
FROM node:22-alpine AS build

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build


# ─────────────────────────────────────────────────────────────
# Stage 4: Production (used by docker-compose.prod.yml)
# nginx serves the static files and proxies /api to the backend
# ─────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS production

RUN rm -f /etc/nginx/conf.d/default.conf \
    # pdf.js worker is an ES module; make sure .mjs is served as JavaScript
    && (grep -qE '\bmjs\b' /etc/nginx/mime.types \
        || sed -i -E 's/(javascript[[:space:]]+)js;/\1js mjs;/' /etc/nginx/mime.types) \
    && grep -nE '\bmjs\b' /etc/nginx/mime.types
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]