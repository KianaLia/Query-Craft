FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

CMD ["gunicorn", "nl2sql_project.wsgi:application", "--bind", "0.0.0.0:8000"]
