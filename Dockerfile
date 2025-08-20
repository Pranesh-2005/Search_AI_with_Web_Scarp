# Use Playwright python image (Chromium + deps preinstalled)
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Fix SSL/TLS issues
ENV PYTHONHTTPSVERIFY=0
ENV SSL_VERIFY=false
ENV REQUESTS_CA_BUNDLE=""
ENV CURL_CA_BUNDLE=""

# Update certificates and install network tools
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    wget \
    openssl \
    && update-ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage caching
COPY requirements.txt /app/requirements.txt

# Install Python dependencies with SSL fixes
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r requirements.txt

# Install Playwright browser with dependencies
RUN python -m playwright install --with-deps chromium

# Run Crawl4AI setup
RUN crawl4ai-setup

# Run Crawl4AI doctor (diagnostics)
RUN crawl4ai-doctor || true

# Copy rest of application
COPY . /app

# Make start script executable
RUN chmod +x /app/start.sh

# Use non-root user that Playwright image provides
USER pwuser

# Expose port for Render
EXPOSE 5000

# Start backend with gunicorn
CMD ["/app/start.sh"]