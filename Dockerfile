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
CMD waitress-serve --port=$PORT app:application
