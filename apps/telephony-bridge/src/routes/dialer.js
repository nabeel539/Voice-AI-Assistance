import express from 'express';
import axios from 'axios';
import { twilioService } from '../services/twilioClient.js';
import { config } from '../config.js';

export const dialerRouter = express.Router();

/**
 * Initiate an outbound phone call with DNC verification.
 * POST /api/dial
 * Body: { to: string, lead_id: string, call_id?: string }
 */
dialerRouter.post('/', async (req, res) => {
  const { to, lead_id, call_id } = req.body;

  if (!to || !lead_id) {
    return res.status(400).json({ error: 'Missing required fields: to, lead_id' });
  }

  const effectiveCallId = call_id || `call_${Date.now()}`;

  try {
    // 1. Check DNC via Backend API before placing outbound call
    try {
      const dncCheck = await axios.post(`${config.backendApiUrl}/api/dnc/check`, { phone: to });
      if (dncCheck.data && dncCheck.data.allowed === false) {
        return res.status(403).json({
          status: 'dnc_blocked',
          call_id: effectiveCallId,
          message: 'Target number is on Do-Not-Call registry. Outbound call blocked.',
        });
      }
    } catch (dncErr) {
      console.warn('[TwilioBridge:Dialer] DNC service warning:', dncErr.message);
    }

    // 2. Place outbound Twilio Call
    const call = await twilioService.placeCall({
      to,
      leadId: lead_id,
      callId: effectiveCallId,
    });

    return res.json({
      status: 'initiated',
      call_id: effectiveCallId,
      call_sid: call.sid,
      to,
      lead_id,
      twilio_status: call.status,
      message: `Outbound call initiated via Twilio (Call SID: ${call.sid})`,
    });
  } catch (error) {
    console.error('[TwilioBridge:Dialer] Failed to place outbound call:', error);
    return res.status(500).json({
      error: 'Failed to initiate outbound call',
      detail: error.message,
    });
  }
});

/**
 * Hang up an active call.
 * POST /api/dial/hangup
 * Body: { call_sid: string }
 */
dialerRouter.post('/hangup', async (req, res) => {
  const { call_sid } = req.body;
  if (!call_sid) {
    return res.status(400).json({ error: 'Missing call_sid' });
  }

  try {
    await twilioService.hangupCall(call_sid);
    return res.json({ status: 'completed', call_sid });
  } catch (error) {
    console.error('[TwilioBridge:Dialer] Failed to hang up call:', error);
    return res.status(500).json({ error: 'Failed to hang up call', detail: error.message });
  }
});

/**
 * Get call status from Twilio.
 * GET /api/dial/status/:callSid
 */
dialerRouter.get('/status/:callSid', async (req, res) => {
  const { callSid } = req.params;
  try {
    const client = twilioService.getClient();
    const call = await client.calls(callSid).fetch();
    return res.json({
      call_sid: call.sid,
      status: call.status,
      duration: call.duration,
      from: call.from,
      to: call.to,
      start_time: call.startTime,
      end_time: call.endTime,
    });
  } catch (error) {
    return res.status(500).json({ error: 'Failed to fetch call status', detail: error.message });
  }
});
