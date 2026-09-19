import twilio from 'twilio';
import { config } from '../config.js';

class TwilioClientService {
  constructor() {
    this._client = null;
  }

  getClient() {
    if (!this._client) {
      if (!config.twilio.accountSid || !config.twilio.authToken) {
        throw new Error('Twilio Account SID and Auth Token must be configured.');
      }
      this._client = twilio(config.twilio.accountSid, config.twilio.authToken);
    }
    return this._client;
  }

  /**
   * Place an outbound phone call via Twilio.
   * @param {Object} params
   * @param {string} params.to - Recipient phone number in E.164 format
   * @param {string} params.callId - CIMET internal call session ID
   * @param {string} [params.leadId] - Lead identifier
   * @returns {Promise<Object>} Twilio Call instance
   */
  async placeCall({ to, callId, leadId }) {
    const client = this.getClient();
    const baseUrl = config.twilio.webhookBaseUrl.replace(/\/+$/, '');
    const webhookUrl = `${baseUrl}/api/voice/webhook?call_id=${encodeURIComponent(callId)}`;
    const statusCallbackUrl = `${baseUrl}/api/voice/status?call_id=${encodeURIComponent(callId)}`;

    console.log(`[TwilioBridge:Dialer] Placing call to ${to} for lead ${leadId} (call_id: ${callId})`);
    console.log(`[TwilioBridge:Dialer] Webhook: ${webhookUrl}`);

    const call = await client.calls.create({
      to,
      from: config.twilio.phoneNumber,
      url: webhookUrl,
      statusCallback: statusCallbackUrl,
      statusCallbackEvent: ['initiated', 'ringing', 'answered', 'completed'],
      statusCallbackMethod: 'POST',
    });

    console.log(`[TwilioBridge:Dialer] Call successfully placed. CallSid: ${call.sid}`);
    return call;
  }

  /**
   * Hang up an active call.
   * @param {string} callSid - Twilio Call SID
   */
  async hangupCall(callSid) {
    const client = this.getClient();
    console.log(`[TwilioBridge:Dialer] Terminating call ${callSid}`);
    return await client.calls(callSid).update({ status: 'completed' });
  }

  /**
   * Generate TwiML XML to connect the call to the Media Stream WebSocket.
   * @param {Object} params
   * @param {string} params.callId - CIMET Call ID
   * @param {string} params.streamWsUrl - WebSocket URL for media streaming
   * @returns {string} TwiML XML string
   */
  generateMediaStreamTwiml({ callId, streamWsUrl }) {
    const VoiceResponse = twilio.twiml.VoiceResponse;
    const response = new VoiceResponse();

    const connect = response.connect();
    const stream = connect.stream({
      url: streamWsUrl,
    });

    if (callId) {
      stream.parameter({
        name: 'call_id',
        value: callId,
      });
    }

    return response.toString();
  }
}

export const twilioService = new TwilioClientService();
