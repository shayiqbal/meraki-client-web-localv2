FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

# Copy application code
COPY config/ config/
COPY meraki_client/ meraki_client/
COPY rules/ rules/
COPY services/ services/
COPY reporting/ reporting/
COPY auth/ auth/
COPY webapp/ webapp/

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
USER appuser

CMD ["python", "-m", "uvicorn", "webapp.app:app", "--host", "0.0.0.0", "--port", "8000"]
