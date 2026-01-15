FROM node:20-slim AS frontend-build

WORKDIR /app/frontend
ENV NEXT_OUTPUT=export
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build


FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=frontend-build /app/frontend/out /app/frontend_out

ENV FRONTEND_DIST=/app/frontend_out
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
