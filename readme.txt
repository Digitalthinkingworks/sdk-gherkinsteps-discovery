python -m venv .venv

pip install -r requirements.txt

uvicorn embedding_service.main:app --host 0.0.0.0 --port 8001 --reload

uvicorn query_service.main:app --host 0.0.0.0 --port 8002 --reload

uvicorn chatui.main:app --host 0.0.0.0 --port 8000 --reload

Remove-Item -Recurse -Force chroma_db

python -c "
from ingestion.pipeline import run_pipeline
result = run_pipeline(crawler_mode='local', sdk_config={'supply-chain-sdk': '2.3.1'})
print(result)
"

ollama serve
ollama pull mistral