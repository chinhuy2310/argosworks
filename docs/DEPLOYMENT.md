# ARGOS WORKS — Deployment Runbook (self-hosted)

This is the operational path that the `deploy.bat` / `deploy.sh` scripts actually
execute. Everything below was verified against the repository's own scripts.

## 1. Prerequisites

| Requirement | Notes |
| --- | --- |
| Docker Engine 24+ with Compose v2 | `docker compose version` must succeed |
| Python 3.9+ (optional) | Only used by the local bootstrap script; PowerShell/openssl fallbacks exist |
| 4 GB RAM / 2 vCPU | Minimum for the app + Caddy; PostgreSQL needs ~512 MB more |

## 2. First start

**Windows**

```bat
deploy.bat
```

**Linux / macOS**

```bash
chmod +x deploy.sh
./deploy.sh
```

Both scripts call `scripts/init_deploy.py` (or `scripts/init_deploy.ps1` when
Python is absent) before `docker compose up`. The bootstrap is idempotent and
performs three steps:

1. **`.env`** — created from `.env.example` with freshly generated
   `ARGOS_MASTER_KEY` (32 random bytes, hex), `POSTGRES_PASSWORD` and
   `ARGOS_LICENSE_SECRET`. Any template placeholder is replaced.
2. **`server/config.json`** — created as a *file* from `server/config.example.json`.
   This matters: `docker-compose.yml` bind-mounts that single file, and if it is
   missing Docker creates a **directory** instead, after which the application can
   no longer persist settings.
3. **`data/`, `data/backups/`, `data/attachments/`, `data/templates/`, `logs/`**.

You can also run the bootstrap on its own:

```bash
python scripts/init_deploy.py          # prepare/repair a checkout
python scripts/init_deploy.py --check  # verify only, exit 1 when something is missing
```

## 3. Secrets

`ARGOS_MASTER_KEY` encrypts secrets stored at rest (integration credentials,
SMTP passwords, etc.). `POSTGRES_PASSWORD` is consumed by both the database
container and `DATABASE_URL`.

The bootstrap **never rotates an existing secret implicitly**, because:

* a new `ARGOS_MASTER_KEY` makes every value encrypted with the old key
  unreadable — it looks exactly like data loss;
* a new `POSTGRES_PASSWORD` must also be applied inside PostgreSQL
  (`ALTER USER argos_admin WITH PASSWORD '...'`), otherwise the app stops
  connecting.

Deliberate rotation:

```bash
python scripts/init_deploy.py --rotate   # regenerates all three secrets
# PowerShell fallback:
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\init_deploy.ps1 -Rotate
```

A backup copy of the previous `.env` is written next to it
(`.env.bak-YYYYMMDDHHMMSS`). Keep `.env` out of version control — it holds the
master key.

## 4. Post-start checks

```bash
docker compose ps          # argos-works, argos-proxy, argos-postgres must be Up
docker compose exec argos-works curl -fsS http://localhost:8080/api/health
curl -k https://localhost/api/health        # through Caddy
```

Only Caddy publishes reachable host ports (80/443); PostgreSQL is bound to
`127.0.0.1:5432` and the app container is only reachable on the internal network
as `argos-works:8080`. That is why `TRUSTED_PROXIES` defaults to the Docker bridge
range — the app only honours `X-Forwarded-For` from the proxy.

Then open `https://localhost` (`https://<DOMAIN>` when `DOMAIN` is set). A fresh
instance redirects to `/setup`, which needs:

* a **license key** (`ARGOS_LICENSE_SECRET` signs it; the key is issued per
  customer), and
* if `ARGOS_BOOTSTRAP_TOKEN` is set in `.env`, the same value must be supplied to
  `/api/setup/complete`. Set it before the first start on any host reachable from
  an untrusted network, otherwise the first visitor can become the admin.

## 5. Upgrades

```bash
git pull
python scripts/init_deploy.py     # repairs .env / config.json if a file is missing
docker compose up -d --build
```

`.env` and `data/` are preserved; existing secrets are left untouched. The
application applies schema migrations on start (`schema_migrations` table).

## 6. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `docker compose` aborts with `bắt buộc đặt ARGOS_MASTER_KEY` | `.env` is missing or the key is empty — run `python scripts/init_deploy.py` |
| `server/config.json is a directory` | A previous start ran without the file. `rmdir server/config.json`, then re-run the bootstrap |
| Login succeeds but settings do not persist | `server/config.json` is not writable by the container user (check the bind mount) |
| Every client appears as `172.x.x.x` in the audit log | The proxy is outside `TRUSTED_PROXIES`; extend that value with the proxy's IP/CIDR |
| `password authentication failed for user "argos_admin"` | `POSTGRES_PASSWORD` was changed after the volume was initialised, or `DATABASE_URL` no longer matches it |

## 7. Backups

`BACKUP_DIR` (default `./data/backups`) receives database dumps; PostgreSQL uses
`pg_dump` through `services/backup_manager.py`. Point it at a mounted volume or
NAS path and copy the directory off-box — a backup that only exists on the same
disk is not a backup.
