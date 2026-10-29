# Model Gateway

This repository is moving toward the [model gateway architecture](docs/model-gateway-architecture.md). The gateway API lives in `gateway/`; `browser/` is a gateway client with browser-local chat history. The former Streamlit app, Python CLI chat, and browser model worker have been removed.

The gateway is still an implementation in progress. It has API, adapter, quota, key, billing, and storage code, but the architecture document's production requirements such as a connected host agent, durable atomic accounting, and full account flow are not complete. Do not treat this as a production billing or security boundary yet.

## Run the gateway

Install Python 3.12+ dependencies and start the API:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[gateway]'
GATEWAY_DEV_API_KEY=dev-key-change-me .venv/bin/python -m gateway.server
```

The API listens on `http://127.0.0.1:8080` by default. `docker compose up --build` starts the gateway and PostgreSQL; the compose credentials are development placeholders. Register an approved deployment in the gateway router before sending chat requests. Without one, chat requests return `model_unavailable`.

## Browser client

```bash
cd browser
npm install
npm run dev
```

Set the gateway URL, API key, and model in Settings. The browser stores the API key in tab session storage, and chat history in local storage. Prompts and replies pass through the gateway to the model host. The gateway currently has no general cross-origin browser policy, so use a same-origin proxy or configure an allowed origin before serving the browser and gateway on separate origins.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests
npm test
```

The database definition in `db/schema_postgres.sql` is the PostgreSQL schema for a fresh database. Existing deployments need a data migration before applying incompatible schema changes.
