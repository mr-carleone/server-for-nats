# server.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import nats
import asyncio
import json
from contextlib import asynccontextmanager
from loguru import logger

# Логгер с паттерном Singleton
class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]

class Logger(metaclass=SingletonMeta):
    def __init__(self):
        logger.add("logs/file_{time}.log", rotation="50 MB")  # Логирование в файл
        logger.add(lambda msg: print(msg), colorize=True, format="<green>{time}</green> <level>{message}</level>")  # Логирование в консоль

    def info(self, message):
        logger.info(message)

    def error(self, message):
        logger.error(message)

    def debug(self, message):
        logger.debug(message)

    def warning(self, message):
        logger.warning(message)

# Инициализация логгера
log = Logger()

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
    js = nc.jetstream()
    await js.add_stream(name="MY_STREAM", subjects=["my_subject"])
    await js.publish("my_subject", json.dumps(message).encode())
    await nc.close()
    return {"status": "Message sent"}

@app.get("/message_count")
async def get_message_count():
    nc = await nats.connect("nats://localhost:4222")
    js = nc.jetstream()
    stream_info = await js.stream_info("MY_STREAM")
    await nc.close()
    return {"count": stream_info.state.messages}

async def nats_listener(nc):
    js = nc.jetstream()
    async def message_handler(msg):
        data = msg.data.decode()
        parsed_data = json.loads(data)
        log.info(f"Received message from broker: {parsed_data['message']}")
        await manager.broadcast(data)

    try:
        await js.subscribe("my_subject", cb=message_handler)
    except nats.js.errors.NotFoundError:
        log.error("Stream or subject not found. Ensure the stream is created and the subject is correct.")
    except Exception as e:
        log.error(f"An error occurred: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    nc = await nats.connect("nats://localhost:4222")
    js = nc.jetstream()

    # Создаем поток, если он не существует
    try:
        await js.add_stream(name="MY_STREAM", subjects=["my_subject"])
    except nats.js.errors.StreamNameAlreadyInUseError:
        pass  # Поток уже существует

    asyncio.create_task(nats_listener(nc))
    yield
    await nc.close()

app.router.lifespan_context = lifespan

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
