# Grupo Sazón — Screening Agent

Agente de IA para el cribado de candidatos a repartidor de Grupo Sazón, con
panel para reclutadores. Monorepo: `back` (FastAPI) + `front` (Next.js) + Postgres,
desplegado en Railway.

## Estructura

```
back/
  main.py     app FastAPI (monta los routers)
  api/        endpoints HTTP: auth, chat, voz, reclutador
  agent/      el agente: runner, prompts, tools, guardrails, FAQ (+ data/)
  storage/    Postgres: db.py + migrations/
  scripts/    seed (datos demo) y llm_smoke
  tests/  evals/
front/src/
  app/        páginas: chat, voz y panel del reclutador
  components/ chat/, voice/ y ui/ (piezas compartidas)
  lib/        cliente de la API y utilidades
```

## Desarrollo local

Copia `.env.example` a `.env` y rellena las claves.

```sh
# Back  (http://localhost:8000, /health, /docs)
cd back && uv sync && uv run uvicorn main:app --reload
cd back && uv run pytest        # tests
cd back && uv run python -m scripts.seed   # reclutador demo + conversaciones de ejemplo
cd back && OPENAI_API_KEY=... uv run python -m evals   # evals del agente real (back/evals/README.md)

# Front  (http://localhost:3000)
cd front && npm install && npm run dev
cd front && npm test           # e2e del chat (Playwright, back simulado)
```

## Despliegue

Railway lee `railway.toml` (servicios `back` + `front`) y añade Postgres como
plugin (inyecta `DATABASE_URL`). `git push` a `main` → redeploy.
