FROM python:3.13.14-slim-trixie AS runtime

ARG PIP_VERSION=26.1.2
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    REMAP_SIGTERM=SIGQUIT

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        libgl1 \
        libglib2.0-0t64 \
        libgomp1 \
        libxcb1 \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system worker && adduser --system --ingroup worker worker

COPY services/worker/requirements-prod.lock /tmp/requirements-prod.lock
RUN python -m pip install --upgrade "pip==${PIP_VERSION}" \
    && python -m pip install --requirement /tmp/requirements-prod.lock

COPY services/api/pyproject.toml /src/api/pyproject.toml
COPY services/api/app /src/api/app
RUN python -m pip install --no-deps /src/api

COPY services/worker/pyproject.toml /src/worker/pyproject.toml
COPY services/worker/cf_worker /src/worker/cf_worker
RUN python -m pip install --no-deps /src/worker

# Import and initialize the exact OCR stack during the image build.  Merely
# installing rapidocr is insufficient because its default ONNX engine is an
# explicit dependency and OpenCV also needs Linux shared libraries.
RUN python -c "from rapidocr import RapidOCR; RapidOCR()"

COPY packages/evals /eval-data

USER worker
EXPOSE 8020

CMD ["celery", "-A", "cf_worker.celery_app:celery_app", "worker", "--loglevel=INFO", "--queues=outbox.poll,outbox.process", "--concurrency=1"]
