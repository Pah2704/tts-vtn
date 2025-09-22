from fastapi import FastAPI

app = FastAPI(title="TTS-VTN")

@app.get("/healthz")
def healthz():
    return {"ok": True}
