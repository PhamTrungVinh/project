# PostgreSQL setup

The default Compose deployment uses PostgreSQL for all application databases
and LangGraph checkpoints. Existing SQLite data is not imported.

Set a strong URL-safe `POSTGRES_PASSWORD` (letters/numbers) in the root `.env` file. Optional settings are
`POSTGRES_USER` (default `support`) and `POSTGRES_PORT` (default `5432`).

Start PostgreSQL from the repository root:

```bash
docker compose up -d postgres
docker compose ps postgres
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d postgres -c "\l"'
```

The initialization script creates `identity`, `ticket`, `booking`, `event`,
`chat`, `memory`, and `checkpoints`. Service migrations create the application
tables automatically when the application containers start. The PostgreSQL image's entrypoint runs initialization
scripts only on an empty data volume.

Data persists in the `postgres17_data` named volume. Avoid `docker compose down -v`
if you want to retain it. Changing the credentials in `.env` after initialization
does not change the existing database roles or passwords.

Containers connect to `postgres:5432`; host processes connect to
`localhost:5432` (or the configured `POSTGRES_PORT`). The published port binds
only to the host's loopback interface.

Start the complete application and apply all service migrations:

```bash
docker compose up --build -d
docker compose ps
```

Both backends wait for PostgreSQL to be healthy. Chat also waits for the business
backend. The graph initializes its checkpoint tables with `PostgresSaver.setup()`.
Local Python tests retain their SQLite defaults unless database URLs are supplied.
