FROM python:3.11

# Tizim kutubxonalarini o'rnatish (QR skaner va rasm uchun)
RUN apt-get update && apt-get install -y \
    libzbar0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

# Kutubxonalarni o'rnatish
RUN pip install --no-cache-dir -r requirements.txt

# Server porti
EXPOSE 7860

# Botni ishga tushirish
CMD ["python", "main.py"]