from fastapi import FastAPI

app = FastAPI(title="Six-seven")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

