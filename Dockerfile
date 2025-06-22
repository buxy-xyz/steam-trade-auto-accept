# Start by pulling the python image
FROM python:3.11-alpine

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies for potential SSL/network issues
RUN apk add --no-cache \
    ca-certificates \
    tzdata

# Copy the requirements file into the image
COPY requirements.txt /app/requirements.txt

# Switch working directory
WORKDIR /app

# Install the dependencies and packages in the requirements file
RUN pip install --no-cache-dir -r requirements.txt

# Copy every content from the local file to the image
COPY . /app

# Create a non-root user for security
RUN adduser -D -s /bin/sh appuser
RUN chown -R appuser:appuser /app
USER appuser

# Configure the container to run in an executed manner
ENTRYPOINT [ "python3" ]

CMD ["-u", "main.py"]