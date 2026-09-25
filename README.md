# UK Climate Insights

A Django app that parses the UK Met Office regional climate series and serves them through a REST API,
a small explorer UI and an LLM chat grounded in the database.

Work in progress.

## Local development

Requires Python 3.12 and Docker.

```bash
docker compose up -d db                   # Postgres 16 on localhost:5432
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                      # optional: dev settings have safe defaults
python manage.py migrate
python manage.py runserver
pytest                                    # tests run against the same Postgres
```
