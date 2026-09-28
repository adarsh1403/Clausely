# Use official lightweight Python runtime
FROM python:3.12-slim

# Set working directory inside container
WORKDIR /app

# Prevent Python from writing bytecode and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy dependency definition and install packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and entrypoint
COPY app/ ./app/
COPY main.py .
COPY .env.example .env

# Expose standard application port
EXPOSE 8000

# Run the FastAPI server via main.py
CMD ["python", "main.py"]
