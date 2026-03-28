# ElectronChat — FastAPI + WebSocket

A real-time desktop chat application built with **Electron** (frontend) and **FastAPI** (WebSocket server).

## Project Structure

```
electron-chat/
├── fastapi-server/
│   ├── main.py              # FastAPI WebSocket server
│   └── requirements.txt     # Python dependencies
├── electron/
│   ├── package.json
│   └── src/
│       ├── main.js          # Electron main process
│       └── preload.js       # Secure IPC bridge
└── src/
    ├── index.html           # Chat UI
    ├── styles.css           # Styling
    └── app.js               # WebSocket client logic
```

## Setup & Run

### 1. Start the FastAPI WebSocket Server

```bash
cd fastapi-server

# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Start the server
python main.py
# Server runs at: http://localhost:8000
# WebSocket at:   ws://localhost:8000/ws/{room}/{username}
```

### 2. Start the Electron App

```bash
cd electron

# Install dependencies
npm install

# Run the app
npm start
```

### 3. Using the App

1. Enter a **username** (e.g. `Alice`)
2. Enter a **room name** (e.g. `general`)
3. Server URL: `ws://localhost:8000` (default)
4. Click **JOIN ROOM**
5. Open another window with a different username to chat!

---

## Features

- **Real-time messaging** via WebSocket
- **Multiple rooms** — each room is isolated
- **Typing indicators** — see when others are typing
- **Member list** — live online users sidebar
- **Message grouping** — consecutive messages from same user are grouped
- **Heartbeat** — auto ping/pong keeps connection alive
- **Custom frameless window** with native controls

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Server health check |
| `GET /rooms` | List active rooms & online counts |
| `WS /ws/{room}/{username}` | WebSocket chat connection |

## WebSocket Message Types

### Client → Server
```json
{ "type": "message", "content": "Hello!" }
{ "type": "typing", "is_typing": true }
{ "type": "ping" }
```

### Server → Client
```json
{ "type": "message", "user": {...}, "content": "Hello!", "timestamp": "..." }
{ "type": "system", "event": "connected|user_joined|user_left", ... }
{ "type": "typing", "user": "Alice", "is_typing": true }
{ "type": "pong" }
```
