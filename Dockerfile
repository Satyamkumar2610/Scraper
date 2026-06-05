FROM python:3.11-slim

LABEL maintainer="gov-data-ingest"

WORKDIR /app

# System deps for psycopg2 / pyarrow
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create dirs that the app expects
RUN mkdir -p raw exports logs migrations

ENTRYPOINT ["python", "main.py"]
CMD ["--help"]
