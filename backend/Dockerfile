FROM python:3.11-slim
WORKDIR /srv/backend
ENV PYTHONPATH=/srv:/srv/backend PYTHONUNBUFFERED=1
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app app
COPY backend/alembic.ini .
COPY backend/migrations migrations
COPY cv/__init__.py /srv/cv/
COPY cv/gesture_detector /srv/cv/gesture_detector
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
