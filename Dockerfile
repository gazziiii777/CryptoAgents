FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY core/ ./core/
COPY db/ ./db/
COPY cli/ ./cli/
COPY migrations/ ./migrations/
COPY alembic.ini .
COPY main.py .

ENTRYPOINT ["python", "-m", "cli"]
CMD ["--help"]
