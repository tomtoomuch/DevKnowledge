FROM python:3.12-slim-bookworm
WORKDIR /app
COPY poc/rncp-postgres/requirements-test.txt requirements-test.txt
RUN pip install --no-cache-dir -r requirements-test.txt
COPY backend/knowledge-service/app ./app
COPY backend/knowledge-service/app/rncp ./rncp
COPY poc/rncp-postgres/migrations ./migrations
COPY poc/rncp-postgres/tests ./tests
ENV PYTHONDONTWRITEBYTECODE=1
USER 65534:65534
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "/app/tests"]
