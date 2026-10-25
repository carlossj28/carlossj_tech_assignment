# Arquitectura y decisiones — Rita · Grupo Sazón

El comportamiento conversacional (personalidad, etapas, tono, casos difíciles) está en
[`proceso-diseno.pdf`](proceso-diseno.pdf) (Phase 1). Este documento cuenta cómo está construido.

---

## 1. Principio

**El modelo entiende al candidato; Python decide el estado.** Rita conduce la conversación con
tool-calling y traduce lo que dice el candidato a valores tipados. Pydantic valida los tipos y
`screening_status()` calcula el veredicto a partir de los datos **en cada respuesta**. El modelo
nunca decide si alguien es apto ni descarta a nadie: si se equivoca al llamar una herramienta,
el estado sigue saliendo de los datos.

Lo que esto no cubre: si el modelo interpreta mal ("sí" cuando era "no"), Python ve un dato
bien tipado pero falso. La defensa es el resumen y la confirmación explícita antes de cerrar,
y la transcripción completa para el reclutador.

---

## 2. Piezas

```
Navegador ── /api/* ──▶ front (Next.js) ── rewrite ──▶ back (FastAPI) ──▶ Postgres
   │                    chat, voz, panel              agente, tools,      conversations
   │                                                  endpoints           turns, recruiters
   └── WebRTC (solo voz) ──▶ OpenAI Realtime        back ──▶ OpenAI (chat)
```

- **Mismo origen:** Next reescribe `/api/*` a `API_URL` (`front/next.config.ts`). El navegador
  nunca habla con el back directamente: sin CORS y con la cookie `SameSite=Strict`.
- **Voz:** el back emite una clave efímera y el audio va directo del navegador a OpenAI; nuestra
  clave nunca llega al navegador. Las llamadas a herramientas sí vuelven al back.

| Carpeta | Qué hay |
|---|---|
| `back/agent/` | El cerebro, sin BD: `prompts.py`, `runner.py` (bucle del chat), `tools.py` (5 tools + `screening_status`), `schemas.py` (Pydantic), `faq.py` (RAG en memoria), `guardrails.py`, `language.py`, `service_areas.py`, `data/` (ciudades, huecos, FAQ) |
| `back/api/` | Endpoints: `chat.py`, `voice.py`, `recruiter.py`, `auth.py` |
| `back/storage/` | `db.py` (SQL plano, psycopg 3) y la migración única |
| `back/scripts/` | `seed.py` (reclutador + 3 conversaciones demo), `llm_smoke.py` |
| `back/evals/` | 27 candidatos con guion contra el modelo real |
| `front/src/` | `app/` (páginas), `components/{chat,voice,ui}`, `lib/` (cliente API, analítica, .ics) |

---

## 3. Herramientas

Cinco, definidas una vez en `agent/tools.py` y registradas igual en chat y voz. Los schemas
OpenAI se generan desde los modelos Pydantic, así lo que ve el modelo y lo que valida Python
no pueden divergir.

| Tool | Qué hace |
|---|---|
| `save_answer` | Guarda uno o varios campos tipados (todos opcionales), **en una sola llamada por mensaje**. La ciudad llega tal como la escribió el candidato y pasa por RapidFuzz. Devuelve el estado y, si hay knock-out, el motivo y las ciudades cubiertas. Un tipo inválido devuelve `validation_error` y Rita vuelve a preguntar. |
| `end_interview` | Cierra con un resumen de 2-3 frases y el tono del candidato (`positive/neutral/frustrated`). |
| `find_slots` | Solo si es apto: los 3 huecos libres más próximos que encajan con su preferencia (día, desde qué fecha, mañana/tarde/noche). Los guarda como `_offered_slots`. |
| `book_interview` | Solo si es apto: reserva el hueco que eligió el candidato **por su número** (1-3) entre los ofrecidos. |
| `search_faq` | Dudas sobre el puesto (sueldo, vehículo, contrato…): las 3 entradas de la FAQ más cercanas. Rita responde solo con eso y retoma (ADR-031). |

`dispatch()` nunca lanza excepciones: herramienta desconocida, JSON roto o argumentos inválidos
se convierten en un resultado de error al que el modelo puede reaccionar.

**Campos** (`SaveAnswerArgs`): `full_name` (1-120), `has_driver_license` (bool), `city`,
`availability` (`full_time/part_time/weekends`), `preferred_schedule`
(`morning/afternoon/evening/flexible`), `prior_experience` (`{years 0-80, platforms[]}`),
`start_date` (ISO, hoy o después).

---

## 4. Estado

```python
screening_status(extracted):
    sin carné                 → ("disqualified", "no_license")
    ciudad fuera de cobertura → ("disqualified", "out_of_service_area")
    carné + ciudad cubierta   → ("qualified", None)
    si no                     → ("pending", None)
```

Tres ejes que no se mezclan:

| Eje | Valores | Quién lo pone |
|---|---|---|
| `screening_status` | `pending / qualified / disqualified` (+ `knockout_reason`) | Python, en cada respuesta |
| `completed` | Rita cerró con `end_interview` | el modelo; en chat un mensaje nuevo lo reabre |
| `inactive` | abierta y sin actividad del candidato > 5 min | se deriva en el SQL, no se guarda |

Una corrección ("perdona, sí tengo carné") vuelve a guardar el campo y el estado cambia solo.
No hay estados "pegados" que arreglar a mano.

---

## 5. Un turno de chat

1. `POST /api/chat/start`: devuelve un id nuevo y el saludo fijo. **No toca la BD.**
2. `POST /api/chat/message`: **una transacción** que mantiene el lock de la fila:
   - `ensure_conversation` crea la fila si es el primer mensaje (quien no escribe no deja rastro).
   - `SELECT … FOR UPDATE NOWAIT`: si otro turno tiene el lock → **409**, y el front reintenta.
   - Lee el historial (solo texto; las tools quedan fuera) y los datos guardados.
   - `run_turn`: guardrail de entrada → prompt + línea «Hoy es … · Datos ya guardados» +
     historial + override de idioma → bucle del modelo con tools (máx. 6 iteraciones; si no,
     mensaje de fallo técnico) → limpieza de la salida → estado recalculado. Dos redes en el
     bucle, salidas de las evals:
     - un **segundo `save_answer`** en el mismo turno se rechaza (siempre era el modelo
       rellenando un dato que nadie dio);
     - si aparece un **knock-out nuevo** y Rita se despide sin `end_interview`, se le pide una
       vez que cierre; el candidato recibe su despedida, no dos.
   - El prompt pide **un paso por mensaje** (nombre → carné → ciudad → jornada → turno →
     experiencia → fecha → resumen → agenda) y adapta el registro a español de México si el
     candidato es de allí.
   - `save_turn`: inserta el mensaje del candidato y la respuesta de Rita (con las tools que
     ejecutó, para auditoría) y actualiza datos, estado y resumen. Pone `nudge_count = 0`.
   - Un error de OpenAI → **502** y rollback completo: no quedan turnos a medias.
3. Silencio de 60 s en el front → `POST /api/chat/nudge`. Hasta 3 recordatorios por silencio,
   sin tools y en el idioma del candidato. No cuentan como actividad (`last_activity_at` no
   cambia), así no "reviven" la conversación en el panel.

---

## 6. Una llamada de voz

1. `POST /api/voice/session`: pide a OpenAI una clave efímera con el mismo prompt + reglas de
   voz, las mismas tools, voz `marin`, transcripción, reducción de ruido `near_field` y un VAD
   más estricto (umbral 0,65, 700 ms de silencio) para que el ruido no corte a Rita. No toca la BD.
   Las reglas de voz obligan a **llamar a `save_answer` antes de contestar** (una llamada real
   guardó 0 de 7 campos porque Rita decía "lo apunto" sin guardar) y fijan lo que debe decir en
   el saludo, porque en voz no hay texto fijo.
2. El navegador abre WebRTC con OpenAI (con cancelación de eco y supresión de ruido). Rita habla
   primero.
3. El navegador hace de **cartero**, con las llamadas al back **en cola** (una detrás de otra,
   para no chocar con el lock):
   - tool call → `POST /api/voice/tool` → mismo `dispatch()`, mismo `screening_status()`; el
     estado se relee de Postgres en cada llamada.
   - `search_faq` no toca datos del candidato, así que se ejecuta sin lock.
   - frase terminada → `POST /api/voice/transcript`. La frase del candidato ocupa su sitio
     cuando deja de hablar y recibe el texto al llegar la transcripción, así el orden es el real.
     Nada se guarda hasta que habla el candidato: una llamada sin respuesta no deja fila.
   - Si el back falla, el modelo recibe `{ok:false, error:"unavailable"}` y Rita da el mensaje
     de fallo técnico.
4. Cierre (ADR-029): antes de `end_interview` Rita pregunta «¿Puedo ayudarte en algo más?».
   Tras la despedida, el navegador cuelga solo (con un respaldo de 15 s). Una llamada cerrada
   no se reabre. Si el candidato cuelga antes, lo guardado se queda y a los 5 min sale como
   inactiva.

**Diferencias con el chat:** en voz no hay guardrail de entrada, override de idioma,
recordatorios ni las dos redes del bucle (el audio va directo a OpenAI), y no hay evals.

---

## 7. Agenda (ADR-032)

Solo para aptos, tras confirmar los datos y antes de cerrar. Los huecos salen de un patrón
semanal (`agent/data/slots.json`: lunes a viernes, 10:00-12:00 y 16:00-17:30 cada 30 min,
próximos 14 días) recalculado desde hoy, así la demo no caduca. La reserva va en su propia
columna `interview_at`, porque es una acción del sistema y no algo que dijo el candidato. Durante
el turno viaja como `_interview_at` dentro de los datos, para que Rita vea que ya hay reserva y no
reserve dos veces. Los huecos ofrecidos se guardan con los datos (`_offered_slots`) y se reserva
por número: como el historial del modelo es solo texto, al turno siguiente ya no veía las fechas
ISO e intentaba reconstruirlas con sus palabras ("lunes 26 a las 10:00"). En pantalla: «Añadir a mi calendario» (.ics) o, si no hubo hueco, enlace a
Calendly (`NEXT_PUBLIC_CALENDLY_URL`).

Simplificaciones asumidas: sin zonas horarias (las mismas horas para España y México), sin
bloqueo contra reservas dobles y sin anulación si el candidato deja de ser apto.

---

## 8. Datos

| Tabla | Contenido |
|---|---|
| `conversations` | `id`, `source` (chat/voice), `screening_status`, `knockout_reason`, `completed`, `candidate_name`, `extracted_fields` (JSONB), `summary`, `sentiment`, `interview_at`, `nudge_count`, `created_at`, `last_activity_at` |
| `turns` | Append-only: `role` (user/assistant), `content` (en voz, la transcripción aproximada), `tool_calls` (JSONB, auditoría), `created_at` |
| `recruiters` | `username`, `password_hash` (Argon2) |

Una sola migración idempotente (`IF NOT EXISTS`), aplicada al arrancar.

## 9. Contrato HTTP

| Ruta | Para qué |
|---|---|
| `POST /api/chat/start` · `/message` · `/nudge` | Chat del candidato (§5). Errores: 404, 409, 422, 502 |
| `POST /api/voice/session` · `/tool` · `/transcript` | Voz (§6) |
| `POST /api/recruiter/login` · `/logout`, `GET /api/recruiter/me` | Sesión del reclutador |
| `GET /api/recruiter/conversations` · `/conversations/{id}` | Lista y detalle (tras login) |
| `GET /health` | Healthcheck de Railway |

## 10. Guardrails, idioma, privacidad

- **Prompt de alcance estricto:** reconduce cualquier tema ajeno en una frase y cierra a la
  tercera insistencia.
- **Filtros regex** (`guardrails.py`): bloquean insultos y frases de inyección antes de gastar
  una llamada al modelo; en la salida tapan teléfonos (9 o más dígitos, así una fecha ISO no se
  toca) y nombres de tools que se le escapen al modelo.
- **Idioma:** se detecta en cada turno por stop-words y se fija con un mensaje de sistema al
  final. Sin esto, el modelo se ancla al idioma inicial. Solo ES/EN; cualquier otro idioma →
  español.
- **FAQ** (`agent/faq.py`, ADR-031): 18 entradas en JSON, embeddings `text-embedding-3-small`
  calculados una vez y guardados en memoria, ranking por coseno, top 3. Sin BD vectorial (con
  20 entradas no compensa; con miles, pgvector). Si falla, devuelve cero resultados y Rita pasa
  la duda al equipo: la FAQ nunca rompe la entrevista. Las dudas del puesto no cuentan como
  "fuera de tema".
- **Privacidad:** solo se piden los 7 campos; el prompt prohíbe guardar DNI, dirección o teléfono.

## 11. Pruebas

- `cd back && uv run pytest`: 73 tests sin red (LLM falso inyectable); los de BD se saltan si no
  hay `DATABASE_URL`.
- `cd front && npm test`: 20 e2e con Playwright (chat, voz y panel), con el back simulado.
- `cd back && uv run python -m evals`: 27 casos contra el modelo real (base, edge, agenda, FAQ y
  sentimiento). Comprueban lo que se **guardó** y las tools usadas, no lo que se dijo. La primera
  pasada dio 17/21 y destapó 4 bugs (reserva, datos inventados, cierre en knock-out, fechas
  relativas), ya corregidos; con la suite de entonces (26 casos) ×3 salió 77/78. Fuera de CI a propósito
  (gastan tokens y el modelo no es determinista). Detalle en `back/evals/README.md`.

---

## 12. Decisiones (ADR)

Los números son los que cita el código:

| ADR | Decisión | Por qué |
|---|---|---|
| 001 | El LLM conduce con tool-calling; no hay máquina de estados | Conversación natural con poco código |
| 003 | Un cerebro, dos transportes: chat y voz comparten prompt, tools y `screening_status` | La lógica se escribe una vez; en el panel, una conversación de voz y una de chat son iguales |
| 004 | En voz, Postgres es la memoria entre tool calls | El bucle vive en el navegador; cada POST llega sin estado |
| 006 / 016 | Solo OpenAI: `gpt-5.4-mini` (reasoning `low`) en chat, `gpt-realtime-mini` en voz; conmutables por env | Un SDK, una clave, las mismas tools; sin fábrica multi-proveedor |
| 007 | FastAPI + Next + Postgres en Railway; Next hace de proxy | URL pública viva con `git push`; mismo origen |
| 008 | Monorepo, `uv` + `npm` | Instalaciones reproducibles; `npm` porque `pnpm` pedía permisos de admin |
| 009 | RapidFuzz para la ciudad (umbral 80) | Un match fallido es un candidato mal descartado; acierta "Madird" o "vivo en Valencia" |
| 010 | SQL plano, sin ORM | Tres tablas; el lock y los UPDATE quedan a la vista |
| 011 | Usuario/contraseña con Argon2, cookie firmada (itsdangerous, 8 h), `HttpOnly` + `SameSite=Strict` | Sin tabla de sesiones; aislado tras `require_recruiter` para cambiar a SSO |
| 012 | Saludo fijo, sin llamada al modelo | Rápido, gratis y siempre igual |
| 013 / 017 | El estado se calcula en Python a partir de los datos en cada respuesta | Un knock-out no depende de que el modelo llame a una tool |
| 014 / 015 | `save_answer` tipado; los schemas salen de Pydantic | El modelo interpreta y Python solo comprueba tipos |
| 018 | `inactive` = abierta y sin actividad 5 min, derivado en SQL; recordatorio tras 60 s | Sin jobs ni barridos; no hay estado que se desincronice |
| 020 | Cobertura por ciudad (12, con alias), el mismo catálogo para el matcher y el prompt | Rita no puede inventarse cobertura |
| 021 / 028 | Las correcciones recalculan el estado; en chat un mensaje nuevo reabre una entrevista cerrada | El candidato puede decir "me equivoqué" |
| 023 / 024 / 027 | Esquema con estado calculado; un turno = una transacción con `FOR UPDATE NOWAIT`; 404/409/502 | Nada a medias; dos turnos a la vez fallan rápido en vez de encolarse |
| 025 | El modelo ve el historial solo como texto, más la línea «Datos ya guardados» | Menos tokens; no repite preguntas ya contestadas |
| 026 | Hasta 3 recordatorios por silencio, en tono escalado | Re-engagement sin insistir de más |
| 029 | En voz: «¿algo más?», despedida y cuelgue automático; la llamada no se reabre | Las correcciones tienen que llegar antes de colgar |
| 030 | Rita valora el tono al cerrar; el panel avisa si hubo frustración | Sentimiento sin un segundo modelo |
| 031 | FAQ con RAG ligero en memoria (tool `search_faq`) | Responde con el texto de la empresa sin inventar; sin infra nueva |
| 032 | Agenda con huecos en Python y columna propia, reserva por número; Calendly como plan B | Se puede reservar hablando, también en voz |

La numeración tiene huecos porque es la que cita el código: las decisiones que se sustituyeron
no se renumeran. Una que conviene recordar: una frase de relleno en voz («vale, lo apunto») se
eliminó porque hacía que Rita dijera que guardaba en vez de guardar.

---

## 13. Límites conocidos y qué haría con más tiempo

- **No hay resultado "revisión humana"** ni paso a una persona: los casos ambiguos quedan
  `pending`. Añadir el estado y una cola en el panel.
- **FAQ:** las evals comprueban que Rita busca, no que la respuesta sea correcta (haría falta
  un LLM como juez). La FAQ en JSON exige redeploy para cambiarla.
- **Voz con menos red:** sin guardrail de entrada, override de idioma, recordatorios, el límite
  de un `save_answer` por turno ni evals.
- **Agenda:** índice único en `interview_at`, zona horaria por ciudad, disponibilidad real del
  calendario de cada reclutador.
- **Panel:** filtros y analítica en el front sobre la lista completa; sin paginación. Con
  volumen: filtros y paginación en el servidor y una vista materializada para las métricas.
- **Guardrails regex e idioma por stop-words:** suficientes para la demo; en producción,
  Moderation API y un detector de idioma real.
- **Auth:** usuario/contraseña sin revocación de sesiones → SSO corporativo.
- **Ciudades y huecos en JSON:** cambiarlos exige redeploy → configuración en BD.
- **Escala a 10K/semana:** ~2-3 escrituras/s en pico; la BD no es el cuello de botella. Lo son
  la latencia y los rate limits de OpenAI. La API no tiene estado y escala con réplicas;
  PgBouncer cuando crezcan las réplicas y partición de `turns` por mes.
