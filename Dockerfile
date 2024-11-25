FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src /app/src

ENV PYTHONPATH=/app

CMD ["kopf", "run", "--standalone", "/app/src/main.py"]