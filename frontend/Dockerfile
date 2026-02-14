# =============================================================================
# Stage 1: Build (Node 18 + pnpm)
# =============================================================================
FROM node:18-alpine AS builder

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

# Ensure devDependencies (tsc, vite) are installed in builder stage
ENV NODE_ENV=development

# Copy dependency manifests first for layer caching
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Copy source and build
COPY . .

# Build with relative API URL — gateway will proxy /api/ to backend
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=${VITE_API_URL}
ENV NODE_ENV=production
RUN pnpm build

# =============================================================================
# Stage 2: Runtime (nginx:alpine serving static SPA)
# =============================================================================
FROM nginx:alpine AS runner

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom SPA-aware nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy build artifacts from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Run as non-root (nginx alpine already runs worker as nginx user)
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
