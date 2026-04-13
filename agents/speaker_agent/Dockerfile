FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules and agent code
COPY shared/ ./shared/
COPY agents/base_agent.py ./agents/
COPY agents/speaker_agent/ ./agents/speaker_agent/

ENV PYTHONPATH=/app

CMD ["python", "-m", "agents.speaker_agent.main"]
