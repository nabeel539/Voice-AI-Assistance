# CIMET Telephony Bridge & Dialer Service (Node.js)

Dedicated high-performance Node.js service for Twilio outbound dialing, voice call bridging, and real-time bidirectional audio streaming via Twilio Media Streams.

## Features

- **Outbound Dialer**: Initiates outbound Twilio voice calls with DNC pre-screening.
- **TwiML Voice Webhook**: Dynamically generates TwiML to connect live calls to WebSocket media streams.
- **Real-time Audio Bridge**: WebSocket server accepting 8kHz $\mu$-law audio frames from Twilio with barge-in detection and instant buffer flushing.
- **Call Management**: Live status callback tracking, remote hangup, and stream monitoring.
- **Backend Integration**: Direct connection with CIMET FastAPI backend.

## Quick Start

### 1. Install Dependencies
```bash
cd apps/telephony-bridge
npm install
```

### 2. Configure Environment
Copy `.env.example` to `.env` and verify your Twilio credentials:
```ini
PORT=5050
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+17372508034
TWILIO_WEBHOOK_BASE_URL=https://<your-ngrok-url>.ngrok-free.dev
BACKEND_API_URL=http://localhost:8000
```

### 3. Run the Service
```bash
# Start server
npm start

# Or dev mode with auto-reload
npm run dev
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/dial` | Place outbound call with DNC check |
| `POST` | `/api/dial/hangup` | Terminate an active Twilio call |
| `GET` | `/api/dial/status/:callSid` | Query Twilio call status |
| `ALL` | `/api/voice/webhook` | Twilio Voice Webhook returning TwiML `<Connect><Stream>` |
| `POST` | `/api/voice/status` | Twilio status callback |
| `GET` | `/api/bridge/streams` | List active Media Stream WebSockets |
| `POST` | `/api/bridge/speak` | Send $\mu$-law audio chunk to live call |
| `POST` | `/api/bridge/clear` | Send Twilio clear signal (interrupt playback) |
| `WS` | `/media-stream` | Twilio Media Stream WebSocket |
