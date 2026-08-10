FROM python:3.10-slim
WORKDIR /app
COPY . /app
RUN pip install -r requirements.txt && pybabel compile -d translations
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 CMD python scripts/healthcheck.py
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:80", "--timeout", "60", "main:app"]