FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY shell/ ./shell/
COPY main.py .

ENTRYPOINT ["python", "-m", "shell"]
CMD ["enrich"]
