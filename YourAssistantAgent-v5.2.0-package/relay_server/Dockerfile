FROM python:3.12-slim
WORKDIR /app
COPY relay_server/server.py /app/server.py
USER 10001:10001
ENV RELAY_BIND=0.0.0.0 PORT=8080 PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "/app/server.py"]
