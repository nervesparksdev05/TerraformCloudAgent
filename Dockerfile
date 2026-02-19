# Multi-stage build to get Terraform binary
FROM hashicorp/terraform:1.7 AS terraform

# Base Python image
FROM python:3.11-slim-bookworm

# Copy Terraform binary from the first stage
COPY --from=terraform /bin/terraform /usr/local/bin/terraform

# Set working directory
WORKDIR /app

# Install system dependencies
# (Skipping git/curl/unzip to avoid network 403 errors and keep image small)
# RUN apt-get update && apt-get install -y git curl unzip && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
# Copy the bot debug file if it's needed at runtime (referenced in some logic)
COPY bot_debug.txt .

# Create directories for logs and runs to map volumes later
RUN mkdir -p logs runs

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
