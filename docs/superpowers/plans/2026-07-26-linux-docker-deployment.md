# GenImage Linux Docker Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package GenImage for Linux with Docker Compose, expose the complete application on port 8083, persist new SQLite data, and publish the verified `master` branch to `zhangjietest666/GenImage`.

**Architecture:** A multi-stage frontend image builds Vue with Node and serves it through Nginx. Nginx is the only public service and proxies `/api/*` plus `/health` to an internal FastAPI container. A named Docker volume mounted at `/app/backend/data` persists the SQLite database without copying local data into the image or repository.

**Tech Stack:** Docker Compose, Python 3.13, FastAPI/Uvicorn, Node.js 22, Vue/Vite, Nginx Alpine, SQLite

---

### Task 1: Repository and build-context hygiene

**Files:**
- Modify: `.gitignore`
- Create: `.dockerignore`

- [ ] **Step 1: Extend Git ignore rules**

Add explicit entries for `.codegraph/`, `.cursor/`, `.firecrawl/`, `note.txt`, `testfiles/`, logs, virtual environments, Node dependencies, build output, and all SQLite sidecar files. Preserve the existing rules.

- [ ] **Step 2: Add Docker build-context exclusions**

Create `.dockerignore` with the same local-only paths plus `.git/`, documentation, tests, caches, and local environment files. Keep `backend/app`, `backend/requirements.txt`, and all frontend source/build manifest files in the context.

- [ ] **Step 3: Verify ignored local data**

Run:

```bash
git status --short --ignored
git check-ignore -v note.txt testfiles backend/data/genimage.db .codegraph .cursor .firecrawl
```

Expected: every named local-only path is ignored and none is staged.

### Task 2: Backend container

**Files:**
- Create: `backend/Dockerfile`

- [ ] **Step 1: Define the backend image**

Use `python:3.13-slim`, install `backend/requirements.txt` without pip cache, copy `backend/app` into `/app/backend/app`, create `/app/backend/data`, and run as an unprivileged `app` user. Start with:

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
```

- [ ] **Step 2: Build the backend image**

Run:

```bash
docker build -f backend/Dockerfile -t genimage-backend:test .
```

Expected: build exits with status 0 and does not copy `backend/data/genimage.db` into the image.

### Task 3: Frontend and Nginx container

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`

- [ ] **Step 1: Define the frontend multi-stage image**

Use `node:22-alpine` as the builder, run `npm ci` and `npm run build`, then copy `frontend/dist` into `nginx:1.27-alpine`. Copy the production Nginx configuration to `/etc/nginx/conf.d/default.conf`.

- [ ] **Step 2: Configure routing and proxy limits**

Configure SPA fallback with `try_files`, proxy `/api/` and exact `/health` requests to `http://backend:8002`, preserve standard proxy headers, allow request bodies up to 25 MB, and set connect/read/send timeouts to 300 seconds.

- [ ] **Step 3: Build the frontend image**

Run:

```bash
docker build -f frontend/Dockerfile -t genimage-web:test .
```

Expected: Vite production build and Nginx image creation both exit with status 0.

### Task 4: Compose orchestration and deployment script

**Files:**
- Create: `compose.yaml`
- Create: `deploy.sh`

- [ ] **Step 1: Define Compose services**

Create `backend` and `web` services from the two Dockerfiles. Expose only `8083:80` on `web`; use `expose: 8002` for `backend`. Mount a stable named volume `genimage_data` at `/app/backend/data`, add health checks for both services, make `web` depend on a healthy backend, and set `restart: unless-stopped`.

- [ ] **Step 2: Add the deployment command**

Create an executable Bash script with `set -Eeuo pipefail`, verify Docker and Compose are available, validate the Compose file, and execute:

```bash
docker compose up -d --build --wait --wait-timeout 180
docker compose ps
```

- [ ] **Step 3: Validate Compose**

Run:

```bash
docker compose config --quiet
```

Expected: exit status 0, only `web` publishes a host port, and the volume resolves to `genimage_data`.

### Task 5: Operator documentation

**Files:**
- Create: `README.md`

- [ ] **Step 1: Document first deployment and updates**

Document the prerequisites, SSH clone URL, `chmod +x deploy.sh`, `./deploy.sh`, access URL `http://SERVER_IP:8083/`, API Key setup through the UI, `git pull --ff-only`, logs, status, restart, and shutdown without deleting the volume.

- [ ] **Step 2: Document SQLite backup**

Document a backup command using a temporary Alpine container with the stable `genimage_data` volume. State that local API keys, history, images, and SQLite files are not migrated or committed.

### Task 6: Full local verification

**Files:**
- Verify only

- [ ] **Step 1: Run backend tests**

Run:

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests -q
```

Expected: all backend tests pass.

- [ ] **Step 2: Run frontend tests and production build**

Run:

```bash
npm --prefix frontend test -- --run
npm --prefix frontend run build
```

Expected: all frontend tests pass and Vite exits with status 0.

- [ ] **Step 3: Start the production stack**

Run:

```bash
docker compose up -d --build --wait --wait-timeout 180
docker compose ps
```

Expected: both services are running and healthy.

- [ ] **Step 4: Verify the public routes**

Run requests against:

```text
http://127.0.0.1:8083/
http://127.0.0.1:8083/health
http://127.0.0.1:8083/api/settings
```

Expected: the frontend returns HTTP 200, health returns `{"status":"ok"}`, and settings returns HTTP 200 with the fixed base URL and API Key configured state.

- [ ] **Step 5: Verify named-volume persistence**

Update the model through `PUT /api/settings`, force-recreate the backend container without deleting volumes, then read `/api/settings` again.

Expected: the selected model remains after container replacement and `docker volume inspect genimage_data` succeeds.

### Task 7: Commit, merge, and publish

**Files:**
- Stage only the deployment plan/spec, Docker files, ignore files, script, and README

- [ ] **Step 1: Review repository scope**

Run:

```bash
git status --short
git diff --check
git diff --stat master...HEAD
```

Expected: no local databases, `note.txt`, test images, local tooling folders, or unrelated untracked documentation are included.

- [ ] **Step 2: Commit deployment implementation**

Stage only intended deployment files and commit with a concise Chinese message.

- [ ] **Step 3: Merge into master**

Switch to `master`, merge `codex/docker-deployment`, and rerun the full backend tests, frontend tests/build, and `docker compose config --quiet` on the merged result.

- [ ] **Step 4: Configure and push the repository**

Set `origin` to:

```text
git@github.com:zhangjietest666/GenImage.git
```

Push `master` with upstream tracking. Verify that GitHub shows `master` and that ignored local-only files are absent.
