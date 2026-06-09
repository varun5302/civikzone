FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies (light રાખ્યું)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Requirements copy
COPY requirements.txt .

RUN pip install --upgrade pip && pip install -r requirements.txt

# Project copy
COPY . .

# Create required folders
RUN mkdir -p /app/staticfiles /app/media

EXPOSE 8000

# Development CMD (same as yours but cleaner)
CMD ["sh", "-c", "python manage.py migrate && python manage.py collectstatic --noinput && python manage.py runserver 0.0.0.0:8000"]