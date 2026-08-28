FROM mcr.microsoft.com/playwright/python:v1.47.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["python", "server.py"]
