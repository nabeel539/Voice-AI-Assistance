/**
 * CIMET Reconnect — Frontend Domain Types
 * Matches the backend domain models and API contracts.
 */

export type JourneyStep =
  | "property_details"
  | "energy_details"
  | "usage_details"
  | "customer_details"
  | "completion";

export type ConsentStatus = "pending" | "consented" | "declined";

export type CallStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "declined"
  | "handoff"
  | "failed"
  | "ended";

export type EscalationReason =
  | "none"
  | "frustration"
  | "confusion"
  | "human_request"
  | "payment"
  | "off_script"
  | "sensitive"
  | "low_confidence"
  | "advice_request"
  | "repeated_failure";

export type JourneySubmissionStatus =
  | "not_started"
  | "ready"
  | "submitted"
  | "success"
  | "failed";

export interface Lead {
  lead_id: string;
  last_completed_step: JourneyStep;
  test_contact: string;
  status: string;
  created_at: string;
}

export interface ConversationMessage {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  field_name?: string;
  confidence?: number;
}

export interface CallState {
  lead_id: string;
  call_id: string;
  current_step: JourneyStep;
  completed_steps: JourneyStep[];
  collected_fields: Record<string, any>;
  missing_fields: string[];
  call_status: CallStatus;
  consent_status: ConsentStatus;
  current_field?: string | null;
  retry_count: number;
  max_retries: number;
  escalation_status: EscalationReason;
  escalation_reason: string;
  journey_submission_status: JourneySubmissionStatus;
  submission_reference_id?: string;
  conversation_history: ConversationMessage[];
  dnc_checked: boolean;
  dnc_allowed: boolean;
  channel?: "browser" | "twilio" | "vapi" | "phone" | string;
  twilio_call_sid?: string | null;
  twilio_stream_sid?: string | null;
  to_phone?: string | null;
  started_at: string;
  last_updated: string;
}

export interface OutboundCallResponse {
  call_id: string;
  lead_id: string;
  twilio_call_sid?: string | null;
  status: string;
  call_state: CallState;
  message: string;
}

export interface HandoffPackage {
  handoff_id: string;
  lead_id: string;
  call_id: string;
  created_at: string;
  current_step: JourneyStep;
  escalation_reason: EscalationReason;
  customer_statement: string;
  summary: string;
  collected_fields: Record<string, any>;
  missing_fields: string[];
  suggested_operator_action: string;
}

export interface StartCallResponse {
  call_id: string;
  lead_id: string;
  status: string;
  agent_message: string;
  audio_base64?: string | null;
  call_state: CallState;
}

export interface ProcessTurnResponse {
  call_id: string;
  customer_utterance: string;
  agent_message: string;
  audio_base64?: string | null;
  status: string;
  call_state: CallState;
  guardrail_result?: {
    passed: boolean;
    escalation_required: boolean;
    escalation_reason: EscalationReason;
    violation_rule?: string;
    customer_statement: string;
    agent_message?: string;
  } | null;
  handoff_package?: HandoffPackage | null;
  submission_result?: {
    status: JourneySubmissionStatus;
    reference_id?: string;
    http_status_code: number;
    message: string;
    payload?: Record<string, any>;
  } | null;
}
