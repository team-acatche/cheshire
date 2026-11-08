# Cheshire

A security compliance assessment tool for evaluating project documents (Technical Design Documents) to empower development teams into implementing more secure software.

Upload a PDF, and Cheshire audits it against company standards and security best practices using AI. Findings are highlighted directly on the page, ranked by severity, and summarized in an exportable compliance report, so issues are caught before the Information Security review.

This project is containerized using Docker for a consistent and easy development setup.

---

## Features

* **PDF audit** with a multistep pipeline: Docling parsing and chunking, per-section audit, deduplication, then a document-wide checklist audit
* **Findings highlighted on the PDF** by severity (major, minor, observation) with confidence, recommendations, and web references
* **Document-wide findings** for missing sections, diagrams, and reference documents that have no spot on the page
* **Live progress** while the audit runs (stages, page radar, live feed, ETA), plus **cancel** and **re-run**
* **AI chatbot** to discuss findings. It streams responses over SSE, can search the web, and saves your team's policies to a knowledge base that is used in later audits
* **Assessment report** with compliance score, severity breakdown, trend across assessments, and **PDF export**
* **PDF viewer** with search, zoom, pagination, and full screen
* Email/password auth (JWT in an HttpOnly cookie), avatars, light/dark theme, and mobile support

---

## Quick Start (Docker)

### 1. Create the backend `.env`

Create a `.env` file in the `cheshire-backend` folder and paste:

```env
# LLM (OpenRouter)

OPENROUTER_API_KEY=<YOUR-OPENROUTER-API-KEY>
OPENROUTER_MODEL=anthropic/claude-haiku-5.5:nitro

# Web search (Exa)

EXA_API_KEY=<YOUR-EXA-API-KEY>

# Auth

JWT_SECRET=<A-LONG-RANDOM-STRING>
JWT_EXPIRY_HOURS=24

# Optional: Hugging Face token (model downloads)

HF_TOKEN=<YOUR-HUGGINGFACE-TOKEN>
```

Generate a `JWT_SECRET` with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

#### Environment variables

| Variable             | Required | Description                                                                                          |
| -------------------- | -------- | ---------------------------------------------------------------------------------------------------- |
| `OPENROUTER_API_KEY` | Yes      | API key used for all LLM calls (audit passes and chatbot)                                            |
| `OPENROUTER_MODEL`   | Yes      | OpenRouter model ID. Use `anthropic/claude-haiku-5.5:nitro`                                          |
| `EXA_API_KEY`        | Yes      | Exa key for the `web_search` tool, used to verify CVEs, standards, and references                    |
| `JWT_SECRET`         | Yes      | Secret used to sign login tokens. Login fails with a 500 error if it is missing                     |
| `JWT_EXPIRY_HOURS`   | No       | Login session length in hours (default `24`)                                                         |
| `COOKIE_SECURE`      | No       | Set to `true` only when served over HTTPS. Defaults to `false` in dev and `true` in the prod compose |
| `HF_TOKEN`           | No       | Hugging Face token for downloading models                                                            |

> **Note:** `OPENROUTER_MODEL` falls back to a different default in code if it is not set. Always set it explicitly in your `.env`.

Docker Compose also sets these for you, so you don't need them in `.env`: `CHESHIRE_DATA_PATH=/data`, `QDRANT_HOST=qdrant`, `QDRANT_PORT=6333`.

> Optional: put overrides in `cheshire-backend/.env.user`. It is loaded if present.

### 2. Run

```bash
docker compose up --build
```

### 3. Create an account

There is no sign-up screen yet. Create your first account with the API once the backend is up:

```bash
curl -X POST http://localhost:8000/api/v1/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "your-password", "username": "you", "full_name": "Your Name"}'
```

Then sign in at `http://localhost:5173` with that email and password.

---

## Services

| Service  | Description                          | URL                     |
| -------- | ------------------------------------ | ----------------------- |
| Frontend | User interface (React/Vite)          | `http://localhost:5173` |
| Backend  | FastAPI backend API                  | `http://localhost:8000` |
| Qdrant   | Vector store for the knowledge base  | internal (`qdrant:6333`) |

User data (accounts, sessions, uploaded PDFs, and Qdrant storage) is persisted on the host in `~/.cheshire`.

---

## Health Check

To verify that the backend is running:

```bash
curl http://localhost:8000/healthcheck
```

---

## Docker Setup

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
├── docker-compose.yml          # Development stack
├── docker-compose.prod.yml     # Production stack (nginx)
├── README.md
├── cheshire-backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── poetry.lock
│   ├── assets/
│   │   └── standards/          # global_rules.json, local_rules.json (company standards)
│   └── src/
│       ├── auth/               # users, hashing, JWT dependencies
│       ├── cheshire_configs/   # OpenRouter config, prompts, multistep audit pipeline
│       ├── endpoints/          # evaluate, chat, reports, user, user_auth
│       ├── knowledge_base/     # Qdrant, sessions, history, jobs, progress
│       ├── tools/              # agent tools (web search, knowledge, findings)
│       └── tests/
├── cheshire-frontend/
│   ├── Dockerfile
│   ├── package.json
│   └── src/
```

---

## How It Works

1. **Upload** a PDF. It is validated (type, size up to 100 MB, not password-protected) and stored per session.
2. **Parse and chunk** with Docling into sections, tables, and figures.
3. **Audit each section** with the LLM against the local standards checklist, using `web_search` for external facts.
4. **Deduplicate** findings and discard false positives.
5. **Global audit** against the document-level checklist (required sections, diagrams, reference documents).
6. **Locate** findings on the PDF, then save them. Progress is polled by the frontend the whole time.
7. **Chat** about the findings. Policies you state in chat are saved to the knowledge base and applied to future audits.

Company standards live in `cheshire-backend/assets/standards/*.json` and are seeded into Qdrant on startup.

---

## Development Notes

* Backend is built with **FastAPI** and runs using **Uvicorn**
* LLM calls go through **OpenRouter** with retry and timeout handling
* Frontend runs in a separate container for modular development. The Vite dev server proxies `/api` to the backend via `BACKEND_URI`
* Services communicate through Docker networking
* Backend is accessible via `0.0.0.0` inside container for proper exposure

### Running backend tests

```bash
cd cheshire-backend
pytest
```

---

## Known Limitations

* No sign-up screen yet. Accounts are created through `POST /api/v1/register`
* Evaluation jobs are tracked in memory, so live progress is lost if the backend restarts mid-run
* Chat streaming resume state is per-process (use Redis for multi-replica deployments)

---

## How to Test

1. Run:

   ```bash
   docker compose up --build
   ```

2. Open the frontend in your browser: `http://localhost:5173`

3. Test the backend:

   ```bash
   curl http://localhost:8000/healthcheck
   ```

4. Check the FastAPI docs: `http://localhost:8000/docs`

5. Upload a PDF and monitor backend logs:

   ```bash
   docker compose logs -f cheshire-backend
   ```

---

## Production Deployment

In production, you don't use the Vite dev server. The frontend is **built** into static files and served by **nginx**, which also proxies `/api` to the backend. You can then expose it to the internet using a **Cloudflare Tunnel**, with no need to open ports on your machine.

The frontend `Dockerfile` already includes the `production` stage (nginx), and `docker-compose.prod.yml` targets it.

### Step 1: Configure the backend

Use the same `cheshire-backend/.env` as above. Set `COOKIE_SECURE` correctly:

* `true` when users reach the site over **HTTPS** (for example behind a Cloudflare Tunnel or a TLS proxy). This is the default in the prod compose file.
* `false` if you test over plain `http://host:6000`. A Secure cookie is dropped by the browser on plain HTTP, and login will appear to fail.

You can set it inline:

```bash
COOKIE_SECURE=false docker compose -f docker-compose.prod.yml up -d --build
```

### Step 2: Build and run

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Only the frontend (nginx) is meant to be public. It is published on host port `6000` (container port `80`). The backend and Qdrant are reached over the internal Docker network.

Visit `http://localhost:6000` to verify the frontend is working.

> **What nginx does:** requests to `/api/*` (for example `/api/v1/evaluate`) are forwarded to the backend container. Everything else serves static files, falling back to `index.html` for client-side routing.

### Step 3: Expose to the internet with Cloudflare Tunnel

If you're already familiar with Cloudflare Tunnels, you can skip the setup steps. Point your tunnel to the nginx container:

```bash
# If you haven't logged in yet:
cloudflared tunnel login

# Create a tunnel (one-time):
cloudflared tunnel create cheshire

# Route your domain to the tunnel:
cloudflared tunnel route dns cheshire cheshire.yourdomain.com

# Run the tunnel, pointing to the published frontend port:
cloudflared tunnel run --url http://localhost:6000 cheshire
```

This proxies `cheshire.yourdomain.com` to your local port `6000` (nginx) and the built React app. No ports need to be opened on your router or firewall.

> **Tip:** Audits can take several minutes. Cheshire polls for evaluation status, and chat streams send keepalive pings, to stay under Cloudflare's proxy timeouts.

---

## Notes

* Make sure Docker is running before executing commands
* Avoid using `--no-cache` unless necessary to prevent large storage usage
* Cache directory has been optimized to prevent disk space issues
* Cheshire can make mistakes. Verify important security findings

---

## Contributors

* Team Acatche

---

## Related Task

SCRUM-92 – Dockerize the app to provide a more consistent environment and allow for integration with other services

---
