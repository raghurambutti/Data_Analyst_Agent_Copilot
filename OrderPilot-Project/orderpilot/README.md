# OrderPilot

**A product analyst agent for order data that drafts new orders with human approval.**

Ask questions in plain English ("Which 3 products earned the most?"). OrderPilot writes a guarded,
read-only SQL query, runs it, and answers, showing the SQL it used. Ask it to create an order and it
prepares a priced draft, then **pauses until a human clicks Approve** before saving anything.

Stack: **Python**, **LangGraph**, a **Databricks-hosted LLM**, **Unity Catalog** tables, and a **Streamlit** web app.

## How it works

```
You ──► agent (LLM) ──► get_schema / run_sql ──► safety guard ──► tables (read only)
              │
              └──► create_order_draft ──► validate + price ──► PAUSE (interrupt)
                                                                  │
                                                       Approve ──► INSERT into order_drafts (pending_review)
                                                       Reject  ──► nothing saved
```

| Piece | File |
|---|---|
| Settings from environment variables | `orderpilot/config.py` |
| SQLite / Databricks SQL backends | `orderpilot/db.py` |
| Fake data + table creation | `orderpilot/seed.py` |
| Read-only SQL guard | `orderpilot/safety.py` |
| Draft validation, pricing, the only write | `orderpilot/orders.py` |
| Tools the model can call | `orderpilot/tools.py` |
| System prompt | `orderpilot/prompts/system.md` |
| LangGraph agent with `interrupt()` approval | `orderpilot/graph.py` |
| Model factory (Databricks Model Serving) | `orderpilot/llm.py` |
| Terminal chat | `orderpilot/chat.py` |
| Streamlit web app | `app.py` |
| Databricks Apps config | `app.yaml` |
| Tests (no cloud account needed) | `tests/` |

## 1. Run it locally (SQLite data)

Use Python 3.11 or 3.12.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt      # if this fails on a new Python: add --only-binary=:all:
cp .env.example .env                 # fill in DATABRICKS_HOST, DATABRICKS_TOKEN, LLM_ENDPOINT

python -m orderpilot.seed            # creates orderpilot_local.db with fake data
pytest -v                            # 31 tests, no network needed
streamlit run app.py                 # opens http://localhost:8501
```

The data is local in this mode, but the answers still come from your Databricks model endpoint,
so `DATABRICKS_HOST`, `DATABRICKS_TOKEN` and `LLM_ENDPOINT` must be set.

## 2. Use Databricks for the database

1. In Databricks, open **SQL Warehouses** and start a warehouse. Copy its **HTTP path** from
   *Connection details* (or just its ID).
2. Create a personal access token: profile picture → **Settings → Developer → Access tokens**.
3. In `.env` set:
   ```
   ORDERPILOT_MODE=databricks
   DATABRICKS_HOST=https://<your-workspace>.cloud.databricks.com
   DATABRICKS_TOKEN=<your token>
   DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/<id>
   ```
4. Create the tables in Unity Catalog: `python -m orderpilot.seed`
5. Check them in **Catalog → workspace → orderpilot**.
6. Run `streamlit run app.py`. The sidebar now shows `Data: databricks`.

To use your own tables instead of the fake ones, point `ORDERPILOT_CATALOG` / `ORDERPILOT_SCHEMA` at them
and update `READ_TABLES` in `config.py` plus the column names in `orders.py`.

## 3. Deploy as a Databricks App (optional)

1. **Compute → Apps → Create app → Custom**, and point it at this folder (sync it to your workspace).
2. In the app's settings, add resources with these keys: `sql-warehouse` (Can use) and
   `serving-endpoint` (Can query). `app.yaml` reads them, so no token is stored anywhere.
3. Grant the app's service principal `SELECT` on the four order tables and `MODIFY` on `order_drafts`.
4. Deploy. Databricks installs `requirements.txt` and runs `streamlit run app.py`.

## Safety design

1. The model never touches the database directly; it can only call three tools.
2. Reads are guarded: one `SELECT`, allow-listed tables, always a `LIMIT`.
3. Prices come from the database, never from the model.
4. Writes need a human: the graph pauses with `interrupt()`.
5. Writes go to a staging table (`order_drafts`), never straight into `orders`.
6. In production, add Unity Catalog grants as a second lock.

All data in this repo is fake (`orderpilot/seed.py`). No keys, tokens or workspace details are included.
