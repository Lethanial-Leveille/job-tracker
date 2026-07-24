# Deployment runbook (v3, Option A)

Deploying the Job & Scholarship Tracker to a single DigitalOcean droplet, with the
frontend and backend on the **same origin** behind Caddy. Prepared ahead of time;
run top to bottom when the droplet exists. Config artifacts live in `deploy/`.

Architecture: **Caddy** (public HTTPS edge) serves the built React `dist/` and
proxies `/api/*` to **uvicorn** on `127.0.0.1:8000`; uvicorn is a **systemd**
service; data is in **Postgres** on the same box. Same origin means no CORS.

---

## 0. Prerequisites (before touching the server)

- DigitalOcean account with the GitHub Student credit redeemed (verify its expiry).
- A droplet: **Ubuntu 24.04 LTS**, the basic/cheapest shared-CPU size is plenty
  for a single user. Add your SSH public key during creation.
- DNS: an **A record** for `tracker.lethanial.com` → the droplet's IP. Do this
  early — Caddy can only get a TLS certificate once the name resolves to the box.

## 1. First login and a non-root user

```bash
ssh root@DROPLET_IP
adduser deploy && usermod -aG sudo deploy          # a non-root owner for the app
rsync --archive ~/.ssh /home/deploy/ && chown -R deploy:deploy /home/deploy/.ssh
# from here on, SSH in as deploy@DROPLET_IP
```

Firewall — allow SSH and web only:

```bash
sudo ufw allow OpenSSH && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw enable
```

## 2. System packages

```bash
sudo apt update && sudo apt upgrade -y
# Python + git, Postgres, Caddy prereqs, WeasyPrint's Pango/Cairo libs, Carlito
# font (matches the resume template), and Node for building the frontend.
sudo apt install -y python3 python3-venv git postgresql \
  libpango-1.0-0 libpangocairo-1.0-0 fonts-crosextra-carlito nodejs npm
```

WeasyPrint note: on Linux these libs land in standard loader paths, so the macOS
`~/lib` symlink hack from decisions.md is **not** needed here.

Install Caddy (official repo) and `uv`:

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
curl -LsSf https://astral.sh/uv/install.sh | sh      # installs uv for the deploy user
```

## 3. Get the code

```bash
sudo mkdir -p /opt/job-tracker && sudo chown deploy:deploy /opt/job-tracker
git clone https://github.com/Lethanial-Leveille/job-tracker.git /opt/job-tracker
```

## 4. Postgres: database + a real role WITH a password

Locally we used trust auth; in prod the app connects with a password.

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE jobtracker LOGIN PASSWORD 'CHANGE_ME_STRONG_PASSWORD';
CREATE DATABASE job_tracker OWNER jobtracker;
SQL
```

## 5. Backend: deps, secrets, migrations, seed

```bash
cd /opt/job-tracker/backend
uv sync --no-dev                         # prod install from uv.lock (no pytest)
```

Create `backend/.env` (chmod 600, never committed). Generate a fresh JWT secret:

```bash
umask 077
cat > .env <<EOF
ANTHROPIC_API_KEY=sk-ant-...              # same key as local
JWT_SECRET=$(openssl rand -hex 32)        # a NEW strong secret for prod
DATABASE_URL=postgresql+psycopg://jobtracker:CHANGE_ME_STRONG_PASSWORD@localhost:5432/job_tracker
EOF
```

Run migrations and seed your user:

```bash
uv run alembic upgrade head
uv run python scripts/seed_user.py        # creates your login (interactive)
```

## 6. Frontend: build and place the static files

```bash
cd /opt/job-tracker/frontend
npm ci && npm run build                   # produces dist/
sudo mkdir -p /var/www/job-tracker
sudo cp -r dist/* /var/www/job-tracker/
```

(Leaner alternative: build on your Mac with `npm run build` and `scp` the `dist/`
contents up, so the droplet needs no Node toolchain.)

No frontend code change is needed: it calls relative `/api`, and Caddy strips the
`/api` prefix on the way to uvicorn.

## 7. Run the backend under systemd

```bash
sudo cp /opt/job-tracker/deploy/job-tracker.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now job-tracker
systemctl status job-tracker
curl -s localhost:8000/health             # expect {"status":"ok","database":"connected"}
```

## 8. Caddy: serve the site with HTTPS

```bash
sudo cp /opt/job-tracker/deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

With DNS pointing at the box (step 0), Caddy obtains a Let's Encrypt certificate
automatically. This is also deployment step 6 (HTTPS) — nothing more to do.

## 9. Verify end to end

- Visit `https://tracker.lethanial.com` → the login screen loads over HTTPS.
- Log in with the seeded user → the app loads, applications list works.
- Add an opportunity and parse a JD → confirms the Anthropic key and DB writes.

## Redeploying later

```bash
cd /opt/job-tracker && git pull
cd backend && uv sync --no-dev && uv run alembic upgrade head
cd ../frontend && npm ci && npm run build && sudo cp -r dist/* /var/www/job-tracker/
sudo systemctl restart job-tracker
```

## Notes / gotchas

- Secrets stay in `backend/.env` on the server (chmod 600), never in git.
- The backend binds to `127.0.0.1` only; Caddy is the sole public entry point.
- Postgres enum gotcha (from decisions.md): adding a new status value later needs
  an explicit `ALTER TYPE ... ADD VALUE` migration — Alembic won't autogenerate it.
- n8n / service token is a later (v4) concern; not part of this deploy.
