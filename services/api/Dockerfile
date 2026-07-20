FROM python:3.14.6-slim-trixie AS runtime

ARG PIP_VERSION=26.1.2
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY services/api/pyproject.toml ./pyproject.toml
COPY services/api/requirements-prod.lock ./requirements-prod.lock
COPY services/api/app ./app
RUN python -m pip install --upgrade "pip==${PIP_VERSION}" \
    && python -m pip install --requirement requirements-prod.lock \
    && python -m pip install --no-deps .

COPY services/api/alembic.ini ./alembic.ini
COPY services/api/migrations ./migrations
COPY packages/tenant-content /seed-data
COPY packages/evals /eval-data

USER app
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
