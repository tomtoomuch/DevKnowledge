FROM python:3.14-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY app ./app

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]

FROM runtime AS test
COPY requirements-test.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements-test.txt

# The default image contains only runtime dependencies.
FROM runtime AS production
