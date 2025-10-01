FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend base package
COPY backend-base /app/backend-base
RUN cd /app/backend-base && pip install -e .

# Copy the AXF package
COPY axf /app/axf
RUN cd /app/axf && pip install -e .

# Copy the flow file
COPY SIMPLIFIED.json /app/flow.json

# Set environment variables
ENV PYTHONPATH="/app/backend-base:$PYTHONPATH"
ENV AXIESTUDIO_API_KEY="your-secret-key"

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the AXF server
CMD ["python", "-m", "axf", "serve", "/app/flow.json", "--host", "0.0.0.0", "--port", "8000"]
