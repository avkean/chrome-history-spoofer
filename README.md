# Chrome History Generator

Generate a realistic Chrome browser history file for a student profile.

## Stack

- **Frontend:** React + Vite + Tailwind CSS
- **Backend:** FastAPI (Python)
- **Deploy:** Docker Compose + Caddy reverse proxy

## Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

Frontend runs on `localhost:5173`, proxies `/api` to the backend.

## Production

```bash
docker compose build
docker compose up -d
```

Requires the external `proxy_net` Docker network (shared with Caddy).

## API

| Endpoint | Description |
|---|---|
| `GET /api/preview?weeks=3&seed=42` | JSON preview of generated history |
| `GET /api/generate?weeks=3&seed=42` | Downloads `History` SQLite file |

Response headers include `X-Seed` and `X-Visits`.
