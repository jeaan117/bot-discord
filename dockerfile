FROM python:3.11-slim

# Instalar FFmpeg y librerías de audio del sistema
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg libopus-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto
COPY . .

# Comando de inicio
CMD ["python", "bot.py"]