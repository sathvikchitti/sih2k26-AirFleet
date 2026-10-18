FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ML_PROVIDER=fd001 \
    DEMO_SCENARIO=fd001_operations \
    DEMO_RESET_ENABLED=true \
    DEMO_PERMISSION_MODE=hardened \
    FD001_MODEL_PATH=/app/models/cmapss_fd001_rf_v1.joblib \
    FD001_DATA_DIR=/CMAPSSData

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/models/cmapss_fd001_rf_v1.joblib ./models/cmapss_fd001_rf_v1.joblib
COPY CMAPSSData /CMAPSSData

RUN python -c "from pathlib import Path; assert Path('/app/models/cmapss_fd001_rf_v1.joblib').is_file(); assert Path('/CMAPSSData/test_FD001.txt').is_file()"

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
