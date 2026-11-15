FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# Give permissions so any user can write seen_messages.json
RUN chmod -R 777 /app

EXPOSE 7860

CMD ["python", "bot.py"]
