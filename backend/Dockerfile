# Use an official lightweight Python 3.11 image built on Debian Bookworm
FROM python:3.11-slim-bookworm 

# Set the working directory inside the container to /app
WORKDIR /app

# Install essential system tools required for compiling packages and downloading files
RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*

# Copy our Python requirements list into the container
COPY backend/requirements.txt .

# Install all required Python packages (including FastAPI, Pydantic, and Prisma)
RUN pip install --no-cache-dir -r requirements.txt

# --- FIX FOR PRISMA-CLIENT-PYTHON ---
# Manually create the missing executable script so Prisma CLI can find it in the system PATH
RUN echo '#!/usr/local/bin/python' > /usr/local/bin/prisma-client-python && \
    echo 'from prisma.cli import main' >> /usr/local/bin/prisma-client-python && \
    echo "if __name__ == '__main__': main()" >> /usr/local/bin/prisma-client-python && \
    chmod +x /usr/local/bin/prisma-client-python

# Copy the database schema folder from the root workspace into the container
COPY prisma/ ./prisma

# Copy the remaining backend application source code into /app
COPY backend/ .

# Run Prisma generate to build the type-safe Python client database bindings
RUN prisma generate

# Expose port 8000 so our FastAPI backend can receive web traffic
EXPOSE 8000