from fastapi import FastAPI

app = FastAPI(title="mywheel-backend")


@app.get("/health")
def health():
    return {"status": "ok"}
