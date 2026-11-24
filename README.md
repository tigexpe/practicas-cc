# CloudLink — acortador de enlaces con FastAPI y microservicios

```
                    ┌──────────────┐
   navegador ─────▶ │   gateway    │ :8000  (frontend + enrutado)
                    └──────┬───────┘
         /api/links        │ /{code}           /api/stats
      ┌────────────────────┼──────────────────────┐
      ▼                    ▼                      ▼
┌───────────┐  HTTP  ┌───────────┐          ┌───────────┐
│ shortener │◀───────│ redirect  │          │ analytics │
│   :8001   │        │   :8002   │          │   :8003   │
└─────┬─────┘        └─────┬─────┘          └─────┬─────┘
      │                    │ caché + XADD         │ XREADGROUP
      ▼                    ▼                      ▼
 Postgres (db shortener)   Redis  ── stream "clicks" ──▶  Postgres (db analytics)
```

| Servicio | Responsabilidad |
|---|---|
| **gateway** | Único punto público. Sirve la web y hace de proxy a los demás servicios. `/health` agrega el estado de todos. |
| **shortener** | Dueño de los enlaces: crear (código aleatorio o alias), listar, consultar, borrar. Base de datos propia. |
| **redirect** | Ruta caliente: resuelve `/{code}` con caché en Redis y redirige (307). Publica un evento de clic sin bloquear la respuesta. Escalable con `--scale redirect=N`. |
| **analytics** | Consume el stream `clicks` como grupo de consumidores, guarda los clics y expone estadísticas (total, por día, referrers). |

## Arrancar con Docker

```powershell
docker compose up --build
```

Abre http://localhost:8000. Para cambiar credenciales o dominio, copia `.env.example` a `.env` y edítalo antes del primer arranque.


## API (a través del gateway)

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/links` | `{"url": "...", "custom_code": "opcional"}` → 201 con `short_url` |
| `GET` | `/api/links` | Lista (`?limit=&offset=`) |
| `GET` | `/api/links/{code}` | Detalle |
| `DELETE` | `/api/links/{code}` | Borra (204) |
| `GET` | `/{code}` | Redirige al destino (307) |
| `GET` | `/api/stats` | Enlaces más visitados |
| `GET` | `/api/stats/{code}` | Clics totales, por día y referrers |
| `GET` | `/health` | Estado de todos los servicios |

Cada servicio expone además su documentación OpenAPI en `/docs`, accesible solo desde la red interna de compose salvo la del gateway.
