# cheshire
A security compliance assessment tool for evaluating project documents to empower development teams into implementing more secure software.

This project is containerized using Docker for a consistent and easy development setup.

---

## Quick Start (Docker)
Create an .env file in cheshire-backend folder and paste:
```
# Mode
MODE=ollama # ollama | together-ai
CONFIG_TYPE=rag # rag | full-document

# HuggingFace
HF_TOKEN=<YOUR-HUGGING-FACE-TOKEN>

# Ollama
OLLAMA_URL=http://172.27.80.1:11434/
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0.6b
OLLAMA_CHAT_MODEL=qwen3
HF_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B

# Exa
EXA_API_KEY=<YOUR-EXA-API-KEY>

# Together AI
TOGETHER_API_KEY=<YOUR-TOGETHER-AI-API-KEY>
TOGETHER_CHAT_MODEL=Qwen/Qwen3-235B-A22B-Instruct-2507-tput
TOGETHER_REASONING_EFFORT=high
```


Run the entire project with a single command:

```bash
docker compose up --build
```

---

## Services

| Service  | Description                 | URL                   |
| -------- | --------------------------- | --------------------- |
| Frontend | User interface (React/Vite) | http://localhost:5173 |
| Backend  | FastAPI backend API         | http://localhost:8000 |

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

* Nginx production setup is not yet included (project still in development)
* UI does not yet include a processing/loading animation

  * A skeletal loading animation was suggested to improve user experience
  * Currently considered low priority

---

## How to Test

1. Run:

   ```bash
   docker compose up --build
   ```

2. Open frontend in browser:

   ```
   http://localhost:5173
   ```

3. Test backend:

   ```bash
   curl http://localhost:8000/healthcheck
   ```

4. Check FastAPI docs:

    ```
    http://localhost:8000/docs
    ```

5. Upload a document and monitor backend logs:

   ```bash
   docker compose logs -f cheshire-backend
   ```

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
