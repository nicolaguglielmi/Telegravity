# Use a lightweight Python image
FROM python:3.11-slim

# Set environment variables
# PYTHONUNBUFFERED=1 is crucial for MCP over Stdio to ensure logs/data are sent immediately
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set the working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the server code
COPY server.py .

# Entrypoint runs the MCP server
# Note: Podman/Docker will pass stdin/stdout through if run with -i
# Default command is regular python, but can be overridden with watchmedo
CMD ["python", "server.py"]
