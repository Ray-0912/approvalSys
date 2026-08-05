FROM python:3.10-slim
WORKDIR /app
COPY . /app
RUN pip install -r requirements.txt
RUN pybabel compile -d translations
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:80", "--timeout", "60", "main:app"]