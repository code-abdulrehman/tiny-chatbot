FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn[standard]>=0.29" "asyncpg>=0.30" "httpx>=0.27"

COPY gateway ./gateway
COPY db ./db
COPY pyproject.toml README.md ./

ENV GATEWAY_HOST=0.0.0.0
ENV GATEWAY_PORT=8080
ENV GATEWAY_DATABASE_URL=postgresql+asyncpg://gateway:gateway@db:5432/gateway
ENV GATEWAY_STORE_BACKEND=postgres
ENV GATEWAY_DEV_API_KEY=dev-key-change-me
ENV GATEWAY_STRIPE_WEBHOOK_SECRET=whsec_change-me
ENV GATEWAY_FREE_CREDITS=10000

EXPOSE 8080

CMD ["python", "-m", "gateway.server"]
