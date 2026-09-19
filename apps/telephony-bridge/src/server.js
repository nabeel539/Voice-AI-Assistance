import http from 'http';
import express from 'express';
import cors from 'cors';
import morgan from 'morgan';
import { WebSocketServer } from 'ws';

import { config } from './config.js';
import { dialerRouter } from './routes/dialer.js';
import { voiceRouter } from './routes/voice.js';
import { bridgeRouter } from './routes/bridge.js';
import { audioBridgeManager } from './services/audioBridge.js';

const app = express();

// Middleware
app.use(cors());
app.use(morgan('dev'));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Health Check
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'cimet-telephony-bridge',
    environment: config.nodeEnv,
    twilio_number: config.twilio.phoneNumber,
    backend_url: config.backendApiUrl,
    timestamp: new Date().toISOString(),
  });
});

// Mount Routes
app.use('/api/dial', dialerRouter);
app.use('/api/voice', voiceRouter);
app.use('/api/bridge', bridgeRouter);

// Root Info
app.get('/', (req, res) => {
  res.json({
    name: 'CIMET Telephony Bridge & Dialer Service',
    version: '1.0.0',
    endpoints: [
      'POST /api/dial',
      'POST /api/dial/hangup',
      'GET /api/dial/status/:callSid',
      'ALL /api/voice/webhook',
      'POST /api/voice/status',
      'GET /api/bridge/streams',
      'POST /api/bridge/speak',
      'POST /api/bridge/clear',
      'WS /media-stream',
    ],
  });
});

// Create HTTP and WebSocket Server
const server = http.createServer(app);
const wss = new WebSocketServer({ noServer: true });

wss.on('connection', (ws, req) => {
  audioBridgeManager.handleConnection(ws, req);
});

// Handle WebSocket upgrade for Twilio Media Streams
server.on('upgrade', (request, socket, head) => {
  const { pathname } = new URL(request.url, `http://${request.headers.host}`);

  if (pathname === '/media-stream' || pathname === '/api/telephony/media-stream') {
    wss.handleUpgrade(request, socket, head, (ws) => {
      wss.emit('connection', ws, request);
    });
  } else {
    socket.destroy();
  }
});

// Start Server
const PORT = config.port;
server.listen(PORT, () => {
  console.log('====================================================');
  console.log(`🚀 CIMET Telephony Bridge & Dialer running on port ${PORT}`);
  console.log(`📞 Twilio Outbound Number: ${config.twilio.phoneNumber || 'Not configured'}`);
  console.log(`🌐 Webhook Base URL: ${config.twilio.webhookBaseUrl}`);
  console.log(`🔗 Connected to Backend API: ${config.backendApiUrl}`);
  console.log('====================================================');
});
