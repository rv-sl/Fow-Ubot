# Use official Python slim image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Install build dependencies (for tgcrypto)
RUN apt-get update && apt-get install -y gcc libffi-dev python3-dev

# Create app directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files
COPY . .

# Expose port 8000 for Flask
EXPOSE 8000

# Run the Flask app
CMD ["python", "app.py"]
