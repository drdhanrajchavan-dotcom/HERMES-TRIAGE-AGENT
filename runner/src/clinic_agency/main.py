from fastapi import FastAPI

app = FastAPI(title="Clinic Agency Runner")


@app.get("/health")
def health() -> dict[str, str]:
    return {"service": "clinic-agency-runner", "status": "ready"}
