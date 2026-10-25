# Propuesta de integración con el ATS

Estado: **propuesta de diseño**, sin implementar. Contrato de la API en
[`openapi.yaml`](openapi.yaml).

## Qué problema resuelve

Hoy el reclutador ve la ficha en el panel de Rita y luego tiene que pasarla a mano al
ATS de Grupo Sazón, donde vive el proceso de verdad: oferta, entrevistas,
contratación. Con 13 reclutadores y ~1.000 solicitudes a la semana, copiar fichas es
justo el trabajo que queríamos quitarles.

La integración hace dos cosas:

1. **El ATS lleva al candidato a Rita.** Cuando alguien aplica a una oferta de
   repartidor, el ATS pide una entrevista y recibe un enlace para mandárselo.
2. **Rita devuelve el resultado al ATS.** Al cerrar la entrevista, el ATS recibe la
   ficha: estado, datos validados, resumen, tono, entrevista reservada y enlace a la
   transcripción.

El ATS sigue siendo la fuente de verdad del candidato y del proceso. Rita solo es
dueña de la conversación y de su resultado.

## Principios

- **Agnóstico del proveedor.** Grupo Sazón no tiene ATS elegido en el enunciado. Rita
  expone un contrato propio y pequeño; lo que cambia según el ATS (Greenhouse,
  Workable, Teamtailor, uno interno…) es un **adaptador** fino, no el agente.
- **Eventos al ATS, no consultas.** Rita avisa con un webhook cuando pasa algo; el ATS
  no tiene que preguntar cada X minutos. Si lo prefiere, también puede leer por API.
- **Nada se pierde.** Un evento que el ATS no acepta se reintenta y no bloquea la
  entrevista: el candidato nunca nota que el ATS está caído.
- **Mínimos datos.** Solo viajan los 7 campos del cribado y el resultado. Rita no
  pide ni guarda nada más del candidato.

## Flujo

```
Candidato aplica en el ATS
        │
        ▼
ATS ──POST /ats/v1/screenings──▶ Rita        ← crea la entrevista con su external_id
        ◀── 201 { screening_id, interview_url }
        │
ATS manda el enlace al candidato (email/SMS/WhatsApp)
        │
        ▼
Candidato habla con Rita (chat o voz)
        │
        ▼
Rita ──webhook screening.completed──▶ ATS     ← resultado, datos, resumen, tono
Rita ──webhook interview.booked────▶ ATS      ← si es apto y reservó entrevista
Rita ──webhook screening.updated───▶ ATS      ← si corrige algo después de cerrar
        │
        ▼
ATS mueve al candidato de etapa y asigna al reclutador
```

Si un candidato llega a Rita sin pasar por el ATS (enlace directo, campaña), la
entrevista se crea igual sin `external_id`. Al cerrarla, el webhook lleva
`external_id: null` y el adaptador crea el candidato en el ATS.

## Contrato (resumen)

### Rita expone (el ATS llama)

| Método y ruta | Qué hace |
|---|---|
| `POST /ats/v1/screenings` | Crea una entrevista para un candidato del ATS. Idempotente por `external_id`: repetir la llamada devuelve la misma. Responde `screening_id` y `interview_url`. |
| `GET /ats/v1/screenings/{id}` | Estado actual y resultado. Para reconciliar o si el ATS prefiere leer. |
| `GET /ats/v1/screenings?updated_since=…` | Lista de cambios desde una fecha, paginada: para recuperarse tras una caída larga. |
| `POST /ats/v1/screenings/{id}/cancel` | La oferta se cerró o el candidato se retiró: el enlace deja de funcionar. |
| `DELETE /ats/v1/screenings/{id}` | El candidato pide borrar sus datos: Rita borra la conversación y la transcripción. |

### Rita emite (webhooks al ATS)

| Evento | Cuándo | Qué lleva |
|---|---|---|
| `screening.completed` | Rita cierra la entrevista | Estado (`qualified` / `disqualified`), motivo, los 7 campos, resumen, tono, canal, enlace a la transcripción |
| `screening.updated` | El candidato corrige un dato tras cerrar y el resultado cambia | La ficha completa de nuevo (no un diff) |
| `interview.booked` | Un apto reserva hueco de entrevista | Fecha y hora, ciudad |
| `screening.inactive` | 24 h sin respuesta y sin cerrar | Lo recogido hasta el momento, con estado `pending` |

Todos los eventos llevan la **ficha completa** y un `version` creciente. El ATS
aplica el de versión más alta y descarta los viejos, así el orden de llegada no importa.

Ejemplo de `screening.completed`:

```json
{
  "event_id": "evt_01JB7Q8Z3K",
  "type": "screening.completed",
  "occurred_at": "2026-10-24T10:04:12Z",
  "screening": {
    "screening_id": "9b2f6c1e-4a7d-4f0b-9a51-2c3d8e7f6a10",
    "external_id": "greenhouse-app-482913",
    "version": 3,
    "channel": "chat",
    "status": "qualified",
    "knockout_reason": null,
    "completed": true,
    "fields": {
      "full_name": "Marta López",
      "has_driver_license": true,
      "city": "Madrid",
      "availability": ["full_time"],
      "preferred_schedule": ["morning"],
      "prior_experience": { "years": 2, "platforms": ["Glovo"] },
      "start_date": "2026-12-01"
    },
    "summary": "Repartidora con 2 años en Glovo, carné y disponibilidad completa por las mañanas en Madrid. Puede empezar el 1 de diciembre.",
    "sentiment": "positive",
    "interview_at": "2026-10-27T10:00",
    "transcript_url": "https://rita.gruposazon.example/recruiter/9b2f6c1e-…",
    "started_at": "2026-10-24T10:00:03Z",
    "completed_at": "2026-10-24T10:04:12Z"
  }
}
```

## Fiabilidad

- **Outbox en Postgres.** El evento se guarda en una tabla `ats_outbox` **en la misma
  transacción** que el turno que lo provoca. Un worker lo envía después. Si el turno
  falla, no hay evento; si el envío falla, el turno no se pierde.
- **Reintentos** con espera creciente (1 min, 5 min, 30 min, 2 h… hasta 24 h). Tras eso,
  el evento queda como fallido en el panel y se puede reenviar a mano.
- **Entrega "al menos una vez".** El ATS puede recibir un evento repetido: lo reconoce
  por `event_id` y lo ignora.
- **Reconciliación.** Una vez al día, el adaptador compara con
  `GET /screenings?updated_since=` para cazar lo que se hubiera escapado.

## Seguridad y privacidad

- **ATS → Rita:** API key por cliente en cabecera (`Authorization: Bearer`), con
  permisos solo sobre `/ats/v1`. En producción, OAuth 2 client credentials si el ATS
  lo soporta.
- **Rita → ATS:** cada webhook va firmado con HMAC-SHA256 del cuerpo y una marca de
  tiempo (`X-Rita-Signature`, `X-Rita-Timestamp`). El ATS rechaza firmas inválidas o de
  más de 5 minutos, para evitar repeticiones.
- **Datos:** solo los 7 campos del cribado. La transcripción no viaja en el webhook:
  va un enlace al panel, tras login. Si el candidato pide borrar sus datos (RGPD / LFPDPPP
  en México), el ATS llama a `DELETE` y Rita borra conversación y turnos.

## Mapeo al ATS

Lo concreto de cada ATS vive en el adaptador. Cómo se traduce, en general:

| Rita | ATS (típico) |
|---|---|
| `qualified` | Avanza la candidatura a "Entrevista" y la asigna al reclutador de la ciudad |
| `disqualified` + `knockout_reason` | Rechazo con motivo; el ATS decide si manda su email de rechazo |
| `pending` / `screening.inactive` | Se queda en "Cribado" con una etiqueta para seguimiento manual |
| `fields.*` | Campos personalizados de la candidatura |
| `summary`, `sentiment` | Nota en la candidatura |
| `interview_at` | Evento de entrevista en el calendario del ATS |
| `transcript_url` | Enlace en la nota |

## Qué cambia en Rita

Poco, porque la base ya está pensada para esto:

- **Ya está:** el estado y los datos tipados que calcula el código, el resumen y el tono
  al cerrar, la entrevista en su propia columna (`interview_at`, pensada para que la
  lea un tercero) y la transcripción completa.
- **Habría que añadir:**
  - columnas `external_id` y `version` en `conversations`;
  - la tabla `ats_outbox` y su worker;
  - el router `/ats/v1` con su API key;
  - un adaptador para el ATS elegido.

## Fases

1. **Salida, solo lectura:** webhooks de `screening.completed` e `interview.booked` y
   la API `GET`. El reclutador deja de copiar fichas. Es lo que más ahorra.
2. **Entrada:** `POST /screenings` para que el ATS mande el enlace al aplicar. El
   candidato recibe la entrevista en minutos, no cuando un reclutador lo llame.
3. **Ciclo completo:** `screening.updated`, `screening.inactive`, cancelación, borrado
   y reconciliación diaria.

## Preguntas abiertas para Grupo Sazón

- ¿Qué ATS usan, y admite webhooks entrantes o solo API?
- ¿Quién manda el enlace al candidato: el ATS o Rita (WhatsApp, email)?
- ¿El rechazo lo comunica Rita en la conversación, el ATS por email, o los dos?
- ¿Las entrevistas se agendan en el calendario del ATS o en el de cada reclutador?
- ¿Cuánto tiempo hay que guardar las transcripciones?
