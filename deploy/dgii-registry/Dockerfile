FROM python:3.12-slim-bookworm

WORKDIR /app

RUN useradd --system --uid 10001 --home /app --shell /usr/sbin/nologin korventis

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY korventis_dgii_registry /app/korventis_dgii_registry
COPY migrations /app/migrations

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV KORVENTIS_DGII_BIND=0.0.0.0
ENV KORVENTIS_DGII_PORT=8080
ENV KORVENTIS_DGII_AUTO_IMPORT=false

USER korventis

EXPOSE 8080

CMD ["python", "-m", "korventis_dgii_registry"]
