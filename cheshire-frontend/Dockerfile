# ─────────────────────────────────────────────────────────────
# Stage 1: Dependencies
# Installs project dependencies once so other stages can reuse them
# ─────────────────────────────────────────────────────────────
FROM node:22-alpine AS deps

# Set working directory inside the container
WORKDIR /app

# Copy package files first for better Docker cache usage
COPY package.json package-lock.json ./

# Install project dependencies
RUN npm ci


# ─────────────────────────────────────────────────────────────
# Stage 2: Development
# Runs the Vite development server
# This is the stage used by docker-compose
# ─────────────────────────────────────────────────────────────
FROM node:22-alpine AS development

# Set working directory
WORKDIR /app

# Reuse installed dependencies from the deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy the project source files
COPY . .

# Expose Vite's default development port
EXPOSE 5173

# Backend service URL inside the Docker network
ENV BACKEND_URI=http://localhost:8000

# Start the Vite dev server and bind to all interfaces
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]


# ─────────────────────────────────────────────────────────────
# Stage 3: Build
# Creates a production-ready static frontend build
# Kept here for future deployment use
# ─────────────────────────────────────────────────────────────
FROM node:22-alpine AS build

# Set working directory
WORKDIR /app

# Reuse installed dependencies
COPY --from=deps /app/node_modules ./node_modules

# Copy project source files
COPY . .

# Build the app for production
RUN npm run build