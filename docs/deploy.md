# Deploying (free tier: Render + Neon)

The API runs as a Docker web service on Render. The database is Postgres with pgvector on Neon.
Render's own free Postgres expires after 30 days, which is why the database lives on Neon.

Free-tier behaviour to expect:

- Render sleeps the service after 15 minutes without traffic. The first request after that takes
  about a minute.
- Neon scales the database to zero after 5 minutes idle. The first query is slower.
- This is a demo host, not production. Sign-ups are capped (`MAX_USERS`) and the model is the
  scripted fake (`LLM_PROVIDER=fake`), so no model spend is possible.

## 1. Database (Neon)

1. Create a project at neon.com (free plan, no card). Pick the region closest to Render's.
2. Open Connect, switch **Connection pooling off**, and copy the connection string. Use the direct
   string: the pooled one runs through PgBouncer, which can break prepared statements in psycopg 3.
3. It looks like `postgresql://user:pw@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require`. Paste it
   as is. The app rewrites it to `postgresql+psycopg://` itself.
4. Nothing else is needed: the first migration runs `CREATE EXTENSION IF NOT EXISTS vector`.

## 2. API (Render)

1. Push this repo to GitHub (done).
2. In Render choose New, then Blueprint, and select the repo. It reads `render.yaml`.
3. When asked for `DATABASE_URL`, paste the Neon string. `SECRET_KEY` is generated for you.
4. Wait for the deploy. The container runs `alembic upgrade head` on every start, then the server.
5. Open `https://<service>.onrender.com/health/ready`. It should answer 200.
6. If the log says no open port was detected, add an environment variable `PORT=8000` in the
   dashboard. The container honours `$PORT` and falls back to 8000.

## 3. Try it

- API docs: `https://<service>.onrender.com/docs`
- Seeded walk-through against the hosted URL: `python -m app.demo.run --base-url https://<service>.onrender.com`
  (this creates `demo@example.com` on the hosted database; the credentials are public by design).

## Known limits

- No per-IP rate limiting. The sign-up cap is the only brake on abuse.
- Neon's free database holds 1 GB. At 200 users that is far more than enough.
- Logs are on Render's dashboard only and are lost when the service is rebuilt.
