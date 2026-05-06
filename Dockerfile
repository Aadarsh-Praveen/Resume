FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    poppler-utils \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY job-agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080
CMD cd job-agent && uvicorn dashboard.main:app --host 0.0.0.0 --port ${PORT:-8080}
