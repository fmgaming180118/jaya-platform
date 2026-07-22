# Testing & Development Guide

## Menjalankan Test Suite

```bash
# Jalankan semua test
python -m pytest tests/ -v

# Jalankan test spesifik
python -m pytest tests/test_resource_evolution.py -v

# Dengan coverage
python -m pytest tests/ --cov=src --cov-report=html
```

---

## Struktur Test

```
tests/
├── test_resource_evolution.py    ← Test Digital Twin evolution
├── ...
```

---

## Development Mode

### Hot Reload Backend

```bash
# uvicorn dengan hot reload
uvicorn src.network.research_api:app --reload --host 0.0.0.0 --port 8000
```

### Hot Reload UI

```bash
cd ui
npm run dev   # Vite sudah hot reload by default
```

---

## Menambah Endpoint Baru

1. Tambahkan endpoint di `src/network/research_api.py`
2. Tambahkan method di `ui/src/services/api.js`
3. Update [API Reference](../02-architecture/api-reference.md)

**Template endpoint:**
```python
class MyRequest(BaseModel):
    field: str
    optional_field: str = "default"

@app.post("/my-endpoint")
async def my_endpoint(request: MyRequest):
    """Docstring yang jelas."""
    try:
        result = some_module.do_something(request.field)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## Menambah Modul Academic Baru

Ikuti pola yang sudah ada di `src/research/academic/`:

```python
# src/research/academic/my_analyzer.py
from src.teacher import Teacher

class MyAnalyzer:
    """Docstring: apa yang dianalisis dan outputnya."""
    
    def __init__(self):
        self.brain = Teacher(model_type="reasoning")
    
    def analyze(self, text: str, topic: str) -> str:
        prompt = f"""..."""
        return self.brain.ask(prompt)
```

Kemudian integrasikan ke `run_analysis()` di `research_api.py`.

---

## Environment Variables untuk Development

```bash
# .env — tambahkan untuk development
DEBUG=true
LOG_LEVEL=DEBUG
PORT=8000
```

---

## Linting & Formatting

```bash
# Python
pip install black flake8
black src/
flake8 src/ --max-line-length=120

# JavaScript
cd ui && npm run lint
```

---

**Lihat juga:** [Contributing Guide](../../CONTRIBUTING.md) | [Architecture Overview](../02-architecture/overview.md)
