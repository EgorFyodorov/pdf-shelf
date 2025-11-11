FROM python:3.12-slim

WORKDIR /app

COPY system-deps.txt .
RUN apt-get update && \
    xargs -a system-deps.txt apt-get install -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/* system-deps.txt

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY . .

CMD ["python", "bot.py"]
