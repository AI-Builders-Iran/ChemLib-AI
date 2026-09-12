FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run the FastAPI backend.
# Override to run Streamlit instead, e.g.:
#   docker run <image> streamlit run app/streamlit_app/app.py --server.address 0.0.0.0
EXPOSE 8000 8501

CMD ["uvicorn", "app.api.api_app:app", "--host", "0.0.0.0", "--port", "8000"]
