from fastapi import FastAPI
from threading import Thread
from .consumer import latest_trucks, start_consumer
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for testing only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    Thread(target=start_consumer, daemon=True).start()

@app.get("/trucks")
def get_trucks():
    return list(latest_trucks.values())