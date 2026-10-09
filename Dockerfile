# PlayGo em contêiner (publicação própria, sem Vercel nem Supabase). Ver docs/publicar-do-zero.md
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt requirements-servidor.txt ./
RUN pip install -r requirements-servidor.txt

COPY playgo ./playgo
COPY scripts ./scripts

# arquivos enviados (fotos, vídeos, PDFs) ficam num volume
RUN mkdir -p /dados/uploads && useradd --system --uid 10001 playgo && chown -R playgo /dados /app
USER playgo
ENV PLAYGO_PASTA_UPLOADS=/dados/uploads PLAYGO_ARMAZENAMENTO=local PLAYGO_AUTO_MIGRAR=true

EXPOSE 8010
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8010/saude', timeout=4).status == 200 else 1)"

CMD ["python", "-m", "playgo", "web", "--host", "0.0.0.0", "--porta", "8010"]
