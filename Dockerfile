FROM python:3.12-slim

WORKDIR /app

# Cai dat dependencies he thong
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Cai dat thu vien python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ma nguon
COPY . .

# Tao thu muc luu tru database
RUN mkdir -p data

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
