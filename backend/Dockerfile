FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc git curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./root-requirements.txt
COPY backend/requirements.txt ./backend-requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r root-requirements.txt -r backend-requirements.txt

COPY . .

RUN chmod +x backend/entrypoint.sh

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["./backend/entrypoint.sh"]
