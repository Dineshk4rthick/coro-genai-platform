FROM python:3.12.7-slim-bookworm AS builder

WORKDIR /build
COPY app/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12.7-slim-bookworm

RUN useradd --create-home --uid 10001 appuser

WORKDIR /home/appuser
COPY --from=builder /install /usr/local
COPY app/ ./app/

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]