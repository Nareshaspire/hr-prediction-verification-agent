FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set Prisma cache directory to a writable path
ENV PRISMA_CACHE_DIR=/tmp/prisma

# Copy requirements from backend directory
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code and schema
COPY backend/ .
COPY prisma/ ./prisma

# Generate Prisma client during build time
RUN python -m prisma generate

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]