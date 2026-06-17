# Use a pinned slim base image for reproducible builds
FROM python:3.12-slim-bookworm

WORKDIR /app

# Install Python dependencies (cache-friendly: only rebuild when requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 5000

# Use waitress as production WSGI server
# Railway sets PORT env var; default to 8080 if unset
CMD ["sh", "-c", "waitress-serve --port=${PORT:-8080} app:application"]
