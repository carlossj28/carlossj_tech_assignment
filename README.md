# Grupo Sazón — Screening Agent

Agente de IA para el cribado de candidatos a repartidor de Grupo Sazón, con
panel para reclutadores. Monorepo: `back` (FastAPI) + `front` (Next.js) + Postgres,
desplegado en Railway.

## Estructura

```
back/   FastAPI — agente, tools, persistencia, endpoints
front/  Next.js — chat, voz y panel del reclutador
```

## Desarrollo local

Copia `.env.example` a `.env` y rellena las claves.

```sh
# Back  (http://localhost:8000, /health, /docs)
cd back && uv sync && uv run uvicorn main:app --reload
cd back && uv run pytest        # tests

# Front  (http://localhost:3000)
cd front && npm install && npm run dev
```

## Despliegue

Railway lee `railway.toml` (servicios `back` + `front`) y añade Postgres como
plugin (inyecta `DATABASE_URL`). `git push` a `main` → redeploy.
