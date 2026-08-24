# Imagem enxuta e sem root para os jobs de ingestao.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Preserva o pacote 'src' dentro da imagem. Os modulos importam uns aos outros
# como 'src.jobs...' / 'src.utils...', entao achatar o conteudo em /app quebra
# o import no container (funcionava so localmente, onde o make roda da raiz).
COPY src/ ./src/

# Usuario nao-root (boa pratica de seguranca).
RUN useradd --create-home appuser
USER appuser

EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "0", "src.main:app"]
