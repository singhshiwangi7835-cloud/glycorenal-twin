#!/usr/bin/env bash
# Start GlycoRenal Twin inside the container.
#   MODE=api  -> FastAPI only (port 8000)
#   MODE=ui   -> Streamlit only (port ${PORT:-8501}); needs API_URL
#   MODE=all  -> both in one container (for Hugging Face Spaces / single-service hosting):
#                API on 127.0.0.1:8000, Streamlit on ${PORT:-7860}
set -euo pipefail
MODE="${MODE:-all}"
case "$MODE" in
  api)
    exec uvicorn api.main:app --host 0.0.0.0 --port 8000
    ;;
  ui)
    exec streamlit run app/Home.py --server.port "${PORT:-8501}" --server.address 0.0.0.0 \
      --server.headless true
    ;;
  all)
    export API_URL="${API_URL:-http://127.0.0.1:8000}"
    uvicorn api.main:app --host 127.0.0.1 --port 8000 &
    echo "Waiting for the API (first start seeds demo data, about 30-60 s)..."
    for i in $(seq 1 120); do curl -sf http://127.0.0.1:8000/health >/dev/null && break; sleep 2; done
    # XSRF off: Streamlit file uploads otherwise fail inside the Hugging Face Spaces iframe (demo only)
    exec streamlit run app/Home.py --server.port "${PORT:-7860}" --server.address 0.0.0.0 \
      --server.headless true --server.enableXsrfProtection false
    ;;
  *)
    echo "Unknown MODE=$MODE (use api, ui or all)"
    exit 1
    ;;
esac
