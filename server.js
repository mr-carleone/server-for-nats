const express = require("express");
const bodyParser = require("body-parser");
const nats = require("nats");
const WebSocket = require("ws");
const cors = require("cors");

const app = express();
const port = 3000;

app.use(bodyParser.json());
app.use(cors()); // Включение поддержки CORS

let nc;
const wss = new WebSocket.Server({ noServer: true });

// Подключение к NATS
(async () => {
  nc = await nats.connect({ servers: "nats://localhost:4222" });
  console.log("Connected to NATS");
})();

// API для отправки сообщений
app.post("/send", async (req, res) => {
  const message = req.body.message;
  console.log(`Sending message: ${message}`);
  await nc.publish("my_subject", message);
  res.send("Message sent");
});

const server = app.listen(port, () => {
  console.log(`Server running at http://localhost:${port}`);
});

server.on("upgrade", (request, socket, head) => {
  wss.handleUpgrade(request, socket, head, (ws) => {
    wss.emit("connection", ws, request);
    console.log("WebSocket connection established");

    // Подписка на сообщения после установления WebSocket-соединения
    const sub = nc.subscribe("my_subject");
    (async (msg) => {
      for await (const m of sub) {
        console.log(`Received message: ${m.data}`);
        wss.clients.forEach((client) => {
          if (client.readyState === WebSocket.OPEN) {
            client.send(m.data.toString()); // Отправляем сообщение как строку
            console.log(`Sent message to client: ${m.data}`);
          }
        });
      }
    })(sub);
  });
});
