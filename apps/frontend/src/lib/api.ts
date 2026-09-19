/**
 * CIMET Reconnect — Frontend API Client
 * Connects to the FastAPI backend with error handling and typed responses.
 */

import {
  CallState,
  HandoffPackage,
  Lead,
  ProcessTurnResponse,
  StartCallResponse,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        ...(options.headers || {}),
      },
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      const message = errData.detail || `Request failed with status ${res.status}`;
      throw new ApiError(res.status, message);
    }

    return (await res.json()) as T;
  } catch (err: any) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(500, err.message || "Network error connecting to CIMET backend");
  }
}

export const api = {
  // System Health
  async getHealth(): Promise<{ status: string }> {
    return request<{ status: string }>("/health");
  },

  // Leads
  async getLeads(): Promise<Lead[]> {
    return request<Lead[]>("/api/leads");
  },

  async getLead(leadId: string): Promise<Lead> {
    return request<Lead>(`/api/leads/${leadId}`);
  },

  async startCall(leadId: string, generateVoice: boolean = true): Promise<StartCallResponse> {
    return request<StartCallResponse>(
      `/api/leads/${leadId}/start-call?generate_voice=${generateVoice}`,
      {
        method: "POST",
      }
    );
  },

  // Calls
  async getActiveCalls(): Promise<CallState[]> {
    return request<CallState[]>("/api/calls");
  },

  async getCallState(callId: string): Promise<CallState> {
    return request<CallState>(`/api/calls/${callId}/state`);
  },

  async endCall(callId: string): Promise<CallState> {
    return request<CallState>(`/api/calls/${callId}/end`, {
      method: "POST",
    });
  },

  async getHandoffs(): Promise<HandoffPackage[]> {
    return request<HandoffPackage[]>("/api/calls/handoffs");
  },

  // Voice Interaction Turns
  async processTurnJson(
    callId: string,
    text: string,
    generateVoice: boolean = true
  ): Promise<ProcessTurnResponse> {
    return request<ProcessTurnResponse>("/api/voice/process-turn-json", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        call_id: callId,
        text,
        generate_voice: generateVoice,
      }),
    });
  },

  async processTurnAudio(
    callId: string,
    audioBlob: Blob,
    generateVoice: boolean = true
  ): Promise<ProcessTurnResponse> {
    const formData = new FormData();
    formData.append("call_id", callId);
    formData.append("audio", audioBlob, "customer_speech.wav");
    formData.append("generate_voice", String(generateVoice));

    return request<ProcessTurnResponse>("/api/voice/process-turn", {
      method: "POST",
      body: formData,
    });
  },

  // Telephony (Real Phone via Twilio)
  async startOutboundTwilioCall(
    leadId: string,
    phoneNumber?: string
  ): Promise<import("@/types").OutboundCallResponse> {
    return request<import("@/types").OutboundCallResponse>("/api/telephony/outbound-call", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        lead_id: leadId,
        phone_number: phoneNumber,
      }),
    });
  },

  async simulatePhoneTurn(
    callId: string,
    customerSpeechText: string
  ): Promise<ProcessTurnResponse> {
    return request<ProcessTurnResponse>("/api/telephony/simulate-phone-turn", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        call_id: callId,
        customer_speech_text: customerSpeechText,
      }),
    });
  },
};
