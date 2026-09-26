# 1. Upgrade to a modern, supported OS base layer (Debian Bookworm)
FROM python:3.10-slim-bookworm

# Set the working directory inside the container
WORKDIR /app/backend

# 2. Update system packages, patch vulnerabilities, and clean up apt cache
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# 3. Create a dedicated non-root application execution user
RUN groupadd -r fastapiuser && useradd -r -g fastapiuser fastapiuser

# Copy requirements manifest first to optimize Docker layer caching
COPY backend/requirements.txt .

# Install Python dependencies and Prisma securely without cache
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir prisma

# Copy the backend source code and root Prisma schema
COPY backend/ ./
COPY prisma/ ./prisma/

# Generate the Prisma client using Python module syntax
RUN python -m prisma generate --schema=prisma/schema.prisma

# 4. Assign file execution ownership to our unprivileged user
RUN chown -R fastapiuser:fastapiuser /app

# 5. Drop root execution privileges
USER fastapiuser

# Expose the FastAPI port
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
