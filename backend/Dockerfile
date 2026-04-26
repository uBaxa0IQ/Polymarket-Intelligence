FROM python:3.12-slim

WORKDIR /app

# Install system deps (for psycopg2, httpx)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install -e ".[clob]"

COPY . .

EXPOSE 8000

ENTRYPOINT ["sh", "entrypoint.sh"]
