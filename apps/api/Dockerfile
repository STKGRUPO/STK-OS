FROM python:3.12-slim

WORKDIR /app

# Install OS-level build dependencies required by some Python packages
# (e.g. cryptography, lxml, psycopg) before they are compiled/installed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libxml2-dev \
        libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first to leverage Docker layer caching.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

# Copy the rest of the application source code.
COPY . .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "stk_os.main:app", "--host", "0.0.0.0", "--port", "8000"]
