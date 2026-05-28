FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

ENV MCP_TRANSPORT=http
ENV HOST=0.0.0.0
ENV UPWORK_TOKEN_FILE=/data/upwork_tokens.json

EXPOSE 8000

CMD ["python", "src/main.py"]
