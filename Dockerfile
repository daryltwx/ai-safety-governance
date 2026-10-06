# MediCare Assist -- app image only. Does NOT include Ollama; see
# docker-compose.yml, which runs this alongside a separate `ollama`
# service and networks them together via OLLAMA_URL=http://ollama:11434
# (Docker's internal service-name DNS) -- not the localhost default this
# app uses for non-Docker dev (see config.py / .env.example).
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5050

# Same dev server this app has always run with (Flask's app.run(), not a
# production WSGI server) -- it's a security-assessment prototype, not a
# production service. Staying with it in Docker too: UPLOADED_DOCUMENT
# and SESSION_NRIC are in-memory globals that assume a single process,
# which a multi-worker WSGI server would silently break.
CMD ["python", "app.py"]
