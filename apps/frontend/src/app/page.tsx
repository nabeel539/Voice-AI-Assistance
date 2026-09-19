"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  PhoneCall,
  Radio,
  ShieldCheck,
  AlertTriangle,
  RotateCcw,
  Volume2,
  Mic,
  User,
  Eye,
  Activity,
  Layers,
} from "lucide-react";
import { api } from "@/lib/api";
import {
  CallState,
  ConversationMessage,
  HandoffPackage,
  Lead,
  ProcessTurnResponse,
} from "@/types";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { SiteHeader } from "@/components/site-header";
import { PageHeader } from "@/components/page-header";
import { StatCard } from "@/components/stat-card";
import { SpeechInput } from "@/components/voice/SpeechInput";
import { AudioPlayer } from "@/components/voice/AudioPlayer";
import { Transcription } from "@/components/voice/Transcription";
import { VoiceSelector } from "@/components/voice/VoiceSelector";
import { JourneyProgress } from "@/components/console/JourneyProgress";
import { CollectedFieldsGrid } from "@/components/console/CollectedFieldsGrid";
import { HandoffAlert } from "@/components/console/HandoffAlert";
import { SubmissionSuccessBanner } from "@/components/console/SubmissionSuccessBanner";
import { LeadsQueue } from "@/components/console/LeadsQueue";

export default function ReconnectConsolePage() {
  // System & Leads State
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [isLoadingLeads, setIsLoadingLeads] = useState(true);

  // Active Call State (Strictly isolated to current active session)
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null);
  const [callState, setCallState] = useState<CallState | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [currentAudioBase64, setCurrentAudioBase64] = useState<string | null>(null);
  const [handoffPackage, setHandoffPackage] = useState<HandoffPackage | null>(null);
  const [submissionResult, setSubmissionResult] = useState<any | null>(null);

  // Operator Handoffs Archive & Historical Inspection Dialog State
  const [allHandoffs, setAllHandoffs] = useState<HandoffPackage[]>([]);
  const [inspectHandoff, setInspectHandoff] = useState<HandoffPackage | null>(null);
  const [isProgressDrawerOpen, setIsProgressDrawerOpen] = useState(false);

  // Turn Execution State
  const [isStartingCall, setIsStartingCall] = useState(false);
  const [isProcessingTurn, setIsProcessingTurn] = useState(false);
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false);
  const [isListening, setIsListening] = useState(false);

  // Voice Configuration
  const [currentVoice, setCurrentVoice] = useState("sage");
  const [synthesizeVoice, setSynthesizeVoice] = useState(true);

  // Initial Load: Check backend health & fetch leads
  const fetchInitialData = useCallback(async () => {
    setIsLoadingLeads(true);
    try {
      await api.getHealth();
      setBackendOnline(true);
    } catch {
      setBackendOnline(false);
    }

    try {
      const fetchedLeads = await api.getLeads();
      setLeads(fetchedLeads);
      if (fetchedLeads.length > 0 && !selectedLeadId) {
        setSelectedLeadId(fetchedLeads[0].lead_id);
      }
    } catch (e) {
      console.error("Failed to fetch leads:", e);
    } finally {
      setIsLoadingLeads(false);
    }

    try {
      const handoffs = await api.getHandoffs();
      setAllHandoffs(handoffs);
    } catch (e) {
      console.warn("Could not fetch handoffs list:", e);
    }
  }, [selectedLeadId]);

  useEffect(() => {
    fetchInitialData();
  }, [fetchInitialData]);

  // Start Recovery Call for a lead with strict session isolation
  const handleStartCall = async (leadId: string, channel: string = "browser") => {
    setSelectedLeadId(leadId);
    setIsStartingCall(true);
    setCallState(null);
    setMessages([]);
    setHandoffPackage(null);
    setSubmissionResult(null);
    setCurrentAudioBase64(null);
    setIsAgentSpeaking(false);
    setIsListening(false);
    setIsProcessingTurn(false);

    try {
      if (channel !== "browser") {
        const resp = await api.startOutboundTwilioCall(leadId);
        setCallState(resp.call_state);
        setSelectedLeadId(resp.lead_id);

        const initialMsgs: ConversationMessage[] = [
          {
            role: "assistant",
            content: resp.message || `Outbound phone call initiated (Call ID: ${resp.twilio_call_sid || "pending"}).`,
            timestamp: new Date().toISOString(),
          },
        ];
        setMessages(initialMsgs);
      } else {
        const resp = await api.startCall(leadId, synthesizeVoice);
        setCallState(resp.call_state);
        setSelectedLeadId(resp.lead_id);

        const initialMsgs: ConversationMessage[] = [
          {
            role: "assistant",
            content: resp.agent_message,
            timestamp: new Date().toISOString(),
          },
        ];
        setMessages(initialMsgs);

        if (resp.audio_base64) {
          setCurrentAudioBase64(resp.audio_base64);
          setIsAgentSpeaking(true);
        }
      }
    } catch (err: any) {
      alert(`Error starting recovery call: ${err.message}`);
    } finally {
      setIsStartingCall(false);
    }
  };

  // Process Turn via Voice Audio
  const handleAudioTurn = async (audioBlob: Blob) => {
    if (!callState) return;
    setIsProcessingTurn(true);

    try {
      const resp = await api.processTurnAudio(callState.call_id, audioBlob, synthesizeVoice);
      handleTurnResponse(resp);
    } catch (err: any) {
      console.error("Voice turn error:", err);
      alert(`Turn failed: ${err.message}`);
    } finally {
      setIsProcessingTurn(false);
    }
  };

  // Process Turn via Direct Text
  const handleTextTurn = async (text: string) => {
    if (!callState) return;
    setIsProcessingTurn(true);

    try {
      const resp = await api.processTurnJson(callState.call_id, text, synthesizeVoice);
      handleTurnResponse(resp);
    } catch (err: any) {
      console.error("Text turn error:", err);
      alert(`Turn failed: ${err.message}`);
    } finally {
      setIsProcessingTurn(false);
    }
  };

  // Handle Response from LangGraph backend
  const handleTurnResponse = (resp: ProcessTurnResponse) => {
    setCallState(resp.call_state);

    const newTurns: ConversationMessage[] = [
      {
        role: "user",
        content: resp.customer_utterance,
        timestamp: new Date().toISOString(),
      },
      {
        role: "assistant",
        content: resp.agent_message,
        timestamp: new Date().toISOString(),
        field_name: resp.call_state.current_field || undefined,
      },
    ];

    setMessages((prev) => [...prev, ...newTurns]);

    if (resp.audio_base64) {
      setCurrentAudioBase64(resp.audio_base64);
      setIsAgentSpeaking(true);
    }

    if (resp.handoff_package) {
      setHandoffPackage(resp.handoff_package);
      setAllHandoffs((prev) => [resp.handoff_package!, ...prev]);
    }

    if (resp.submission_result) {
      setSubmissionResult(resp.submission_result);
    }
  };

  // End active call
  const handleEndCall = async () => {
    if (!callState) return;
    try {
      const ended = await api.endCall(callState.call_id);
      setCallState(ended);
      setIsAgentSpeaking(false);
      setIsListening(false);
    } catch (e) {
      console.error("Failed to end call:", e);
    }
  };

  const isCallActive = !!(callState && ["pending", "in_progress"].includes(callState.call_status));

  // Live Sync for Telephony Phone Calls (Vapi / Twilio): Poll call state and conversation history in real time
  useEffect(() => {
    if (!callState || callState.channel === "browser" || !isCallActive) return;

    const interval = setInterval(async () => {
      try {
        const updatedState = await api.getCallState(callState.call_id);
        setCallState(updatedState);

        // Sync conversation history from backend if new messages arrived
        if (updatedState.conversation_history && updatedState.conversation_history.length > 0) {
          setMessages(updatedState.conversation_history);
        }

        // Check if handoff was triggered
        if (
          updatedState.call_status === "handoff" ||
          (updatedState.escalation_status && updatedState.escalation_status !== "none")
        ) {
          const handoffs = await api.getHandoffs();
          const activeH = handoffs.find((h) => h.call_id === updatedState.call_id);
          if (activeH) setHandoffPackage(activeH);
        }
      } catch (err) {
        console.warn("Error polling phone call state:", err);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [callState?.call_id, callState?.channel, isCallActive]);

  // Session Isolation: Active escalation must strictly belong to current active call
  const activeSessionHandoff =
    handoffPackage && callState && handoffPackage.call_id === callState.call_id
      ? handoffPackage
      : null;

  // Voice State Indicator Configuration
  const getVoiceState = () => {
    if (!isCallActive) {
      return {
        label: "Idle",
        tone: "default" as const,
        icon: Radio,
        desc: "Standby",
      };
    }
    if (isListening) {
      return {
        label: "Listening",
        tone: "destructive" as const,
        icon: Mic,
        desc: "Capturing audio",
      };
    }
    if (isProcessingTurn) {
      return {
        label: "Processing",
        tone: "amber" as const,
        icon: RotateCcw,
        desc: "STT & LangGraph",
      };
    }
    if (isAgentSpeaking) {
      return {
        label: "Speaking",
        tone: "emerald" as const,
        icon: Volume2,
        desc: "Synthesizing voice",
      };
    }
    return {
      label: "Connected",
      tone: "emerald" as const,
      icon: Radio,
      desc: "Awaiting speech",
    };
  };

  const voiceState = getVoiceState();
  const collectedFieldsCount = Object.keys(callState?.collected_fields || {}).length;

  return (
    <div className="min-h-screen lg:h-screen lg:max-h-screen flex flex-col bg-background text-foreground lg:overflow-hidden">
      {/* BidRank SiteHeader */}
      <SiteHeader
        backendOnline={backendOnline}
        isCallActive={isCallActive}
        onEndCall={handleEndCall}
        activeLeadId={callState?.lead_id}
      />

      {/* Main Console Container */}
      <div className="mx-auto w-full max-w-[1600px] px-3 sm:px-6 py-2.5 flex-1 min-h-0 flex flex-col gap-2.5 lg:overflow-hidden">
        {/* BidRank PageHeader */}
        <PageHeader
          title="Energy Recovery Console"
          description="Supervise automated voice dialogues, review real-time speech extraction, and handle live escalation dossiers."
          className="mb-0"
          actions={
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="font-mono text-xs py-1 px-2.5">
                Target: CIMET Energy Sandbox
              </Badge>
            </div>
          }
        />

        {/* BidRank StatCards Row: Key Operations Telemetry */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 shrink-0">
          <StatCard
            label="Active Lead"
            value={callState?.lead_id || selectedLeadId || "None"}
            hint={
              callState ? (
                <span className="font-mono text-[11px] truncate block">
                  Contact: {callState.collected_fields["phone"] || "Available"}
                </span>
              ) : (
                "Select a lead from the queue"
              )
            }
            icon={User}
            tone="default"
            size="sm"
          />

          <StatCard
            label="Session Status"
            value={
              callState?.call_status
                ? callState.call_status.toUpperCase()
                : "STANDBY"
            }
            hint={
              callState ? (
                <span className="font-mono text-[11px] truncate block">
                  {callState.channel === "twilio" ? "Twilio Phone" : "Browser Voice"}
                  {callState.twilio_call_sid ? ` · SID: ${callState.twilio_call_sid.slice(0, 10)}...` : ` · Consent: ${callState.consent_status}`}
                </span>
              ) : (
                "No call active"
              )
            }
            icon={PhoneCall}
            tone={isCallActive ? "emerald" : "default"}
            size="sm"
          />

          <StatCard
            label="Agent Voice State"
            value={voiceState.label}
            hint={
              <span className="font-mono text-[11px]">
                {voiceState.desc} · Retries: {callState?.retry_count || 0}/2
              </span>
            }
            icon={voiceState.icon}
            tone={voiceState.tone}
            size="sm"
          />

          <div
            onClick={() => setIsProgressDrawerOpen(true)}
            className="cursor-pointer group"
            title="Click to open Journey & Data Dossier drawer"
          >
            <StatCard
              label="Lead Data Progress"
              value={`${collectedFieldsCount} / 11 Fields`}
              hint={
                <span className="flex items-center justify-between text-xs">
                  <span className="capitalize font-mono text-[11px]">
                    Step: {callState ? callState.current_step.replace(/_/g, " ") : "Property"}
                  </span>
                  <span className="text-[10px] text-primary group-hover:underline">
                    Dossier ↗
                  </span>
                </span>
              }
              icon={ShieldCheck}
              tone={submissionResult ? "emerald" : "default"}
              size="sm"
              className="group-hover:border-primary/50 transition-colors h-full"
            />
          </div>
        </div>

        {/* Workspace: Left Sidebar + Right Recovery Station */}
        <div className="flex flex-col lg:flex-row gap-3 flex-1 min-h-0 lg:overflow-hidden">
          {/* Left Column: Leads Queue & Escalations Queue */}
          <aside className="w-full lg:w-72 xl:w-80 flex flex-col gap-2.5 shrink-0 h-full min-h-0">
            {/* Dropped Leads Queue */}
            <div className="flex-1 min-h-[220px] overflow-hidden">
              <LeadsQueue
                leads={leads}
                activeLeadId={callState?.lead_id || selectedLeadId}
                activeChannel={callState?.channel || "browser"}
                onSelectLead={handleStartCall}
                isStartingCall={isStartingCall}
                isLoading={isLoadingLeads}
                onRefresh={fetchInitialData}
              />
            </div>

            {/* Operator Escalations Summary Card (Historical Records) */}
            {allHandoffs.length > 0 && (
              <div className="surface bg-card border border-border rounded-xl p-3 text-xs space-y-2 shrink-0 shadow-xs">
                <div className="flex items-center justify-between">
                  <span className="eyebrow uppercase tracking-wider font-semibold text-xs text-muted-foreground flex items-center gap-1.5">
                    <AlertTriangle className="size-3.5 text-amber-500" />
                    <span>Escalations Queue</span>
                  </span>
                  <Badge variant="outline" className="font-mono text-[10px] py-0">
                    {allHandoffs.length} cases
                  </Badge>
                </div>
                <p className="text-[11px] text-muted-foreground leading-normal">
                  Historical records. Click to view dossier without mutating active call state.
                </p>
                <div className="space-y-1.5 max-h-32 overflow-y-auto pr-1">
                  {allHandoffs.map((h) => (
                    <div
                      key={h.handoff_id}
                      onClick={() => setInspectHandoff(h)}
                      className="p-2 rounded-lg border border-border bg-muted/20 hover:bg-muted/50 cursor-pointer transition-colors flex items-center justify-between text-xs"
                    >
                      <div>
                        <span className="font-mono font-semibold text-foreground">
                          {h.lead_id}
                        </span>
                        <span className="text-[10px] text-muted-foreground block capitalize mt-0.5">
                          {h.escalation_reason.replace("_", " ")}
                        </span>
                      </div>
                      <Eye className="size-3.5 text-muted-foreground" />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </aside>

          {/* Right Column: Active Recovery Station */}
          <main className="flex-1 w-full min-w-0 flex flex-col gap-2 h-full min-h-0">
            {/* Quick Status Bar with Drawer Trigger (Journey Progress & Fields hidden by default) */}
            <div className="flex items-center justify-between px-1 py-0.5 shrink-0">
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setIsProgressDrawerOpen(true)}
                  className="h-7 text-xs gap-1.5 rounded-lg border-border hover:bg-muted font-medium bg-card shadow-2xs cursor-pointer"
                >
                  <Layers className="size-3.5 text-primary" />
                  <span>Journey &amp; Captured Fields</span>
                  <Badge variant="secondary" className="font-mono text-[10px] py-0 px-1.5 ml-0.5">
                    {collectedFieldsCount} / 11
                  </Badge>
                </Button>
                <span className="text-[11px] text-muted-foreground font-mono hidden sm:inline">
                  Step: <strong className="text-foreground capitalize">{callState?.current_step.replace(/_/g, " ") || "Property"}</strong>
                </span>
              </div>

              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsProgressDrawerOpen(true)}
                className="h-7 text-xs text-muted-foreground hover:text-foreground gap-1.5 font-mono cursor-pointer"
              >
                <span>Open Dossier Drawer</span>
                <Layers className="size-3" />
              </Button>
            </div>

            {/* Active Escalation Dossier (Strictly for the active session) */}
            {activeSessionHandoff && (
              <div className="shrink-0 max-h-36 overflow-y-auto">
                <HandoffAlert handoff={activeSessionHandoff} />
              </div>
            )}

            {/* Journey Submission Success Banner */}
            {submissionResult && (
              <div className="shrink-0">
                <SubmissionSuccessBanner
                  referenceId={submissionResult.reference_id || "CIMET-REC-COMPLETED"}
                  message={submissionResult.message}
                  payload={submissionResult.payload}
                />
              </div>
            )}

            {/* Live Conversation Transcript with integrated Voice Model & Speech Input */}
            <div className="flex-1 min-h-0 flex flex-col gap-2">
              <Transcription
                messages={messages}
                isProcessing={isProcessingTurn}
                className="flex-1 min-h-0"
                headerAction={
                  <VoiceSelector
                    currentVoice={currentVoice}
                    onVoiceChange={setCurrentVoice}
                    synthesizeVoice={synthesizeVoice}
                    onSynthesizeChange={setSynthesizeVoice}
                  />
                }
              />

              <AudioPlayer
                audioBase64={currentAudioBase64}
                onPlaybackComplete={() => setIsAgentSpeaking(false)}
                onPlaybackStart={() => setIsAgentSpeaking(true)}
              />

              <SpeechInput
                onAudioRecorded={handleAudioTurn}
                onAudioSubmit={handleAudioTurn}
                onTextSubmit={handleTextTurn}
                onRecordingStateChange={setIsListening}
                isDisabled={!isCallActive || isProcessingTurn || isAgentSpeaking}
                disabled={!isCallActive || isProcessingTurn || isAgentSpeaking}
                isProcessing={isProcessingTurn}
                isSpeaking={isAgentSpeaking}
              />
            </div>
          </main>
        </div>
      </div>

      {/* Historical Escalation Inspection Modal (Fixed Dialog) */}
      <Dialog
        open={!!inspectHandoff}
        onOpenChange={(open) => !open && setInspectHandoff(null)}
      >
        <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-sm font-semibold flex items-center gap-2">
              <AlertTriangle className="size-4 text-amber-500" />
              <span>Archived Escalation Dossier</span>
            </DialogTitle>
            <DialogDescription className="text-xs">
              Historical escalation record for lead {inspectHandoff?.lead_id} (Session:{" "}
              {inspectHandoff?.call_id})
            </DialogDescription>
          </DialogHeader>
          {inspectHandoff && <HandoffAlert handoff={inspectHandoff} />}
        </DialogContent>
      </Dialog>

      {/* Lead Journey Progress & Extracted Fields Slide-Over Drawer/Sheet */}
      <Sheet
        open={isProgressDrawerOpen}
        onOpenChange={setIsProgressDrawerOpen}
      >
        <SheetContent side="right" className="sm:max-w-xl flex flex-col gap-5 overflow-y-auto">
          <SheetHeader>
            <SheetTitle className="text-base font-semibold flex items-center gap-2">
              <Layers className="size-4 text-primary" />
              <span>Lead Journey &amp; Extracted Data</span>
            </SheetTitle>
            <SheetDescription>
              Real-time recovery progress, multi-step status, and customer telemetry for lead{" "}
              <span className="font-mono font-medium text-foreground">
                {callState?.lead_id || selectedLeadId || "None"}
              </span>
            </SheetDescription>
          </SheetHeader>

          <div className="space-y-5 flex-1 py-1">
            {/* Step 1: Journey Stepper */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="eyebrow uppercase tracking-wider font-semibold text-xs text-muted-foreground">
                  Journey Stepper
                </span>
                <Badge variant="outline" className="font-mono text-[10px] py-0">
                  {callState?.completed_steps.length || 0} / 4 completed
                </Badge>
              </div>
              <JourneyProgress
                currentStep={callState?.current_step || "property_details"}
                completedSteps={callState?.completed_steps || []}
                isSubmitted={!!submissionResult}
                submissionRef={submissionResult?.reference_id}
              />
            </div>

            {/* Step 2: Captured Fields Grid */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="eyebrow uppercase tracking-wider font-semibold text-xs text-muted-foreground">
                  Extracted Lead Fields
                </span>
                <Badge variant="outline" className="font-mono text-[10px] py-0">
                  {collectedFieldsCount} / 11 collected
                </Badge>
              </div>
              <CollectedFieldsGrid
                collectedFields={callState?.collected_fields || {}}
                currentField={callState?.current_field}
                isSubmitted={!!submissionResult}
              />
            </div>

            {/* Step 3: Active Escalation Details if present */}
            {activeSessionHandoff && (
              <div className="space-y-2 pt-2 border-t border-border">
                <span className="eyebrow uppercase tracking-wider font-semibold text-xs text-amber-500">
                  Active Escalation Dossier
                </span>
                <HandoffAlert handoff={activeSessionHandoff} />
              </div>
            )}

            {/* Step 4: Submission Confirmation if completed */}
            {submissionResult && (
              <div className="space-y-2 pt-2 border-t border-border">
                <span className="eyebrow uppercase tracking-wider font-semibold text-xs text-emerald-600 dark:text-emerald-400">
                  CRM Submission Confirmation
                </span>
                <SubmissionSuccessBanner
                  referenceId={submissionResult.reference_id || "CIMET-REC-COMPLETED"}
                  message={submissionResult.message}
                  payload={submissionResult.payload}
                />
              </div>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
