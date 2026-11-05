FROM python:3.14-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir

COPY event_downloader.py filefunction.py ./

# The script resolves event_img relative to its working directory.
WORKDIR /
CMD ["python", "/app/event_downloader.py"]
