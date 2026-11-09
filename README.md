# Customers Platform (web)

Web version of the desktop Customers Platform (PyQt), for the owner and branch managers.
English + Arabic (right-to-left), Excel reports, date ranges, smart analytics and an AI analyst.

| Part | Technology |
|---|---|
| Website | React + TypeScript + Tailwind (`frontend/`) |
| API | FastAPI, Python 3.13 (`backend/`) |
| Database | PostgreSQL 16 |
| AI | OpenAI API (optional) |
| Deployment | Docker Compose on the VPS, port **1100** |

The original desktop code is kept in `legacy/` for reference.

---

## What's inside

**Pages:** Dashboard · Smart insights · Customers (+ customer profile) · Call lists · Business analysis ·
Areas · Transactions · AI analyst · Data upload · Users & roles · Settings · Audit log · My account.

**On every page:** date range (presets like "last 30 days", "last month", "this year", or custom dates),
branch / sales type / district / season filters, an **Excel** download of what you see (English or Arabic
headers), and Print → PDF.

**Smart analytics**
- KPIs with % change vs the previous period, new customers
- Customer status (active / needs attention / inactive) from rules you set in Settings
- **RFM segments**: Champions, Loyal, Potential, New, Promising, Can't lose, At risk, Hibernating, Lost
- **Churn risk** from each customer's *own* visit rhythm, **expected next visit**, overdue days
- "Due in the next 7 days" list (send a reminder), multi-branch customers
- **Cohort retention** (do new customers come back?), **new vs returning** per month
- **Products bought together** (market basket, lift), busiest **days / hours**
- **Branch growth** vs previous period, Pareto (top 20% customers' share of sales)
- **Smart alerts** in English & Arabic (e.g. "Sales in Maadi dropped 16%")
- **AI analyst** (OpenAI): ask questions in English or Arabic or generate an executive report.
  Only aggregated numbers are sent, never phone numbers or names.

**Big Excel files**
- The browser uploads in 8 MB pieces with automatic retry and resume, up to 1 GB by default
- `.xlsx .xls .xlsb .csv` or a **.zip** of them (zip a big CSV: up to 10× faster to upload)
- Fast Rust-based Excel reader (calamine), streamed in 100k-row batches, bulk-loaded with PostgreSQL `COPY`
- Live progress bar; the swap into the live data is atomic (a failed import changes nothing)
- Column matching is automatic (English & Arabic headers) and you confirm it; the mapping is remembered
- Import modes: *replace same dates & branches* (safe to re-upload), *only newer rows*, *replace everything*
- Duplicate-file warning, and each import can be removed again
- Measured: 316k rows from a 18 MB .xlsx imported in about 10 s

**Security**
- Users with roles; an editable **permissions matrix** (admin / manager / branch_staff / viewer, plus your own roles)
- A user can be limited to certain branches; phone numbers are masked for roles without "See full phone numbers"
- **Audit log** of logins (including failed ones), exports, customer views, imports, user/role/settings changes,
  and AI questions
- Login brute-force protection, bcrypt passwords, customer links use an opaque id (no phone numbers in URLs)

---

## Deploy on the VPS (Hostinger, Ubuntu)

All commands run on the VPS over SSH (`ssh root@187.124.177.138`).

### 1. Install Docker (once)
```bash
curl -fsSL https://get.docker.com | sh
```

### 2. Get the code
```bash
git clone -b claude/compassionate-mccarthy-z04lu3 https://github.com/refaat1942/customers-platform.git /opt/customers-platform
```
The repository is private, so GitHub will ask for a username and a **personal access token** as the password
(GitHub → Settings → Developer settings → Personal access tokens).

### 3. Configure
```bash
cd /opt/customers-platform
```
```bash
cp .env.example .env
```
```bash
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 24)/; s/^SECRET_KEY=.*/SECRET_KEY=$(openssl rand -hex 32)/" .env
```
Optionally put your OpenAI key in `.env` (`OPENAI_API_KEY=sk-...`). You can also add it later in the website
under Settings → AI.

### 4. Start
```bash
docker compose up -d --build
```
The first build takes 1-3 minutes (it only installs Python packages; the website is already built).
If it seems stuck, press Ctrl+C and run `docker compose build --progress=plain` to see each step.
Check that it is running:
```bash
docker compose ps
```

### 5. Open the port
In hPanel → VPS → **Firewall**, allow TCP port **1100**. If `ufw` is enabled on the server:
```bash
ufw allow 1100/tcp
```

### 6. Log in
Open **http://187.124.177.138:1100** and log in with **admin / admin**.
**Change the password right away** (My account). A red banner reminds you until you do.
Then: Settings → upload your logo, set the name and colour, add the OpenAI key → Data upload → upload your Excel.

### Update to a new version
```bash
cd /opt/customers-platform && git pull && docker compose up -d --build
```

### Daily database backup
```bash
(crontab -l 2>/dev/null; echo "30 2 * * * /opt/customers-platform/deploy/backup.sh >> /var/log/cp-backup.log 2>&1") | crontab -
```
Backups go to `/opt/customers-platform/backups/` (last 14 days are kept). Restore with
`deploy/restore.sh backups/<file>.sql.gz`.

### Connect to PostgreSQL directly (pgAdmin / DBeaver)
The database listens only on the VPS itself (127.0.0.1:5433), not on the internet. Use an SSH tunnel:
```bash
ssh -L 5433:127.0.0.1:5433 root@187.124.177.138
```
Then connect to `localhost:5433`, database `customers`, user `customers`, with the password from `.env`.

### Recommended: HTTPS with a domain
Port 1100 uses plain HTTP, so passwords travel unencrypted. If you point a domain (e.g. `crm.yourdomain.com`)
to the VPS, you can put Caddy in front for automatic HTTPS:
```bash
apt install -y caddy
```
```bash
printf 'crm.yourdomain.com {\n  request_body {\n    max_size 20MB\n  }\n  reverse_proxy localhost:1100\n}\n' > /etc/caddy/Caddyfile && systemctl reload caddy
```

### Logs
```bash
docker compose logs -f app
```

---

## Development

Requirements: Python 3.13, Node 22, PostgreSQL 16.

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
```
```bash
cd backend && DATABASE_URL=postgresql://user:pass@localhost/customers ../.venv/bin/uvicorn app.main:app --port 1100 --reload
```
```bash
cd frontend && npm install && npm run dev
```
The dev website runs on http://localhost:5173 and forwards `/api` to port 1100.

The production website is served from the pre-built `frontend/dist` (committed to git, so the VPS needs no
Node.js). After changing anything in `frontend/`, run `npm run build` there and commit `frontend/dist`.

Tests (they use a separate database, e.g. `customers_test`, which is wiped on every run):
```bash
cd backend && DATABASE_URL=postgresql://user:pass@localhost/customers_test ../.venv/bin/python -m pytest -q
```

### Definitions used everywhere
- **Visit / invoice** = distinct invoice number; if the file has none, one visit = same phone + day + branch
- **Total spend** = sum of the amount column
- **Days since last visit** is counted to the **end of the selected date range** (or the latest date in the
  data), not to today, so an older import doesn't make everybody look inactive
- **Status**: Active ≤ 30 days, Needs attention ≤ 60 days, else Inactive (editable in Settings)
- **Churn risk**: high when the customer is more than 2× past their own usual gap between visits
