FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run the FastAPI backend.
# Override to run the NiceGUI app instead, e.g.:
#   docker run <image> python -m app.nicegui_app.main
EXPOSE 8000 8080

CMD ["uvicorn", "app.api.api_app:app", "--host", "0.0.0.0", "--port", "8000"]
