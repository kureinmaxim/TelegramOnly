FROM python:3.12-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir streamlit docker requests pandas watchdog

# Copy application code
COPY app.py .

# Healthcheck
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Run Streamlit
ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
