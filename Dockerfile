# ---------- Builder Stage ----------
    FROM python:3.10-slim as builder

    WORKDIR /app
    
    # Install build dependencies (needed for psycopg2, etc.)
    RUN apt-get update && \
        apt-get install -y gcc build-essential libpq-dev && \
        rm -rf /var/lib/apt/lists/*
    
    # Copy requirements to leverage Docker cache
    COPY requirements.txt .
    
    # Upgrade pip and install dependencies into a target folder
    RUN pip install --upgrade pip && \
        pip install --prefix=/install -r requirements.txt
    
    # ---------- Final Stage ----------
    FROM python:3.10-slim
    
    WORKDIR /app
    
    # Install runtime dependencies (libpq-dev is needed for PostgreSQL driver)
    RUN apt-get update && \
        apt-get install -y libpq-dev && \
        rm -rf /var/lib/apt/lists/*
    
    # Copy the installed python packages from the builder stage
    COPY --from=builder /install /usr/local
    
    # Copy the entire application source code
    COPY . .
    
    # Expose the port your application will run on
    EXPOSE 8000
    
    # Set environment variables for a cleaner Python runtime
    ENV PYTHONDONTWRITEBYTECODE=1
    ENV PYTHONUNBUFFERED=1
    
    # Run the application with uvicorn
    CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
    