# Reconnect — Autonomous Voice AI for Energy Journey Recovery

> **CIMET / econnex Engineering Hackathon Solution**  
> An enterprise-grade, deterministic AI voice recovery agent (*"Emma from CIMET"*) engineered to proactively re-engage customers who dropped off during their energy comparison journey, capture missing fields with real-time validation, confirm pre-existing CRM data, submit valid payloads to the CIMET sandbox, and gracefully escalate complex situations to human specialists.

---

## 🌟 Key Features

1. **Deterministic Multi-Turn State Machine (LangGraph)**
   - Resumes seamlessly from the exact step where the customer dropped off (`property_details`, `energy_details`, `usage_details`, or `customer_details`).
   - Zero unnecessary questioning: Pre-existing lead reference data (e.g. `email`, `last_name`, `phone`) is politely confirmed (*"I have your email as nabeel@example.com, is that still correct?"*) rather than re-prompted from scratch.

2. **Real-Time Bidirectional Twilio Telephony & Media Streams**
   - Direct PSTN call placement to real phone devices with low-latency full-duplex audio streaming (`audio/x-mulaw` 8kHz).
   - Robust debounced RMS Voice Activity Detection (VAD) with Barge-In detection allowing callers to interrupt naturally.
   - Acoustic echo suppression preventing self-speech feedback loops.
   - Automatic post-submission / handoff clean call termination with a polite closing farewell.

3. **11 Guardrail Safety Rules & Human Handoff Engine**
   - DNC (Do-Not-Call) registry pre-call gating.
   - Explicit recording consent verification prior to data capture.
   - Immediate escalation with structured handoff packages for sensitive scenarios (payment distress, billing disputes, vulnerable customers, off-script questions).
   - Configurable validation retry limits (`MAX_VALIDATION_RETRIES` via `.env`).

4. **Live Operator & Observability Console (Next.js & Tailwind CSS)**
   - Live visual journey stepper showing completed and in-progress steps in real-time.
   - Live audio waveform and streaming transcript viewer.
   - Operator escalation handoff panel with full context packages.
   - Real-time CRM submission payload viewer.

---

## 🏗️ Architecture

```
                                  ┌───────────────────────────────┐
                                  │       Customer (PSTN)         │
                                  └───────────────┬───────────────┘
                                                  │ (Phone Call)
                                                  ▼
┌───────────────────────────────┐        ┌───────────────────────────────┐
│       Next.js Console         │◄───────┤         Twilio Cloud          │
│   (Real-time State & Logs)    │ (Poll) └───────────────┬───────────────┘
└───────────────▲───────────────┘                        │
                │                                        │ (TwiML / Media WebSocket)
                │                                        ▼
┌───────────────┴────────────────────────────────────────────────────────┐
│                        FastAPI Backend (Port 8000)                     │
│                                                                        │
│  ┌───────────────────────┐   ┌──────────────────────────────────────┐  │
│  │   Telephony Manager   │   │         LangGraph Agent Core         │  │
│  │  (VAD & Audio Stream) │──►│   - DNC Check Node                   │  │
│  └───────────┬───────────┘   │   - Recording Consent Node           │  │
│              │               │   - Guardrail Safety Node            │  │
│              ▼               │   - Structured Field Extractor       │  │
│  ┌───────────────────────┐   │   - CRM Journey Submission Node      │  │
│  │ OpenAI Speech / Voice │   │   - Specialist Handoff Dispatcher    │  │
│  │ (Whisper STT / TTS)   │   └──────────────────────────────────────┘  │
│  └───────────────────────┘                                             │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Python**: 3.11 or higher
- **Node.js**: 18+ and `npm`
- **OpenAI API Key** (for Whisper-1 STT, GPT-4o, and TTS)
- **Twilio Account** (Account SID, Auth Token, and a Twilio phone number)
- **Ngrok** (for local webhook tunneling during live phone testing)

---

### 2. Environment Configuration

1. In the project root, copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Open `.env` and fill in your credentials:
   ```ini
   # --- OpenAI ---
   OPENAI_API_KEY=sk-proj-...
   OPENAI_LLM_MODEL=gpt-4o
   OPENAI_STT_MODEL=whisper-1
   OPENAI_TTS_MODEL=gpt-4o-mini-tts

   # --- Telephony (Twilio) ---
   TELEPHONY_PROVIDER=twilio
   TELEPHONY_SIMULATE=false
   TWILIO_ACCOUNT_SID=AC...
   TWILIO_AUTH_TOKEN=...
   TWILIO_PHONE_NUMBER=+13613269124
   TWILIO_WEBHOOK_BASE_URL=https://your-subdomain.ngrok-free.dev
   TWILIO_TEST_RECIPIENT_PHONE=+917894526165

   # --- Validation Retries ---
   MAX_VALIDATION_RETRIES=5
   ```

---

### 3. Backend Setup & Startup

1. Navigate to the backend directory and set up a virtual environment:
   ```bash
   cd apps/backend
   python -m venv venv
   
   # Activate virtual environment:
   # Windows:
   venv\Scripts\activate
   # macOS / Linux:
   source venv/bin/activate
   ```

2. Install backend dependencies:
   ```bash
   pip install -r ../../requirements.txt
   ```

3. Start the FastAPI server on port `8000`:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

4. Verify backend health:
   ```bash
   curl http://localhost:8000/health
   # Response: {"status":"ok"}
   ```

---

### 4. Frontend Setup & Startup

1. Open a new terminal and navigate to the frontend directory:
   ```bash
   cd apps/frontend
   ```

2. Install frontend dependencies:
   ```bash
   npm install
   ```

3. Start the Next.js development server:
   ```bash
   npm run dev
   ```

4. Open [http://localhost:3000](http://localhost:3000) in your browser to view the Recovery Console.

---

### 5. Live PSTN Outbound Phone Testing (with Ngrok)

To place real phone calls to mobile devices via Twilio:

1. In a separate terminal, expose your local backend port 8000:
   ```bash
   ngrok http 8000
   ```
2. Copy your public ngrok URL (e.g. `https://xxxx.ngrok-free.dev`) and set `TWILIO_WEBHOOK_BASE_URL` in `.env`.
3. In the Web Console at [http://localhost:3000](http://localhost:3000), select a lead (e.g. `ENG-DEMO-001`) and click **Place Call**.
4. Answer the incoming call on your phone and speak with Emma!

---

## 🧪 Testing & Verification

### Automated Scenario Tests
Run the comprehensive 12-scenario evaluation suite:
```bash
cd apps/backend
pytest -v
```

The test suite covers:
- **Scenario 1**: Happy Path Resume & CRM Submission
- **Scenario 2**: Misheard Answer Clarification
- **Scenario 3**: Invalid Value Retry & Formats
- **Scenario 4**: Customer Busy / Polite Callback
- **Scenario 5**: Not Interested / Immediate Exit
- **Scenario 6**: Frustration Escalation to Human
- **Scenario 7**: Direct Human Representative Request
- **Scenario 8**: Payment Distress / Financial Hardship
- **Scenario 9**: Off-Script Plan Advice
- **Scenario 10**: Complex Multi-Meter Inquiry
- **Scenario 11**: Disconnection / Vulnerable Customer
- **Scenario 12**: DNC Number Block Enforcement

---

## 📁 Repository Structure

```
cimet-reconnect/
├── apps/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── agent/             # LangGraph workflow, nodes & tools
│   │   │   ├── api/               # FastAPI endpoints (calls, telephony, webhooks)
│   │   │   ├── domain/            # Call state, journey models, schemas
│   │   │   ├── services/          # VAD, STT, TTS, Guardrails, Extraction
│   │   │   └── config.py          # Dynamic environment configuration
│   │   └── tests/                 # Full automated test suite (12 scenarios)
│   └── frontend/
│       ├── src/
│       │   ├── app/               # Next.js App Router (Console Dashboard)
│       │   ├── components/        # Journey Stepper, Waveform, Transcript, Payloads
│       │   └── lib/               # API clients and audio utilities
│       └── package.json
├── data/
│   └── mock/                      # Leads & Energy journey schema specifications
├── requirements.txt               # Backend Python dependencies
├── .env.example                   # Clean template for required secrets
└── README.md                      # Complete system documentation
```

---

## 🔒 Security & Privacy Notice
- Real customer credentials, API keys, and auth tokens are strictly excluded from version control via `.gitignore`.
- Utterances are redacted for payment and credit card information prior to logging.
- Do-Not-Call (DNC) checking and recording consent gating are strictly enforced before saving any customer details.
