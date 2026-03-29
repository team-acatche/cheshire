# cheshire

A security compliance assessment tool for evaluating project documents to empower development teams into implementing more secure software.

This project is containerized using Docker for a consistent and easy development setup.

---

## Quick Start (Docker)

Create an .env file in cheshire-backend folder and paste:

```env
# Mode

MODE=ollama # ollama | together-ai
CONFIG_TYPE=rag # rag | full-document

# HuggingFace

HF_TOKEN=\<YOUR-HUGGINGFACE-TOKEN>

# Ollama

OLLAMA_URL=\<YOUR-OLLAMA-URL>
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0.6b
OLLAMA_CHAT_MODEL=qwen3
HF_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B

# Exa

EXA_API_KEY=\<YOUR-EXA-API-KEY>

# Together AI

TOGETHER_API_KEY=\<YOUR-TOGETHER-AI-API-KEY>
TOGETHER_CHAT_MODEL=Qwen/Qwen3-235B-A22B-Instruct-2507-tput
TOGETHER_REASONING_EFFORT=high
```

Run the entire project with a single command:

```bash
docker compose up --build
```

---

## Services

| Service  | Description                 | URL                     |
| -------- | --------------------------- | ----------------------- |
| Frontend | User interface (React/Vite) | `http://localhost:5173` |
| Backend  | FastAPI backend API         | `http://localhost:8000` |

---

## Health Check

To verify that the backend is running:

```bash
curl http://localhost:8000/healthcheck
```

---

## 🐳 Docker Setup

### Prerequisites

* Docker
* Docker Compose

### Build and Run

```bash
docker compose up --build
```

### Stop Containers

```bash
docker compose down
```

---

## Project Structure

```bash
cheshire/
├── docker-compose.yml
├── README.md
├── cheshire-backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── poetry.lock
│   └── src/
├── cheshire-frontend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
```

---

## Development Notes

* Backend is built with **FastAPI** and runs using **Uvicorn**
* Frontend runs in a separate container for modular development
* Services communicate through Docker networking
* Backend is accessible via `0.0.0.0` inside container for proper exposure

---

## Features Implemented

* Dockerized backend service
* Dockerized frontend service
* Multi-container setup using Docker Compose
* Backend healthcheck endpoint (`/healthcheck`)
* Verified document processing via backend logs

---

## Known Limitations

* UI does not yet include a processing/loading animation

---

## How to Test

1. Run:

   ```bash
   docker compose up --build
   ```

2. Open frontend in browser: `http://localhost:5173`

3. Test backend:

   ```bash
   curl http://localhost:8000/healthcheck
   ```

4. Check FastAPI docs: `http://localhost:8000/docs`

5. Upload a document and monitor backend logs:

   ```bash
   docker compose logs -f cheshire-backend
   ```

---

## Production Deployment

In production, you don't use the Vite dev server. Instead, you **build** the frontend into static files and serve them with **nginx** inside a Docker container. You can then expose the containers to the internet using a **Cloudflare Tunnel** — no need to open ports on your machine.

### Step 1: Add an nginx stage to the frontend Dockerfile

The frontend `Dockerfile` already has a `build` stage that creates static files. Add a `production` stage at the end of `cheshire-frontend/Dockerfile`:

```dockerfile
# ─────────────────────────────────────────────────────────────
# Stage 4: Production
# Serves the built static files with nginx
# ─────────────────────────────────────────────────────────────
FROM nginx:alpine AS production

# Copy the built static files from the build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

### Step 2: Create an nginx config for your SPA

Create `cheshire-frontend/nginx.conf`:

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # Proxy API requests to the backend container.
    # The path is preserved: /api/v1/evaluate → http://cheshire-backend:8000/api/v1/evaluate
    location /api/ {
        proxy_pass http://cheshire-backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # For single-page apps: if the file doesn't exist,
    # serve index.html so React Router can handle the URL
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

> **What this does:** Requests to `/api/*` (e.g., `/api/v1/evaluate`) are forwarded to the backend container inside the Docker network. Everything else serves static files, falling back to `index.html` for client-side routing.

### Step 3: Update docker-compose.yml for production

Change the frontend service to target the `production` stage:

```yaml
cheshire-frontend:
  build:
    context: ./cheshire-frontend
    dockerfile: Dockerfile
    target: production        # was: development
  container_name: cheshire-frontend
  restart: unless-stopped
  ports:
    - "80:80"                 # nginx serves on port 80
  depends_on:
    - cheshire-backend
  networks:
    - cheshire
```

Then rebuild:

```bash
docker compose up --build
```

Visit `http://localhost` to verify the frontend is working.

### Step 4: Expose to the internet with Cloudflare Tunnel

If you're already familiar with Cloudflare Tunnels, you can skip the setup steps. Point your tunnel to the container:

```bash
# If you haven't logged in yet:
cloudflared tunnel login

# Create a tunnel (one-time):
cloudflared tunnel create cheshire

# Route your domain to the tunnel:
cloudflared tunnel route dns cheshire cheshire.yourdomain.com

# Run the tunnel, pointing to your local containers:
cloudflared tunnel run --url http://localhost:80 cheshire
```

This proxies `cheshire.yourdomain.com` → your local port 80 (nginx) → the built React app. No ports need to be opened on your router/firewall.

> **Tip:** For the backend, you can add a second `cloudflared` tunnel or add an `ingress` rule in your tunnel config to route `api.yourdomain.com` → `http://localhost:8000`.

---

## Notes

* Make sure Docker is running before executing commands
* Avoid using `--no-cache` unless necessary to prevent large storage usage
* Cache directory has been optimized to prevent disk space issues

---

## Contributors

* Team Acatche

---

## Related Task

SCRUM-92 – Dockerize the app to provide a more consistent environment and allow for integration with other services

---
