FROM python:3.11-slim

WORKDIR /app

COPY job-agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD cd job-agent && uvicorn dashboard.main:app --host 0.0.0.0 --port $PORT
