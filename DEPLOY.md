# Deploying DICS AI System to Render (free tier)

## Why Postgres instead of SQLite
Render's free web services have an ephemeral filesystem -- any local file
(SQLite DB, uploaded citizen-report photos) is wiped on every restart or
redeploy. To stay on the free tier, this deploy uses Render's free managed
Postgres for the database instead. Uploaded photos in
instance/uploads/citizen_reports are NOT persisted with this setup -- they
will be lost on redeploy. If that becomes a problem, either upgrade to a
paid instance + persistent disk, or wire up external storage (e.g.
Cloudinary, S3) for uploads.

## Code changes made for this deploy
- `app.py`: fixed `postgres://` -> `postgresql://` scheme (SQLAlchemy 1.4+
  requires the latter; Render's connection strings use the former).
- `app.py`: legacy SQLite-only migration patches (`migrate_user_table`,
  `migrate_incident_commander_tables`) now only run when the DB is
  actually SQLite. On Postgres, `db.create_all()` already builds the
  full current schema from `models.py`, so these patches (written for
  upgrading old SQLite files) are unnecessary there.
- `blueprints/admin.py`: the "Export Backup" admin feature only works
  against a SQLite file. It now shows a friendly message on Postgres
  instead of silently producing an empty/broken backup file. Use
  Render's built-in Postgres backups, or `pg_dump`, instead.
- `requirements.txt`: added `psycopg2-binary` (Postgres driver) and
  `gunicorn` (production server).
- `render.yaml`: new -- provisions free Postgres + free Python web
  service, wires `DATABASE_URL` automatically, generates `SECRET_KEY`.

## Steps
1. Push this repo to GitHub.
2. Render Dashboard -> New -> Blueprint -> connect your repo.
3. Render creates `dics-postgres` (free Postgres) and `dics-ai-system`
   (free web service) and wires them together automatically.
4. First request triggers `lazy_init()`, which creates all tables via
   SQLAlchemy and seeds the default admin account + agencies.
5. Log in and change the default admin password immediately.

## Things to know about the free tier here
- Free web services spin down after 15 minutes of inactivity; the next
  request triggers a ~30-60s cold start.
- Free Postgres on Render expires 30 days after creation unless
  upgraded -- fine for testing, not for long-term production use.
- Single gunicorn worker is intentional: the app's APScheduler job and
  lazy DB init use in-process flags, so multiple workers would each
  start their own duplicate scheduler.
