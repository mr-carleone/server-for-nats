# server.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import nats
import asyncio
import json
from contextlib import asynccontextmanager

app = FastAPI()

# Настройка CORS
origins = [
    "http://localhost:5173",  # Добавьте ваш фронтенд URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(data)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/send")
async def send_message(message: dict):
    nc = await nats.connect("nats://localhost:4222")
    await nc.publish("my_subject", json.dumps(message).encode())
    await nc.close()
    return {"status": "Message sent"}

async def nats_listener(nc):
    async def message_handler(msg):
        data = msg.data.decode()
        await manager.broadcast(data)

    await nc.subscribe("my_subject", cb=message_handler)

@asynccontextmanager
async def lifespan(app: FastAPI):
    nc = await nats.connect("nats://localhost:4222")
    asyncio.create_task(nats_listener(nc))
    yield
    await nc.close()

app.router.lifespan_context = lifespan

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
