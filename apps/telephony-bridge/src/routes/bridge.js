import express from 'express';
import { audioBridgeManager } from '../services/audioBridge.js';

export const bridgeRouter = express.Router();

/**
 * List active media streams.
 * GET /api/bridge/streams
 */
bridgeRouter.get('/streams', (req, res) => {
  const streams = [];
  for (const [streamSid, data] of audioBridgeManager.activeStreams.entries()) {
    streams.push({
      stream_sid: streamSid,
      call_sid: data.callSid,
      call_id: data.callId,
      status: data.ws.readyState === 1 ? 'active' : 'closing',
    });
  }
  return res.json({ count: streams.length, streams });
});

/**
 * Send mu-law audio frame to an active stream.
 * POST /api/bridge/speak
 * Body: { stream_sid: string, audio_base64: string }
 */
bridgeRouter.post('/speak', async (req, res) => {
  const { stream_sid, audio_base64 } = req.body;
  if (!stream_sid || !audio_base64) {
    return res.status(400).json({ error: 'Missing stream_sid or audio_base64' });
  }

  const success = await audioBridgeManager.sendAudio(stream_sid, audio_base64);
  return res.json({ success });
});

/**
 * Send barge-in clear event to Twilio stream.
 * POST /api/bridge/clear
 * Body: { stream_sid: string }
 */
bridgeRouter.post('/clear', (req, res) => {
  const { stream_sid } = req.body;
  if (!stream_sid) {
    return res.status(400).json({ error: 'Missing stream_sid' });
  }

  audioBridgeManager.sendClear(stream_sid);
  return res.json({ success: true, message: `Clear signal dispatched to stream ${stream_sid}` });
});
