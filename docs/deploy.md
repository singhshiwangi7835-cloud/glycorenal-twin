# Deploying GlycoRenal Twin (free)

**Recommended: Hugging Face Spaces (Docker).** It is free, runs our single Docker image (API + app
in one container, `MODE=all`), gives a public link like `https://<you>-glycorenal-twin.hf.space`,
and has a settings page for secrets. The demo database is created and seeded automatically on
start, so nothing needs to be uploaded.

Alternative: Render (two free web services, API and app); see the end of this page.

## Hugging Face Spaces, step by step (10-15 minutes)

1. Create a free account at https://huggingface.co (or log in).
2. Click your profile picture -> **New Space**.
   - Space name: `glycorenal-twin`
   - License: MIT
   - SDK: **Docker** -> **Blank**
   - Hardware: **CPU basic (free)**
   - Visibility: Private for now (make it Public when you share the link with judges)
   - Click **Create Space**.
3. Connect the code. Easiest way, from PowerShell in the project folder:
   ```
   git remote add space https://huggingface.co/spaces/<your-hf-username>/glycorenal-twin
   git push space main
   ```
   Git asks for a password: use a Hugging Face **access token** with *write* permission
   (huggingface.co -> Settings -> Access Tokens -> New token). It is typed into the Git sign-in
   window, never into chat or a file.
4. Hugging Face needs a short header at the very top of the Space's README. On the Space page open
   **Files -> README.md -> Edit** and make sure the first lines are:
   ```
   ---
   title: GlycoRenal Twin
   sdk: docker
   app_port: 7860
   ---
   ```
5. **Where to enter the environment variables:** Space page -> **Settings** -> **Variables and secrets**.
   | Name | Type | Value |
   |---|---|---|
   | `JWT_SECRET` | **Secret** | a long random string (generate a new one; do not reuse your laptop's) |
   | `LLM_API_KEY` | **Secret** | your Kimi key (optional; without it the assistant uses templates) |
   | `LLM_BASE_URL` | Variable | Kimi base URL from your Kimi dashboard |
   | `LLM_MODEL` | Variable | Kimi model name from your Kimi dashboard |
   | `LLM_FALLBACK_API_KEY` | Secret | optional Gemini key |
   | `LLM_FALLBACK_MODEL` | Variable | optional, e.g. a Gemini model name |
   | `FHIR_BASE_URL` | Variable | optional; default is the public HAPI R4 server |
   Do **not** set `MODE`, `PORT` or `DATABASE_URL`; the image already has the right values.
6. The Space builds (about 5-10 minutes) and starts. The first start seeds the demo data (about a
   minute). Open the Space link and log in with the demo accounts.

Notes:
- Free Spaces sleep after a period without visitors and wake on the next visit (about a minute);
  open the link a few minutes before your presentation.
- The database lives inside the container: it resets on every rebuild or restart. That is fine
  for a demo (it re-seeds itself); use **Admin -> Demo data -> Start demo mode** before presenting.
- The API runs inside the same container and is not public; only the app is.

## Run the same container on any computer with Docker

```
docker build -t glycorenal-twin .
docker run -p 7860:7860 --env-file .env glycorenal-twin
```
Open http://localhost:7860. Or two containers with `docker compose up --build` (API on 8000, app on 8501).

## Alternative: Render (two services)

1. https://render.com -> New -> **Web Service** -> connect the GitHub repo -> Runtime **Docker**.
   - Service 1 (API): environment variable `MODE=api`, port 8000. Add `JWT_SECRET`, `LLM_*` under
     **Environment** (secret values are hidden after saving).
   - Service 2 (app): same repo, `MODE=ui`, `PORT=8501`, `API_URL=https://<your-api-service>.onrender.com`.
2. The free plan sleeps after 15 minutes idle and the disk resets on each deploy (the demo re-seeds).
