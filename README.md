# CloudLink

Acortador de enlaces cloud-native: acorta URLs, redirige con baja latencia y mide
el uso de cada enlace. Arquitectura de microservicios (FastAPI) sobre contenedores,
con PostgreSQL y Redis.

[![CI](https://github.com/tigexpe/practicas-cc/actions/workflows/ci.yml/badge.svg)](https://github.com/tigexpe/practicas-cc/actions/workflows/ci.yml)

**Estado:** Hitos 1 y 2 completados — aplicación, contenerización e integración continua.

## Puesta en marcha

Requiere Docker con Compose.

```bash
cp .env.example .env      # ajusta POSTGRES_PASSWORD
docker compose up -d --build
```

Interfaz en http://localhost:8000

Para parar:

```bash
docker compose down       # detiene y conserva los datos
docker compose down -v    # detiene y BORRA los datos (volúmenes)
```

## Documentación

Toda la documentación del proyecto (dominio, encuadre NIST, arquitectura, API,
decisiones de diseño y limitaciones) está en **[MEMORIA.md](MEMORIA.md)**.

Archivos clave: [`docker-compose.yml`](docker-compose.yml) · [`.github/workflows/ci.yml`](.github/workflows/ci.yml) · [`.env.example`](.env.example)

## Stack

Python 3.12 · FastAPI · PostgreSQL 16 · Redis 7 · Docker Compose · GitHub Actions + GHCR
