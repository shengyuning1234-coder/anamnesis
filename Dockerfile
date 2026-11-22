ARG OPENWEBUI_IMAGE=ghcr.io/open-webui/open-webui:v0.12.3@sha256:a537bbe1e6b428820f52ed4a029d7fff97062e24d5cf32c365fba36fd0542def
FROM ${OPENWEBUI_IMAGE}
USER root
# Full OpenWebUI, including native document/audio/vector integrations. Never
# emulate full mode by changing USE_SLIM on top of a slim dependency set.
RUN python -c "import os; assert os.getenv('USE_SLIM_DOCKER', 'false').lower() != 'true'"
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra poppler-utils \
    libreoffice-writer libreoffice-calc libreoffice-impress fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/anamnesis-browsers
RUN python -m playwright install --with-deps chromium
# Isolate the word app's dependencies from the upstream OpenWebUI runtime.
COPY 英语单词/requirements.txt /opt/anamnesis-requirements.txt
RUN python -m venv /opt/anamnesis-venv && /opt/anamnesis-venv/bin/pip install --no-cache-dir -r /opt/anamnesis-requirements.txt
COPY docker/search-requirements.txt /opt/anamnesis-docker/search-requirements.txt
RUN python -m venv /opt/anamnesis-search-venv && /opt/anamnesis-search-venv/bin/pip install --no-cache-dir -r /opt/anamnesis-docker/search-requirements.txt
COPY docker/embedding-requirements.txt /opt/anamnesis-docker/embedding-requirements.txt
RUN python -m venv /opt/anamnesis-embedding-venv && /opt/anamnesis-embedding-venv/bin/pip install --no-cache-dir -r /opt/anamnesis-docker/embedding-requirements.txt
COPY docker/embedding_model.py /opt/anamnesis-docker/embedding_model.py
ARG BUNDLE_EMBEDDING_MODEL=1
RUN if [ "$BUNDLE_EMBEDDING_MODEL" = "1" ]; then HF_HUB_DISABLE_XET=1 /opt/anamnesis-embedding-venv/bin/python /opt/anamnesis-docker/embedding_model.py; fi
# Preserve upstream's preloaded Whisper/tokenizer/auxiliary models outside the
# mutable data mount. Startup seeds missing files without replacing user caches.
RUN mv /app/backend/data/cache /opt/anamnesis-bundled-cache
COPY 英语单词 /opt/anamnesis
COPY docker /opt/anamnesis-docker
COPY 朗文英汉/ /opt/anamnesis-dictionaries/
ENV APP_DATA_DIR=/data/words LOCAL_DICT_PATH=/opt/anamnesis-dictionaries/oaldpe.mdx \
    DATA_DIR=/data/openwebui FRONTEND_BUILD_DIR=/app/build \
    HOST=0.0.0.0 PORT=5050 PYTHONUNBUFFERED=1 \
    OFFLINE_MODE=false ENABLE_VERSION_UPDATE_CHECK=false \
    SCARF_NO_ANALYTICS=true DO_NOT_TRACK=true ANONYMIZED_TELEMETRY=false \
    ENABLE_OLLAMA_API=false RAG_EMBEDDING_ENGINE=openai \
    VECTOR_DB=chroma CHROMA_DATA_PATH=/data/openwebui/vector_db \
    RAG_EMBEDDING_MODEL_AUTO_UPDATE=false RAG_RERANKING_MODEL_AUTO_UPDATE=true WHISPER_MODEL_AUTO_UPDATE=true \
    HF_HOME=/data/openwebui/cache/embedding/models SENTENCE_TRANSFORMERS_HOME=/data/openwebui/cache/embedding/models \
    WHISPER_MODEL_DIR=/data/openwebui/cache/whisper/models TIKTOKEN_CACHE_DIR=/data/openwebui/cache/tiktoken
RUN mkdir -p /data/words /data/openwebui /dict
WORKDIR /opt/anamnesis
EXPOSE 5050
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=10s --start-period=900s --retries=5 CMD ["python", "/opt/anamnesis-docker/healthcheck.py"]
ENTRYPOINT ["python", "/opt/anamnesis-docker/entrypoint.py"]
CMD []
