# Use a pinned slim base image for reproducible builds
FROM python:3.12-slim-bookworm

WORKDIR /app

# Install system dependencies needed by psycopg2 / waitress
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (cache-friendly: only rebuild when requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 5000

# Use waitress as production WSGI server
CMD waitress-serve --port=$PORT app:application
