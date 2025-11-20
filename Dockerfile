FROM python:3.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# نصب پکیج‌های سیستمی
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    git \
    && rm -rf /var/lib/apt/lists/*

# نصب نیازمندی‌های پایتون
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی اسکریپت شروع و تنظیم دسترسی‌ها
COPY entrypoint.sh .
# تبدیل فرمت ویندوز به لینوکس (برای جلوگیری از خطای احتمالی) و دادن دسترسی اجرا
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

COPY . .

ENTRYPOINT ["./entrypoint.sh"]
CMD ["python", "bot.py"]