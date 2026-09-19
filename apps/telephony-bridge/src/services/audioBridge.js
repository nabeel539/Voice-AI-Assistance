import axios from 'axios';
import { config } from '../config.js';

class AudioBridgeManager {
  constructor() {
    this.activeStreams = new Map();
  }

  /**
   * Register a new Media Stream WebSocket connection.
   */
  handleConnection(ws, req) {
    const url = new URL(req.url, `http://${req.headers.host}`);
    const callIdParam = url.searchParams.get('call_id');

    let streamSid = null;
    let callSid = null;
    let callId = callIdParam || null;
    let isSpeaking = false;
    let audioBuffer = [];

    console.log(`[TwilioBridge:AudioBridge] Media stream connected (call_id param: ${callIdParam})`);

    ws.on('message', async (message) => {
      try {
        const data = JSON.parse(message.toString());

        switch (data.event) {
          case 'connected':
            console.log(`[TwilioBridge:AudioBridge] Protocol connected: ${data.protocol}`);
            break;

          case 'start': {
            const startData = data.start || {};
            streamSid = startData.streamSid;
            callSid = startData.callSid;
            const customParams = startData.customParameters || {};
            callId = customParams.call_id || callId;

            this.activeStreams.set(streamSid, { ws, callSid, callId });
            console.log(`[TwilioBridge:AudioBridge] Stream Started - StreamSid: ${streamSid}, CallSid: ${callSid}, CallId: ${callId}`);

            // Forward stream start event to CIMET backend
            try {
              await axios.post(`${config.backendApiUrl}/api/telephony/logs`, {
                event: 'STREAM_STARTED_NODE_BRIDGE',
                call_id: callId,
                call_sid: callSid,
                stream_sid: streamSid,
                timestamp: new Date().toISOString(),
              }).catch(() => {});
            } catch (err) {
              // Ignore logging error
            }
            break;
          }

          case 'media': {
            const payload = data.media?.payload;
            if (payload && streamSid) {
              const chunk = Buffer.from(payload, 'base64');
              audioBuffer.push(chunk);

              // Detect barge-in energy if agent is currently speaking
              if (isSpeaking) {
                const nonSilent = chunk.filter(b => b !== 0xFF && b !== 0x7F && b !== 0xFE && b !== 0x7E).length;
                if (nonSilent > chunk.length * 0.4) {
                  console.log(`[TwilioBridge:AudioBridge] Barge-in detected on stream ${streamSid}. Sending clear event.`);
                  ws.send(JSON.stringify({ event: 'clear', streamSid }));
                  isSpeaking = false;
                }
              }

              // Periodic flush / forward audio chunk to backend AI agent when buffer reaches ~1s
              const totalBytes = audioBuffer.reduce((acc, c) => acc + c.length, 0);
              if (totalBytes >= 8000) {
                const combined = Buffer.concat(audioBuffer);
                audioBuffer = [];
                // Process / forward speech buffer as needed
              }
            }
            break;
          }

          case 'stop': {
            console.log(`[TwilioBridge:AudioBridge] Stream Stopped - StreamSid: ${streamSid}`);
            if (streamSid) {
              this.activeStreams.delete(streamSid);
            }
            break;
          }

          default:
            break;
        }
      } catch (err) {
        console.error('[TwilioBridge:AudioBridge] Error processing message:', err.message);
      }
    });

    ws.on('close', () => {
      if (streamSid) {
        this.activeStreams.delete(streamSid);
      }
      console.log(`[TwilioBridge:AudioBridge] Media stream closed for stream ${streamSid}`);
    });

    ws.on('error', (err) => {
      console.error(`[TwilioBridge:AudioBridge] WebSocket error on stream ${streamSid}:`, err);
    });
  }

  /**
   * Send 8kHz mu-law audio frame to Twilio.
   */
  async sendAudio(streamSid, mulawBase64) {
    const stream = this.activeStreams.get(streamSid);
    if (!stream || stream.ws.readyState !== 1) {
      console.warn(`[TwilioBridge:AudioBridge] Stream ${streamSid} not open.`);
      return false;
    }

    const mediaMessage = {
      event: 'media',
      streamSid,
      media: {
        payload: mulawBase64,
      },
    };
    stream.ws.send(JSON.stringify(mediaMessage));
    return true;
  }

  /**
   * Send clear signal to Twilio to halt audio queue immediately.
   */
  sendClear(streamSid) {
    const stream = this.activeStreams.get(streamSid);
    if (stream && stream.ws.readyState === 1) {
      stream.ws.send(JSON.stringify({ event: 'clear', streamSid }));
    }
  }
}

export const audioBridgeManager = new AudioBridgeManager();
