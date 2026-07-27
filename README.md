# Ledger

A personal expense tracker: record daily spending, set monthly budget goals, and
see whether you're on track to hit them.

Python throughout — FastAPI server-rendered with Jinja2, SQLAlchemy for storage,
Chart.js for the charts. No Node build step, which keeps deployment to a single
push.

## What it does

**Track spending.** Amount, category, date, optional note. Any entry can be
back-dated, so catching up on a week at once works fine.

**Set goals.** One overall monthly limit plus a limit per category. Limits repeat
every month; clearing a field stops tracking that category.

**Know if you're on track.** Every category shows a pace bar: the fill is what
you've spent, the notch is where an even burn rate would put you today, and the
hatching shows where the month lands if nothing changes. Four states —
`on_track`, `at_risk`, `over`, `untracked`.

**Get warned early.** A rules engine reads the month and surfaces what matters:
categories running hot, projected overruns, how much you can safely spend per
day for the rest of the month, and spending flowing into categories with no
budget attached.

**See the shape of it.** Category mix (doughnut), spending through the month
against an even-pace line (line), and a six-month trend (bar).

**Reorganise freely.** Add, rename, recolor, reorder, and archive categories.
A category with no expenses can be deleted outright; one with history is
archived so past months keep their totals.

## Layout

```
app/
  config.py          settings; the only module that reads the environment
  db.py              engine, session lifecycle, declarative base
  models.py          Category, Expense, Budget
  seed.py            starter categories for an empty database
  templating.py      Jinja2 environment and formatting filters
  main.py            application entry point
  routers/
    pages.py         HTML routes
    expenses.py      add / delete expenses
    categories.py    add / edit / reorder / archive / delete categories
    budgets.py       set and clear monthly limits
    api.py           JSON for the charts
  services/
    periods.py       month arithmetic and pace
    analytics.py     rollups, projections, status classification
    insights.py      the warning and recommendation rules
  templates/         base, dashboard, expenses, budgets, categories, error
  static/            css/app.css, js/charts.js
tests/
  test_analytics.py  budget maths and insight rules
```

Business logic lives in `services/` and never touches HTTP or templates, which
is why it can be tested directly. To add a new warning, write one function in
`insights.py` and append it to `RULES`.

## Run it locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env               # optional; defaults are fine
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. A SQLite file appears at `data/ledger.db` on first
run, along with six starter categories.

```bash
pytest -q                          # run the tests
```

## Deploy to Azure

Free-tier friendly: the F1 App Service plan costs nothing, and SQLite on the
App Service persistent disk means no database bill either. Your Azure for
Students credit stays untouched.

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/ledger.git
git push -u origin main
```

### 2. Create the Web App

In the Azure Portal: **Create a resource → Web App**

| Setting            | Value                     |
| ------------------ | ------------------------- |
| Publish            | Code                      |
| Runtime stack      | Python 3.12               |
| Operating System   | Linux                     |
| Region             | whichever is nearest      |
| Pricing plan       | **F1 Free**               |

Or from the CLI:

```bash
az group create --name ledger-rg --location westus2

az appservice plan create \
  --name ledger-plan --resource-group ledger-rg \
  --sku F1 --is-linux

az webapp create \
  --name ledger-yourname --resource-group ledger-rg \
  --plan ledger-plan --runtime "PYTHON:3.12"
```

### 3. Configure it

**Configuration → General settings → Startup Command:**

```
startup.sh
```

**Configuration → Application settings**, add:

| Name                              | Value  |
| --------------------------------- | ------ |
| `SCM_DO_BUILD_DURING_DEPLOYMENT`  | `1`    |
| `WEBSITES_ENABLE_APP_SERVICE_STORAGE` | `true` |

The first tells Azure to install `requirements.txt` during deployment. The
second keeps `/home` persistent, which is where the SQLite database lives.

### 4. Wire up deployment

Download the publish profile (**Overview → Get publish profile**), then in your
GitHub repo go to **Settings → Secrets and variables → Actions** and add a
secret named `AZURE_WEBAPP_PUBLISH_PROFILE` with the file's contents.

Edit `AZURE_WEBAPP_NAME` in `.github/workflows/azure-deploy.yml` to match your
app name. Every push to `main` now runs the tests and deploys if they pass.

Your app is at `https://ledger-yourname.azurewebsites.net`.

### Keeping it private

There's no login screen — the URL is the only thing standing between your data
and the internet. Two ways to close that gap when you want to:

- **App Service Authentication** (easiest): **Authentication → Add identity
  provider → Microsoft**, restrict to your own account. Azure handles the login
  before a request ever reaches the app. No code changes.
- **Access restrictions**: **Networking → Access restrictions**, allow only
  your home or campus IP range.

### Moving to PostgreSQL

SQLite is genuinely fine for one person. If you outgrow it, create an Azure
Database for PostgreSQL Flexible Server (free for the first 12 months on a new
account), add `psycopg[binary]` to `requirements.txt`, and set one app setting:

```
DATABASE_URL=postgresql+psycopg://user:pass@host.postgres.database.azure.com:5432/ledger?sslmode=require
```

Nothing else changes — SQLAlchemy handles the rest. Tables are created on boot.

### Watching the cost

The F1 plan gives you 60 minutes of CPU per day, which is plenty for personal
use but will throttle under sustained load. If you upgrade to B1 (~$13/month),
set a budget alert under **Cost Management → Budgets** so the student credit
doesn't drain quietly.

## Notes

- Database tables are created automatically on startup. For schema changes
  beyond adding tables, add Alembic — the models are already structured for it.
- Times are handled as plain dates, so there's no timezone drift on entries.
- Amounts use `Decimal` end to end. No floating-point money.
