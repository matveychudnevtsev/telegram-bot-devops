# Этап сборки
FROM python:3.9-slim as builder

WORKDIR /app

# Установка зависимостей для сборки
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Копирование и установка зависимостей
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Финальный этап
FROM python:3.9-slim

WORKDIR /app

# Копирование установленных зависимостей из этапа сборки
COPY --from=builder /root/.local /root/.local

# Установка необходимых системных библиотек
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*

# Добавление пути к установленным пакетам Python
ENV PATH=/root/.local/bin:$PATH

# Копирование исходного кода
COPY . .

CMD ["python", "main.py"]