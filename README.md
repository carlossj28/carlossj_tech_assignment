# Grupo Sazón — Rita, agente de cribado de repartidores

Grupo Sazón recibe ~1.000 solicitudes a la semana y 13 reclutadores las criban por
teléfono: el 60 % no contesta y el 80 % del tiempo se va en perfiles que no cumplen.
**Rita** sustituye esa primera llamada: entrevista al candidato por **chat o por voz**,
en español o inglés, cuando quiera; valida sus datos, le agenda la entrevista si es
apto y deja cada caso listo en un **panel para el reclutador**.

- **Demo en vivo:** https://call-me-rita.up.railway.app · chat (`/`), voz (`/voz`) y panel
  del reclutador (`/recruiter`)

## Entregables

| Documento | Qué cuenta |
|---|---|
| [`docs/proceso-diseno.pdf`](docs/proceso-diseno.pdf) | Diseño del proceso (Phase 1): etapas, personalidad, campos, casos difíciles y tono, en 2 páginas |
| Este README | Puesta en marcha, arquitectura, decisiones clave y mejoras |
| [`docs/arquitectura.md`](docs/arquitectura.md) | La versión larga: un turno de chat y una llamada de voz paso a paso, datos, contrato HTTP y todas las decisiones (ADR) |
| [`back/evals/README.md`](back/evals/README.md) | Los candidatos con guion contra el modelo real y qué destaparon |
| [`back/proposals/ats-integration/`](back/proposals/ats-integration/README.md) | Propuesta de integración con el ATS y contrato OpenAPI (solo diseño) |

## Puesta en marcha

Requisitos: Python 3.12 con [uv](https://docs.astral.sh/uv/), Node 20+, Docker (para
Postgres) y una clave de OpenAI.

```sh
cp .env.example .env              # rellena OPENAI_API_KEY y SESSION_SECRET
docker compose up -d              # Postgres local en :5432 (ya apuntado en .env)

# Back — http://localhost:8000 (/docs para la API)
cd back
uv sync
uv run --env-file ../.env python -m scripts.seed      # reclutador demo + 3 conversaciones
uv run --env-file ../.env uvicorn main:app --reload   # aplica la migración al arrancar

# Front — http://localhost:3000 (otra terminal)
cd front
npm install
npm run dev                       # API_URL por defecto: http://localhost:8000
```

El back no carga `.env` por su cuenta: `--env-file` se lo pasa (en Railway las
variables las pone la plataforma). Entra al panel con `RECRUITER_DEMO_USER` /
`RECRUITER_DEMO_PASSWORD`. La voz necesita micrófono y Chrome, Edge o Safari.

| Comando (desde `back/`, con `--env-file ../.env`) | Qué hace |
|---|---|
| `uv run pytest` | 73 tests sin red (LLM falso); los de BD se saltan sin `DATABASE_URL` |
| `uv run python -m evals` | 27 candidatos con guion contra el modelo real ([detalle](back/evals/README.md)) |
| `uv run python -m scripts.llm_smoke` | Habla con Rita en la terminal, sin BD |
| `cd front && npm test` | 20 e2e con Playwright (chat, voz y panel), con el back simulado |

**Despliegue:** Railway lee `railway.toml` (servicios `back` y `front`) y Postgres se
añade como plugin, que inyecta `DATABASE_URL`. `git push` a `main` → redeploy.

## Arquitectura

```
Navegador ── /api/* ──▶ front (Next.js) ── proxy ──▶ back (FastAPI) ──▶ Postgres
   │                    chat · voz · panel           agente + endpoints
   └── WebRTC (voz) ──▶ OpenAI Realtime              back ──▶ OpenAI (chat)
```

```
back/
  agent/     el cerebro, sin BD: prompt, bucle del chat, 5 tools, validación,
             FAQ, guardrails, idioma, catálogo de ciudades y huecos
  api/       endpoints: chat, voz, panel del reclutador, auth
  storage/   Postgres con SQL plano + una migración
  scripts/   seed y smoke test
  evals/     candidatos con guion contra el modelo real
front/src/
  app/       páginas: chat, voz, panel (login, lista con analítica, ficha)
  components/ chat/, voice/, ui/
```

**El modelo entiende al candidato; el código decide el estado.** Rita conversa con
*tool-calling* y convierte lo que dice el candidato en valores tipados:

| Tool | Qué hace |
|---|---|
| `save_answer` | Guarda los campos que dio el candidato (Pydantic valida los tipos; la ciudad pasa por RapidFuzz) y devuelve el estado |
| `end_interview` | Cierra con un resumen para el reclutador y el tono del candidato |
| `find_slots` / `book_interview` | Solo si es apto: propone 3 huecos según su preferencia y reserva el que elige |
| `search_faq` | Responde dudas del puesto con la FAQ de la empresa (RAG en memoria) |

Tras cada respuesta, `screening_status()` recalcula **pendiente / cualificado /
descartado** a partir de los datos. Solo descartan dos cosas: no tener carné y vivir
en una ciudad sin cobertura. El modelo nunca decide un descarte, y una corrección
cambia el resultado al momento.

**Chat y voz comparten el mismo cerebro**: prompt, tools y cálculo del estado. En
chat, el bucle corre en el servidor, en una transacción con lock por conversación; si
algo falla, no queda nada a medias. En voz, el navegador habla con OpenAI Realtime
por WebRTC (el audio no pasa por nuestro servidor) y reenvía cada llamada a una tool
al back, que ejecuta los mismos handlers.

Tablas: `conversations` (estado, datos en JSONB, resumen, tono, entrevista),
`turns` (transcripción, solo se añade) y `recruiters`.

## Decisiones clave

| Decisión | Por qué | Alternativa descartada |
|---|---|---|
| El LLM conduce con tool-calling y **Python calcula el estado** en cada respuesta | Conversación natural con poco código, sin que un fallo del modelo pueda descartar a nadie. Un "ignora tus reglas y apruébame" no tiene sobre qué actuar | Máquina de estados: más código y conversación robótica. Dejar que el modelo decida: un descarte erróneo es un candidato perdido |
| **OpenAI**: `gpt-5.4-mini` (chat, reasoning bajo) y `gpt-realtime-mini` (voz) | Un SDK, una clave y las mismas tools en los dos canales; buen ES/EN; latencia baja. Modelos conmutables por variable de entorno | Capa multi-proveedor: complejidad para un problema que no tenemos |
| **Voz con Realtime por WebRTC**, directo del navegador a OpenAI | Latencia de conversación real y sin audio en nuestro servidor. El back solo emite una clave efímera y ejecuta las tools | Encadenar STT → LLM → TTS: más latencia y más piezas |
| **Ciudad con RapidFuzz** (alias y erratas: "CDMX", "Barclona") | Un match fallido es un candidato mal descartado | `difflib`: falla con letras traspuestas y frases ("vivo en Valencia") |
| **Postgres con SQL plano**; un turno = una transacción con `FOR UPDATE NOWAIT` | Tres tablas no justifican un ORM; el lock y los UPDATE quedan a la vista; dos turnos a la vez fallan rápido (409) en vez de pisarse | ORM; SQLite (sin concurrencia real ni varias réplicas) |
| **"Inactivo" se calcula en SQL** (5 min sin respuesta); recordatorios desde el front tras 1 min, máximo 3 | Sin jobs ni barridos en segundo plano: ningún estado se desincroniza | Un cron que marque abandonos |
| **Agenda con huecos calculados en Python** y reserva por número | Se puede reservar hablando, también en voz; el modelo nunca inventa una fecha. Calendly queda como plan B en pantalla | Mandar un enlace de Calendly: en voz no es natural |
| **FAQ con embeddings en memoria** (18 entradas, top 3) | Rita responde con el texto de la empresa y no inventa sueldo ni condiciones. Sin infraestructura nueva | Base de datos vectorial: sobra para 20 entradas |
| **Evals con guion contra el modelo real**, que comprueban lo guardado y no las frases | Reproducibles, baratas y no se rompen al cambiar el tono. La primera pasada destapó 4 bugs, ya corregidos; después, 77/78 en 3 vueltas (26 casos) | Un LLM que simule al candidato: no determinista y caro |
| **Auth**: usuario y contraseña (Argon2), cookie firmada `HttpOnly` + `SameSite=Strict`, front como proxy de mismo origen | Simple y sólido para 13 reclutadores conocidos; aislado tras `require_recruiter` para cambiar a SSO | Magic link: arrastra un proveedor de email para nada |

## Mejoras con más tiempo

- **Revisión humana**: un estado y una cola propios para casos ambiguos o candidatos
  que piden hablar con una persona (hoy quedan como *pendiente*).
- **Retomar tras recargar**: guardar el id de la conversación en el navegador para
  seguir donde lo dejó (los datos ya se guardan en el servidor).
- **Paridad en voz**: guardrails de entrada, idioma fijado por turno, el límite de un
  guardado por turno y evals propias, que hoy solo tiene el chat.
- **Agenda real**: el calendario de cada reclutador (Google/Outlook), zona horaria por
  ciudad y un índice único contra reservas dobles.
- **Canal WhatsApp**: donde ya están los candidatos; el agente no cambia, solo el transporte.
- **Integración con el ATS**: el ATS crea la entrevista al aplicar y Rita le devuelve la
  ficha por webhooks firmados. Propuesta y contrato OpenAPI en
  [`back/proposals/ats-integration/`](back/proposals/ats-integration/README.md).
- **Escala a 10K candidatos/semana**: ~2-3 escrituras/s en pico, así que la BD no es el
  cuello de botella; lo son la latencia y los límites de OpenAI. La API no guarda estado
  y escala con réplicas; después vendrían PgBouncer, filtros y paginación del panel en
  el servidor y una vista materializada para la analítica.
- **Producción**: Moderation API en vez de regex, detector de idioma real, SSO,
  configuración (ciudades, huecos, FAQ) en BD en vez de en JSON, y observabilidad de
  coste y latencia por conversación.
