FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including cron and dos2unix for line ending conversion
RUN apt-get update && \
    apt-get install -y cron dos2unix && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create state directory
RUN mkdir -p state

# Copy crontab and entrypoint, then convert line endings from Windows (CRLF) to Unix (LF)
COPY crontab /app/crontab
COPY entrypoint.sh /app/entrypoint.sh
RUN dos2unix /app/crontab /app/entrypoint.sh && \
    chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
