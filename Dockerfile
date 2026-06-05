FROM python:3.12-slim

WORKDIR /app

# Runtime deps for lxml / feed parsing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

# Default: pure generation. Deployment should call run-scheduled explicitly.
CMD ["python", "-m", "finance_news_tracker", "run-once"]
