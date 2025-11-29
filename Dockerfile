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

# 1. اول همه فایل‌ها را کپی می‌کنیم
COPY . .

# 2. حالا entrypoint را اصلاح می‌کنیم (تا مطمئن شویم نسخه نهایی اصلاح شده است)
# دستور sed فرمت ویندوز (\r\n) را به لینوکس (\n) تبدیل می‌کند
# دستور chmod قابلیت اجرایی می‌دهد
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
CMD ["python", "bot.py"]