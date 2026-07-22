FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Папка data будет создана при монтировании volume, но если её нет, создадим (не помешает)
RUN mkdir -p /app/data && chmod 777 /app/data

CMD ["python", "-m", "app.bot"]