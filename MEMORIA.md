# CloudLink: memoria del proyecto

| | |
|---|---|
| **Proyecto** | CloudLink, acortador de enlaces basado en microservicios |
| **Asignatura** | Cloud Computing |
| **Autoría** | Daniel Barea |
| **Fecha** | 24/11/2026 |
| **Repositorio** | https://github.com/tigexpe/practicas-cc |
| **Alcance** | Hitos 1 (aplicación) y 2 (contenedores e integración continua) |

## Índice

1. [Resumen](#1-resumen)
2. [Objetivos y requisitos](#2-objetivos-y-requisitos)
3. [Arquitectura](#3-arquitectura)
4. [Encuadre en la nube (NIST)](#4-encuadre-en-la-nube-nist)
5. [Microservicios](#5-microservicios)
6. [Modelo de datos y eventos](#6-modelo-de-datos-y-eventos)
7. [API](#7-api)
8. [Contenerización](#8-contenerización)
9. [Configuración](#9-configuración)
10. [Pruebas y calidad](#10-pruebas-y-calidad)
11. [Integración continua](#11-integración-continua)
12. [Puesta en marcha](#12-puesta-en-marcha)
13. [Decisiones de diseño](#13-decisiones-de-diseño)
14. [Limitaciones y trabajo futuro](#14-limitaciones-y-trabajo-futuro)
15. [Anexo: estructura del repositorio](#15-anexo-estructura-del-repositorio)

## 1. Resumen

CloudLink convierte direcciones web largas en enlaces cortos, redirige a los visitantes y ofrece estadísticas de uso. Se compone de cuatro microservicios FastAPI, con PostgreSQL para los datos persistentes y Redis como caché y canal de eventos.

El sistema completo se levanta con un comando de Docker Compose. Cada push a la rama principal pasa por análisis estático y tests antes de publicar las imágenes en GitHub Container Registry (GHCR).

## 2. Objetivos y requisitos

### 2.1 Historias de usuario

| ID | Historia | Hito | Implementación |
|---|---|---|---|
| US-01 | Acortar una URL | 1 | `POST /api/links`, código base62 aleatorio y validación con Pydantic |
| US-02 | Alias personalizado | 1 | `custom_code`: 409 si está ocupado, 422 si es inválido o reservado |
| US-03 | Redirigir al destino | 1 | `GET /{code}`: 307 o 404, con caché en Redis |
| US-04 | Contabilizar clics | 1 | Evento en Redis Streams, consumido por analytics |
| US-05 | Estadísticas de un enlace | 1 | `GET /api/stats/{code}`: total, por día y referrers |
| US-06 | Listar y eliminar enlaces | 1 | `GET /api/links` paginado y `DELETE` con invalidación de caché |
| US-07 | Salud del sistema | 1 | `GET /health` agregado: 200 `ok` o 503 `degraded` |
| US-08 | Contenerización reproducible | 2 | Dockerfiles multietapa, Compose, volúmenes y healthchecks |
| US-09 | Integración continua | 2 | GitHub Actions: lint, tests y publicación en GHCR |

### 2.2 Requisitos no funcionales

- **Disponibilidad de la redirección:** un fallo al registrar el clic no impide redirigir.
- **Escalabilidad:** redirect no guarda estado propio cuando usa Redis y admite varias réplicas.
- **Reproducibilidad:** versiones fijadas en las dependencias directas de Python y entorno definido en Compose.
- **Seguridad:** procesos sin privilegios y configuración mediante variables de entorno.

## 3. Arquitectura

```mermaid
flowchart TD
    U[Navegador] -->|:8000| G[gateway]
    G -->|/api/links| S[shortener :8001]
    G -->|"/{code}"| R[redirect :8002]
    G -->|/api/stats| A[analytics :8003]
    R -->|fallo de caché| S
    R -->|caché y XADD| Q[(Redis)]
    S -->|invalida caché| Q
    Q -->|stream clicks| A
    S --> P1[(PostgreSQL: shortener)]
    A --> P2[(PostgreSQL: analytics)]
```

Solo el gateway publica un puerto en el host. Los demás contenedores se comunican por dos redes de Compose: `frontend` (gateway y servicios) y `backend` (servicios, PostgreSQL y Redis). La segunda es interna, por lo que el gateway no alcanza los almacenes de datos. Las dos bases de datos comparten servidor PostgreSQL, pero cada servicio accede únicamente a la suya.

### 3.1 Flujo de una redirección

```mermaid
sequenceDiagram
    participant V as Visitante
    participant G as gateway
    participant R as redirect
    participant C as Redis
    participant S as shortener
    participant A as analytics
    V->>G: GET /demo
    G->>R: GET /demo
    R->>C: GET link:demo
    alt no está en caché
        R->>S: GET /links/demo
        S-->>R: URL de destino
        R->>C: SET link:demo (con TTL)
    end
    R-->>G: 307 Location
    G-->>V: 307 Location
    R->>C: XADD clicks (tarea en segundo plano)
    A->>C: XREADGROUP clicks
    A->>A: guarda el clic en PostgreSQL
    A->>C: XACK
```

### 3.2 Tecnologías

| Tecnología | Uso |
|---|---|
| Python 3.12, FastAPI 0.115.6, Uvicorn 0.34.0 | Servicios HTTP |
| SQLAlchemy 2.0.36 (asíncrono) y asyncpg 0.30.0 | Acceso a PostgreSQL |
| PostgreSQL 16 | Persistencia |
| Redis 7 | Caché y Redis Streams |
| httpx 0.28.1 | Comunicación entre servicios |
| HTML, CSS y JavaScript sin framework | Interfaz web |
| Docker y Docker Compose | Empaquetado y orquestación local |
| GitHub Actions y GHCR | Integración continua y registro de imágenes |
| pytest y ruff | Tests y análisis estático |

## 4. Encuadre en la nube (NIST)

Esta sección sitúa CloudLink en dos marcos de referencia del NIST: la definición de computación en la nube (SP 800-145) y la arquitectura de referencia con sus actores (SP 500-292).

### 4.1 Características esenciales (NIST SP 800-145)

| Característica | Cómo la materializa CloudLink |
|---|---|
| **Autoservicio bajo demanda** | El consumidor crea y gestiona enlaces por la API (`POST /api/links`) sin intervención humana del proveedor. |
| **Acceso amplio a la red** | Todo se expone por HTTP a través del gateway, accesible desde clientes heterogéneos (navegador, curl, móvil). Cada servicio publica su especificación OpenAPI. |
| **Agrupación de recursos** | Una única instancia multi-inquilino sirve los enlaces de todos los usuarios. PostgreSQL y Redis son recursos compartidos y reasignados entre peticiones. |
| **Rápida elasticidad** | Los servicios son stateless. El camino caliente (redirect) escala de forma independiente (`docker compose up --scale redirect=N`) y la ingesta de analítica escala añadiendo consumidores al grupo. |
| **Servicio medido** | El servicio analytics contabiliza cada clic (total, por día, referrers), por lo que el producto es un servicio medido por diseño. Además, el uso de recursos es monitorizable por contenedor. |

### 4.2 Actores (NIST SP 500-292)

| Actor | Quién lo encarna en CloudLink | Impacto económico |
|---|---|---|
| **Consumidor** | El usuario final que acorta y visita enlaces, y el equipo que opera el servicio. | Paga solo por el uso real, sin mantener servidores propios. |
| **Proveedor** | La plataforma que aloja los contenedores: nube pública con capa gratuita o nube privada propia en los Hitos 3-5. En local, el host Docker hace de proveedor. | Pago por uso. El coste se controla escalando solo redirect y destruyendo la infraestructura fuera de laboratorio. |
| **Intermediario (broker)** | GitHub Container Registry como distribución de imágenes. Un posible CDN delante de redirect actuaría también como intermediación. | Reduce la fricción de reparto. |
| **Operador o portador (carrier)** | La conectividad de red (ISP, backbone) que transporta las peticiones. | Coste de tránsito y ancho de banda, sobre todo en la redirección. |
| **Auditor** | La revisión de seguridad y cumplimiento: los análisis del CI (como ruff), la verificación de región UE/RGPD del Hito 4 y el propio alumno. | Previene costes por incidentes y sanciones. |

## 5. Microservicios

### 5.1 gateway (puerto 8000)

Es la única entrada pública. Sirve la interfaz web, reenvía cada petición al servicio correspondiente y agrega el estado de todos en `/health`. Devuelve 503 si el servicio de destino no responde.

La interfaz permite crear, copiar y borrar enlaces, y muestra los clics con un refresco cada 10 segundos.

### 5.2 shortener (puerto 8001)

Es el propietario de los enlaces. Genera códigos de 7 caracteres base62 con el módulo `secrets`, lo que da 62⁷ ≈ 3,5 billones (10¹²) de combinaciones, y prueba hasta 5 candidatos si hay colisión. La unicidad la garantiza la clave primaria.

Los alias admiten de 3 a 32 letras, números, `-` o `_`, salvo las palabras reservadas. Al borrar un enlace elimina su entrada de la caché.

### 5.3 redirect (puerto 8002)

Resuelve un código y responde con 307 y `Cache-Control: no-store`, para que las visitas repetidas también lleguen al sistema y se cuenten. Busca primero en Redis y, si no lo encuentra, consulta a shortener. Publica el clic en una tarea en segundo plano.

### 5.4 analytics (puerto 8003)

Consume el stream `clicks` dentro de un grupo de consumidores, en lotes de hasta 100 eventos. Confirma cada lote después de guardarlo, por lo que la entrega es *al menos una vez*. Calcula total, último clic, clics por día y los 5 referrers principales.

## 6. Modelo de datos y eventos

**Tabla `links`** (base de datos de shortener)

| Columna | Tipo | Notas |
|---|---|---|
| `code` | varchar(32) | Clave primaria |
| `url` | text | Obligatoria |
| `created_at` | timestamptz | UTC |

**Tabla `clicks`** (base de datos `analytics`)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | integer | Clave primaria autoincremental |
| `code` | varchar(32) | Indexada |
| `ts` | timestamptz | Indexada |
| `referrer` | text | Opcional |
| `user_agent` | text | Opcional |

No hay clave foránea entre ambas, ya que pertenecen a servicios distintos. Las estadísticas se conservan al borrar un enlace.

**Redis**

| Clave | Uso |
|---|---|
| `link:{code}` | URL en caché, con TTL configurable (1 hora por defecto) |
| `clicks` | Stream de eventos, limitado a 100 000 entradas |

Contenido de un evento:

```json
{
  "code": "demo",
  "ts": "2026-11-24T18:43:36+00:00",
  "referrer": "https://example.com",
  "user_agent": "Mozilla/5.0"
}
```

## 7. API

Todas las rutas se consumen a través del gateway.

| Método | Ruta | Descripción | Respuestas |
|---|---|---|---|
| `POST` | `/api/links` | Crea un enlace | 201, 409, 422 |
| `GET` | `/api/links?limit=&offset=` | Lista los enlaces (50 por defecto, máximo 500) | 200 |
| `GET` | `/api/links/{code}` | Consulta un enlace | 200, 404 |
| `DELETE` | `/api/links/{code}` | Borra un enlace | 204, 404 |
| `GET` | `/{code}` | Redirige | 307, 404, 503 |
| `GET` | `/api/stats?limit=` | Enlaces más visitados (10 por defecto, máximo 100) | 200 |
| `GET` | `/api/stats/{code}` | Estadísticas de un enlace | 200 |
| `GET` | `/health` | Estado agregado | 200, 503 |

Ejemplo:

```bash
curl -X POST http://localhost:8000/api/links \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com", "custom_code": "demo"}'
```

```json
{
  "code": "demo",
  "url": "https://example.com/",
  "short_url": "http://localhost:8000/demo",
  "created_at": "2026-11-24T18:43:36.346640Z"
}
```

Cada servicio genera su documentación OpenAPI en `/docs`. Desde el host solo es accesible la del gateway.

## 8. Contenerización

### 8.1 Imágenes

Los cuatro Dockerfiles comparten una construcción multietapa:

1. **build:** sobre `python:3.12-slim`, instala las dependencias en `/install`.
2. **runtime:** parte de una imagen limpia, crea el usuario `app` (uid 10001), copia solo las dependencias y `app/`, y ejecuta Uvicorn como ese usuario.

Los `.dockerignore` excluyen cachés, bases de datos locales, entornos virtuales y tests.

| Imagen | Tamaño en disco | Contenido comprimido |
|---|---|---|
| `cloudlink-gateway` | 235 MB | 56,2 MB |
| `cloudlink-redirect` | 239 MB | 56,9 MB |
| `cloudlink-shortener` | 287 MB | 67,2 MB |
| `cloudlink-analytics` | 287 MB | 67,2 MB |

### 8.2 Orquestación

[docker-compose.yml](docker-compose.yml) define el proyecto `cloudlink` con seis contenedores:

- **Orden de arranque:** shortener y analytics esperan a que PostgreSQL y Redis estén sanos; redirect espera a Redis. El gateway arranca tras los otros tres servicios.
- **Salud:** los servicios consultan su `/health` con `urllib` de Python; PostgreSQL usa `pg_isready` y Redis, `redis-cli ping`.
- **Recuperación:** los cuatro servicios usan `restart: unless-stopped`.
- **Persistencia:** volúmenes `cloudlink_pgdata` y `cloudlink_redisdata`; Redis usa además AOF.
- **Inicialización:** [init.sql](infra/postgres/init.sql) crea la base de datos `analytics` la primera vez.

## 9. Configuración

Se lee del entorno o de un archivo `.env`, excluido de Git. La plantilla es [.env.example](.env.example).

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Base de los enlaces cortos |
| `POSTGRES_USER` | `app` | Usuario de PostgreSQL |
| `POSTGRES_PASSWORD` | `app` | Contraseña; debe cambiarse en un despliegue real |
| `POSTGRES_DB` | `shortener` | Base de datos de shortener |
| `CODE_LENGTH` | `7` | Longitud de los códigos aleatorios |
| `CACHE_TTL_SECONDS` | `3600` | Duración de la caché |

PostgreSQL aplica usuario, contraseña y base de datos solo al crear el volumen.

## 10. Pruebas y calidad

| Servicio | Tests | Qué comprueban |
|---|---|---|
| shortener | 10 | Crear, consultar y borrar; alias válido, duplicado, con formato inválido y reservado |
| analytics | 1 | Ingesta de un evento y estadísticas resultantes |
| redirect | 2 | `/health` y raíz sin ruta (404) |
| gateway | 3 | Interfaz en la raíz y `/health` sano y degradado |

Los 16 tests usan `TestClient` de FastAPI. Los de shortener y analytics se ejecutan contra PostgreSQL, y todos sin Redis. El análisis estático se hace con `ruff check services`.

**Verificación de extremo a extremo.** El 24/11/2026 se levantó el sistema con Docker en WSL, con los seis contenedores en estado `healthy`:

| Comprobación | Resultado |
|---|---|
| Crear enlace con alias | 201 |
| Repetir el alias | 409 |
| Dos visitas al enlace | 307 en ambas |
| Estadísticas, mediante Redis Streams | 2 clics |
| Borrar el enlace | 204 |
| Visitarlo tras borrarlo | 404 inmediato |
| Usuario de los cuatro servicios | uid 10001 |

Estas comprobaciones se hicieron a mano, fuera de los tests automáticos. No se han realizado pruebas de carga.

## 11. Integración continua

[ci.yml](.github/workflows/ci.yml) se ejecuta en push y pull request a `main` o `master`:

1. **test:** un trabajo por servicio, con PostgreSQL como servicio auxiliar. Instala dependencias, ejecuta ruff y lanza pytest.
2. **publish:** solo en push y si pasan todos los tests. Construye y publica las cuatro imágenes etiquetadas con el SHA del commit.

```text
ghcr.io/tigexpe/practicas-cc/<servicio>:<sha>
```

La [primera ejecución](https://github.com/tigexpe/practicas-cc/actions/runs/45494561185), del commit `fbcf4de`, terminó en verde en 1 min 31 s: 4 trabajos de test y 4 de publicación.

## 12. Puesta en marcha

Requiere Docker con Compose. Los comandos se ejecutan desde la raíz del repositorio, en Linux o WSL.

```bash
# 1. Configuración: editar POSTGRES_PASSWORD después de copiar
cp .env.example .env

# 2. Construir y arrancar
docker compose up -d --build

# 3. Comprobar
docker compose ps
curl http://localhost:8000/health
```

La interfaz queda en http://localhost:8000.

| Operación | Comando |
|---|---|
| Ver registros | `docker compose logs -f` |
| Escalar redirect | `docker compose up -d --scale redirect=3` |
| Parar conservando los datos | `docker compose down` |
| Parar y **borrar los datos** | `docker compose down -v` |

Para ejecutar los tests hace falta Python 3.12 y un PostgreSQL de pruebas. Con un entorno virtual activo:

```bash
docker run -d --rm --name cloudlink-test -p 5432:5432 \
  -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test postgres:16-alpine
export DATABASE_URL=postgresql+asyncpg://test:test@localhost:5432/test REDIS_URL=

for s in gateway shortener redirect analytics; do
  pip install -r services/$s/requirements.txt
done
pip install -r requirements-dev.txt
ruff check services
for s in gateway shortener redirect analytics; do
  (cd services/$s && python -m pytest tests -v)
done
docker stop cloudlink-test
```

## 13. Decisiones de diseño

| Decisión | Motivo | Contrapartida |
|---|---|---|
| Separar redirect de shortener | La lectura recibe más tráfico y escala por su cuenta | Un salto de red adicional si falla la caché |
| Redis Streams para los clics | Desacopla la redirección y conserva eventos si analytics cae | Estadísticas con consistencia eventual y posibles duplicados |
| Una base de datos por servicio | Independencia entre esquemas | Sin integridad referencial entre enlaces y clics |
| Un solo servidor PostgreSQL | Menor consumo de recursos | Punto único de fallo compartido |
| Redirección 307 | Los navegadores no la memorizan y cada visita se cuenta | Más peticiones que con una redirección permanente |
| Gateway propio en FastAPI | Misma tecnología y control del enrutado | Menos funciones que un proxy especializado |
| Etiqueta por SHA | Cada imagen se puede rastrear hasta su commit | No hay etiqueta `latest` ni de versión |

## 14. Limitaciones y trabajo futuro

**Seguridad**
- No hay autenticación: cualquiera con acceso puede listar y borrar todos los enlaces.
- No hay límite de peticiones ni detección de destinos maliciosos. El TLS debe aportarlo un proxy externo.
- La contraseña de PostgreSQL tiene un valor por defecto y Redis no usa contraseña.

**Robustez**
- Si Redis deja de responder, la redirección falla, porque la lectura de la caché no captura ese error.
- El `/health` de cada servicio no comprueba PostgreSQL ni Redis.
- Los eventos pendientes se recuperan solo al arrancar un consumidor con el mismo nombre. El nombre por defecto es el del contenedor, así que recrearlo puede dejar eventos sin procesar; se resolvería con `XAUTOCLAIM`.
- Un evento puede perderse si Redis falla al publicarlo o contarse dos veces si analytics cae antes de confirmarlo.
- Las tablas se crean al arrancar, sin migraciones versionadas.

**Funcionalidad e infraestructura**
- La interfaz muestra clics solo de los 100 enlaces más visitados.
- Los tests no cubren Redis ni la redirección completa.

**Siguientes pasos:** autenticación, migraciones con Alembic, recuperación de eventos, tests de integración, observabilidad y despliegue en la nube.

## 15. Anexo: estructura del repositorio

```text
.
├── .github/workflows/ci.yml
├── docker-compose.yml
├── .env.example
├── infra/postgres/init.sql
├── requirements-dev.txt
├── ruff.toml
├── README.md
├── MEMORIA.md
└── services/
    ├── gateway/
    │   ├── app/main.py
    │   ├── app/static/index.html
    │   ├── tests/
    │   ├── Dockerfile
    │   ├── .dockerignore
    │   └── requirements.txt
    ├── shortener/     (misma estructura, sin static/)
    ├── redirect/      (misma estructura, sin static/)
    └── analytics/     (misma estructura, sin static/)
```
