import express from 'express';
import axios from 'axios';
import { twilioService } from '../services/twilioClient.js';
import { config } from '../config.js';

export const voiceRouter = express.Router();

/**
 * Twilio Voice Webhook (triggered when phone call is answered).
 * Generates TwiML connecting the call to the Media Stream WebSocket.
 * POST /api/voice/webhook
 */
voiceRouter.all('/webhook', async (req, res) => {
  const callSid = req.body?.CallSid || req.query?.CallSid;
  const callId = req.query?.call_id || req.body?.call_id || '';

  console.log(`[TwilioBridge:Voice] Call Answered - CallSid: ${callSid}, CallId: ${callId}`);

  // Build the WebSocket Media Stream URL
  let streamWsUrl;
  const baseUrl = config.twilio.webhookBaseUrl.replace(/\/+$/, '');
  if (baseUrl.startsWith('https://')) {
    streamWsUrl = `wss://${baseUrl.slice('https://'.length)}/media-stream?call_id=${encodeURIComponent(callId)}`;
  } else if (baseUrl.startsWith('http://')) {
    streamWsUrl = `ws://${baseUrl.slice('http://'.length)}/media-stream?call_id=${encodeURIComponent(callId)}`;
  } else {
    streamWsUrl = `wss://${baseUrl}/media-stream?call_id=${encodeURIComponent(callId)}`;
  }

  const twiml = twilioService.generateMediaStreamTwiml({
    callId,
    streamWsUrl,
  });

  console.log(`[TwilioBridge:Voice] Responding with TwiML for stream ${streamWsUrl}`);
  res.type('text/xml');
  return res.send(twiml);
});

/**
 * Twilio Call Status Callback.
 * POST /api/voice/status
 */
voiceRouter.post('/status', async (req, res) => {
  const callSid = req.body?.CallSid;
  const callStatus = req.body?.CallStatus;
  const callId = req.query?.call_id;

  console.log(`[TwilioBridge:Voice] Status Update: ${callSid} -> ${callStatus} (call_id: ${callId})`);

  // Forward status update to Python FastAPI backend
  try {
    await axios.post(
      `${config.backendApiUrl}/api/telephony/status-callback?call_id=${encodeURIComponent(callId || '')}`,
      req.body,
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
    ).catch(() => {});
  } catch (err) {
    // Ignore backend forward errors
  }

  return res.json({ status: 'received' });
});
