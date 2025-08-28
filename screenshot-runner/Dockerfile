FROM python:3.11-slim

# Install Chromium + deps
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-common \
    chromium-driver \
    fonts-liberation \
    wget \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Environment so Selenium finds Chromium
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMIUM_BIN=/usr/bin/chromium
ENV PATH="/usr/lib/chromium:${PATH}"

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY screenshot_urls.py /app/screenshot_urls.py
COPY app.py /app/app.py
COPY helpers.py /app/helpers.py
COPY controllers /app/controllers

# Expose the FastAPI endpoint
EXPOSE 8000

# Launch the HTTP trigger
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

