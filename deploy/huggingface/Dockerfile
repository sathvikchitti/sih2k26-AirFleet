# Hugging Face Docker Space for the Air Fleet FastAPI backend.
# Spaces run the container as user 1000 and route public traffic to port 7860.
FROM python:3.12-slim

RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ML_PROVIDER=fd001 \
    DEMO_SCENARIO=fd001_operations \
    DEMO_ACCESS_MODE=restricted \
    DEMO_RESET_ENABLED=false \
    DEMO_PERMISSION_MODE=hardened \
    FD001_MODEL_PATH=/home/user/app/models/cmapss_fd001_rf_v1.joblib \
    FD001_DATA_DIR=/home/user/app/CMAPSSData

WORKDIR /home/user/app

COPY --chown=user requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user app ./app
COPY --chown=user models ./models
COPY --chown=user CMAPSSData ./CMAPSSData

RUN python -c "from pathlib import Path; assert Path('models/cmapss_fd001_rf_v1.joblib').is_file(); assert Path('CMAPSSData/test_FD001.txt').is_file()"

EXPOSE 7860
# One worker: demo state and locking are in memory.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
