"""Pinned, image-bundled multilingual CPU embedding model (Apache-2.0)."""
import os

MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
REPOSITORY = 'Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q'
REVISION = 'faf4aa4225822f3bc6376869cb1164e8e3feedd0'
MODEL_PATH = os.getenv('LOCAL_EMBEDDING_MODEL_PATH', '/opt/anamnesis-models/multilingual-minilm')
DIMENSIONS = 384


def load_model():
    from fastembed import TextEmbedding
    return TextEmbedding(MODEL, specific_model_path=MODEL_PATH,
        local_files_only=True, threads=max(1, min(int(os.getenv('EMBEDDING_THREADS', '2')), 8)),
        providers=['CPUExecutionProvider'])


def download_model():
    # Used during image build and when startup repairs missing model assets.
    from huggingface_hub import snapshot_download
    snapshot_download(REPOSITORY, revision=REVISION, local_dir=MODEL_PATH,
        allow_patterns=['*.json', '*.onnx', 'README.md'], max_workers=2)
    embedding = next(load_model().embed(['本地向量模型构建验证']))
    assert len(embedding) == DIMENSIONS
    print('Bundled multilingual embedding model verified:', MODEL, DIMENSIONS)


if __name__ == '__main__':
    download_model()
