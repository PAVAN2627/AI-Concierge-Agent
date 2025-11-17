# =====================================================================
# AI CONCIERGE AGENT — Diet • Shopping • Travel
# Kaggle Agents Intensive Capstone Project (Production Version)
#
# Key Features:
#   • Multi-Agent System (Diet Agent, Shopping Agent, Travel Agent)
#   • Router + Finite State Machine
#   • Multilingual (English, Hindi, Marathi, Telugu)
#   • Persistent Memory (JSON)
#   • Metrics Tracking (sessions, flows, LLM calls, errors)
#   • Logging to file
#   • Structured Question Flows + Dynamic Questions
#   • Gemini 2.0 Flash for LLM responses
#   • Modern WhatsApp-Style Gradio UI
#   • Built-in self-tests for evaluation
#
# Requirements:
#   • Add GOOGLE_API_KEY in Kaggle Notebook Secrets
#   • Run entire file in ONE CELL
# =====================================================================

!pip install -q google-genai gradio

import json, re, os, logging
from datetime import datetime
import gradio as gr
from kaggle_secrets import UserSecretsClient
from google import genai

# =========================================================
# FILE PATHS & SAFE CREATION
# =========================================================
MEMORY_PATH = "/mnt/data/concierge_memory.json"
METRICS_PATH = "/mnt/data/concierge_metrics.json"
LOG_PATH = "/mnt/data/concierge_agent.log"

os.makedirs("/mnt/data", exist_ok=True)

# Ensure required files exist
if not os.path.exists(MEMORY_PATH):
    with open(MEMORY_PATH, "w") as f: json.dump({}, f, indent=2)

if not os.path.exists(METRICS_PATH):
    with open(METRICS_PATH, "w") as f:
        json.dump({
            "sessions_created": 0,
            "flows_completed": {"diet": 0, "shopping": 0, "travel": 0},
            "total_messages": 0,
            "gemini_calls": 0,
            "errors": 0,
            "last_reset": None
        }, f, indent=2)

if not os.path.exists(LOG_PATH):
    open(LOG_PATH, "w").close()

# =========================================================
# LOGGING
# =========================================================
logger = logging.getLogger("ConciergeAgent")
logger.setLevel(logging.INFO)

if not logger.handlers:
    fh = logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(fh)

logger.info("Agent initialized.")

# =========================================================
# MEMORY & METRICS HANDLERS
# =========================================================
def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except: pass
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

memory_bank = load_json(MEMORY_PATH, {})
metrics = load_json(METRICS_PATH, {})

# =========================================================
# GEMINI CLIENT
# =========================================================
API_KEY = UserSecretsClient().get_secret("GOOGLE_API_KEY")
if not API_KEY:
    raise RuntimeError("Missing GOOGLE_API_KEY in Kaggle Secrets.")

client = genai.Client(api_key=API_KEY)

# Gemini wrapper with metrics tracking
def gemini(prompt, temp=0.3, max_tokens=1500):
    metrics["gemini_calls"] += 1
    save_json(METRICS_PATH, metrics)

    try:
        r = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={"temperature": temp, "max_output_tokens": max_tokens}
        )
        if hasattr(r, "text") and r.text:
            return r.text
        return str(r)
    except Exception as e:
        metrics["errors"] += 1
        save_json(METRICS_PATH, metrics)
        return f"⚠️ Gemini Error: {e}"
# =========================================================
# LANGUAGE & INTENT DETECTION
# =========================================================
LANG_CHOICES = {
    "english": "English",
    "hindi": "Hindi",
    "marathi": "Marathi",
    "telugu": "Telugu"
}

def detect_language_and_intent(message):
    msg = message.lower()

    # Intent heuristics
    if any(w in msg for w in ["diet","weight","calorie","meal","breakfast","lunch","dinner"]):
        intent = "diet"
    elif any(w in msg for w in ["shop","shopping","budget","grocery","buy"]):
        intent = "shopping"
    elif any(w in msg for w in ["trip","travel","vacation","hotel","itinerary"]):
        intent = "travel"
    else:
        intent = "other"

    # Language heuristic
    if re.search("[\u0900-\u097F]", message):
        lang = "Hindi"
    elif re.search("[\u0C00-\u0C7F]", message):
        lang = "Telugu"
    else:
        lang = "English"

    return lang, intent


# =========================================================
# QUESTION FLOWS (AGENT INPUT COLLECTION)
# =========================================================
def base_questions_for_flow(flow):

    if flow == "diet":
        return [
            ("age", "Your age?"),
            ("gender", "Male / Female / Other?"),
            ("height_cm", "Height in cm?"),
            ("weight_kg", "Weight in kg?"),
            ("goal", "Goal: Lose / Maintain / Gain?"),
            ("activity", "Activity level (sedentary / light / moderate / active)?"),
            ("diet_type", "What type of diet do you follow? (Vegetarian / Eggetarian / Non-Vegetarian / Vegan)"),
            ("diet_pref", "Any dietary preferences or allergies? (If none, type 'no')")
        ]

    if flow == "shopping":
        return [
            ("currency", "Currency? (INR / USD / EUR / GBP / AED / CAD)"),
            ("budget", "Total shopping budget?"),
            ("category", "Type of shopping? (Clothes, Groceries, Electronics, Home, Kids, Gifts)"),
            ("purpose", "Purpose? (Daily / Festival / Travel / Wedding / Gift)"),
            ("members", "How many people are you shopping for?"),
            ("preferences", "Any preferences? (brand/size/style/etc.)"),
            ("have", "Do you already have some items? If yes, list them or type 'no'.")
        ]

    if flow == "travel":
        return [
            ("currency", "Currency for budget (INR / USD / EUR / GBP / AED / CAD)?"),
            ("budget", "Total travel budget?"),
            ("origin", "Where are you traveling from?"),
            ("members", "How many travelers?"),
            ("country", "Destination country (or 'not sure')"),
            ("days", "How many days?"),
            ("pref", "Trip type: beach / adventure / city / nature / budget / luxury?")
        ]

    return []

# =========================================================
# FINALIZERS — DIET / SHOPPING / TRAVEL AGENTS
# =========================================================

def finalize_diet(answers, lang):
    diet_type = answers.get("diet_type", "Not specified")

    prompt = f"""
Respond in {lang}. You are a certified dietitian.

User Profile:
{json.dumps(answers, indent=2)}

IMPORTANT:
- The user follows this diet type: **{diet_type}**
- Ensure the entire 7-day meal plan strictly follows this diet type.
  Examples:
    • Vegetarian → No eggs, no meat, no fish.
    • Eggetarian → Eggs allowed, but no meat or fish.
    • Non-Vegetarian → Meat, eggs, fish allowed.
    • Vegan → No animal products (no milk, curd, paneer, honey, butter, cheese).

Your Task:
1) Calculate daily calorie target with explanation.
2) Create a full 7-day meal plan (Breakfast, Lunch, Dinner, Snacks) following the diet type.
3) Provide a weekly grocery shopping list (ingredients only from allowed diet type).
4) Provide a simple 1-week workout plan.
5) Provide 3 actionable and personalized nutrition tips.
"""

    res = gemini(prompt, temp=0.35, max_tokens=6000)

    # persistent memory
    memory_bank["last_diet_pref"] = answers.get("diet_pref")
    memory_bank["last_diet_type"] = answers.get("diet_type")
    memory_bank["last_diet_update"] = datetime.utcnow().isoformat()
    save_json(MEMORY_PATH, memory_bank)

    metrics["flows_completed"]["diet"] += 1
    save_json(METRICS_PATH, metrics)

    return res


def finalize_shopping(answers, lang):
    prompt = f"""
Respond in {lang}. You are an advanced shopping assistant.

User details:
{json.dumps(answers, indent=2)}

Produce:
1) Optimized shopping list (grouped by category)
2) Quantity suggestions (based on members)
3) Low/Mid/High cost estimates in {answers.get("currency")}
4) Store suggestions + money-saving tips
5) Final summary
"""
    res = gemini(prompt, temp=0.35, max_tokens=5000)

    memory_bank["last_shopping_budget"] = {
        "budget": answers.get("budget"),
        "currency": answers.get("currency")
    }
    memory_bank["last_shopping_update"] = datetime.utcnow().isoformat()
    save_json(MEMORY_PATH, memory_bank)

    metrics["flows_completed"]["shopping"] += 1
    save_json(METRICS_PATH, metrics)

    return res


def finalize_travel(answers, lang):
    prompt = f"""
Respond in {lang}. You are an expert travel agent.

User details:
{json.dumps(answers, indent=2)}

If country == "not sure":
    recommend 3 destinations that fit budget + trip style.

Else provide:
1) Intro about the destination
2) Visa summary
3) Best cities/areas to visit
4) {answers.get("days")}-day itinerary
5) Cost breakdown in {answers.get("currency")}
6) Best months + expected weather
7) Packing tips + safety tips
"""
    res = gemini(prompt, temp=0.4, max_tokens=6000)

    memory_bank["last_travel_origin"] = answers.get("origin")
    memory_bank["last_travel_update"] = datetime.utcnow().isoformat()
    save_json(MEMORY_PATH, memory_bank)

    metrics["flows_completed"]["travel"] += 1
    save_json(METRICS_PATH, metrics)

    return res


# =========================================================
# MAIN STATE MACHINE — CHAT HANDLER
# =========================================================

def chat_handler(message, history, state):

    # Initialize state on first call
    if state is None or "stage" not in state:
        state = {"stage": "choose_language"}

    if history is None:
        history = []

    # Count every user message
    metrics["total_messages"] += 1
    save_json(METRICS_PATH, metrics)

    # Save user message
    history.append({"role": "user", "content": message})

    # ---------------------------
    # 1. Language selection
    # ---------------------------
    if state["stage"] == "choose_language":
        msg = message.lower().strip()

        if msg in LANG_CHOICES:
            state["lang"] = LANG_CHOICES[msg]
            state["stage"] = "choose_flow"

            history.append({
                "role": "assistant",
                "content": (
                    f"Language set to **{state['lang']}**.\n\n"
                    "How can I help you today?\n"
                    "• Diet Plan\n• Shopping Help\n• Travel Planning\n\n"
                    "Type: **diet**, **shopping**, or **travel**"
                )
            })
            return history, state

        history.append({"role": "assistant", "content": "Please select a language: English / Hindi / Marathi / Telugu"})
        return history, state

    # ---------------------------
    # 2. Flow selection
    # ---------------------------
    if state["stage"] == "choose_flow":
        msg = message.lower().strip()

        if msg in ["diet", "shopping", "travel"]:
            state["flow"] = msg
            state["questions"] = base_questions_for_flow(msg)
            state["answers"] = {}
            state["q_index"] = 0
            state["stage"] = "collecting"

            metrics["sessions_created"] += 1
            save_json(METRICS_PATH, metrics)

            # Ask first question
            q = state["questions"][0][1]
            history.append({"role": "assistant", "content": q})
            return history, state

        history.append({"role": "assistant", "content": "Please type: diet / shopping / travel"})
        return history, state

    # ---------------------------
    # 3. Collecting user answers
    # ---------------------------
    if state["stage"] == "collecting":
        idx = state["q_index"]
        key = state["questions"][idx][0]
        state["answers"][key] = message.strip()
        state["q_index"] += 1

        # ----------------------------------------------------
        # 🔥 NEW: Allergy follow-up for Diet Flow
        # ----------------------------------------------------
        if state["flow"] == "diet" and key == "diet_pref":
            ans = message.lower().strip()

            if ans in ["yes", "y", "allergies", "i have allergies", "i'm allergic", "allergy"]:
                # Ask user to specify allergies
                history.append({
                    "role": "assistant",
                    "content": "Please specify your allergies (e.g., dairy, peanuts, gluten, soy, egg)."
                })

                # Insert new question dynamically
                state["questions"].insert(idx + 1, ("allergy_list", "Please specify your allergies."))

                return history, state
        # ----------------------------------------------------

        # Dynamic shopping deeper questions
        if state["flow"] == "shopping" and key == "category":
            cat = message.lower()

            # Clothing follow-up questions
            if "cloth" in cat:
                extra_qs = [
                    ("for_whom", "Who is this clothing for? (Men / Women / Kids / Baby)"),
                    ("occasion", "Occasion? (Casual / Office / Party / Wedding / Travel)"),
                    ("sizes", "Sizes or measurements?")
                ]
                state["questions"][idx+1:idx+1] = extra_qs

            # Grocery frequency
            if "grocery" in cat:
                state["questions"][idx+1:idx+1] = [
                    ("frequency", "Grocery frequency (Weekly / Monthly)?")
                ]

        # Ask the next question if available
        if state["q_index"] < len(state["questions"]):
            next_q = state["questions"][state["q_index"]][1]
            history.append({"role": "assistant", "content": next_q})
            return history, state

        # All questions answered → generate result
        history.append({"role": "assistant", "content": "Preparing your results… please wait."})

        flow = state["flow"]
        lang = state["lang"]
        answers = state["answers"]

        if flow == "diet":
            result = finalize_diet(answers, lang)
        elif flow == "shopping":
            result = finalize_shopping(answers, lang)
        else:
            result = finalize_travel(answers, lang)

        history.append({"role": "assistant", "content": result})

        # Reset but keep language
        state = {"stage": "choose_flow", "lang": lang}

        history.append({
            "role": "assistant",
            "content": f"What else can I help with in {lang}? (diet / shopping / travel)"
        })

        return history, state



    # ---------------------------
    # Fallback
    # ---------------------------
    history.append({"role": "assistant", "content": "I didn't understand. Please type diet / shopping / travel."})
    return history, state
# -------------------------
# SELF-TESTS / EVALUATION
# -------------------------
def run_self_tests():
    tests = []
    lang, intent = detect_language_and_intent("I want to lose weight and need a meal plan")
    tests.append(("Intent detection (diet)", intent == "diet"))

    l2,i2 = detect_language_and_intent("Help me make a grocery list and budget")
    tests.append(("Intent detection (shopping)", i2 == "shopping"))

    l3,i3 = detect_language_and_intent("Plan a trip to Goa from Pune")
    tests.append(("Intent detection (travel)", i3 == "travel"))

    # memory check
    try:
        memory_bank['__test'] = datetime.utcnow().isoformat()
        save_json(MEMORY_PATH, memory_bank)
        ok = "__test" in load_json(MEMORY_PATH, {})
        tests.append(("Memory persistence", ok))
    except:
        tests.append(("Memory persistence", False))

    # metrics check
    try:
        metrics['__test'] = datetime.utcnow().isoformat()
        save_json(METRICS_PATH, metrics)
        ok2 = "__test" in load_json(METRICS_PATH, {})
        tests.append(("Metrics persistence", ok2))
    except:
        tests.append(("Metrics persistence", False))

    out = []
    passed = 0
    for name, ok in tests:
        out.append(f"{name}: {'PASS' if ok else 'FAIL'}")
        if ok:
            passed += 1

    out.append(f"\n{passed}/{len(tests)} tests passed.")
    return "\n".join(out)

# -------------------------
# UI CSS (clean WhatsApp-like bubbles)
# -------------------------
custom_css = """
/* Container tweaks */
gr-chatbot::part(container) { scrollbar-width: thin !important; }
gr-chatbot::part(container)::-webkit-scrollbar { height:8px; }

/* Message bubbles */
gr-chatbot .message[user] {
    background: #DCF8C6 !important;
    color: #000 !important;
    margin-left: auto !important;
    border-radius: 16px !important;
    padding: 10px 14px !important;
    max-width: 78% !important;
    box-shadow: 0 1px 0 rgba(0,0,0,0.05);
}
gr-chatbot .message[assistant] {
    background: #F1F3F4 !important;
    color: #000 !important;
    margin-right: auto !important;
    border-radius: 16px !important;
    padding: 10px 14px !important;
    max-width: 78% !important;
    box-shadow: 0 1px 0 rgba(0,0,0,0.03);
}

/* Make text readable */
gr-chatbot .message, gr-chatbot .message * { color: #000 !important; }

/* Input & buttons */
textarea { border-radius: 10px !important; padding: 8px !important; }
button { border-radius: 8px !important; padding: 8px 12px !important; }

/* Header */
h2 { margin-bottom: 6px; }
"""

# -------------------------
# Build Gradio UI 
# -------------------------

with gr.Blocks(css=custom_css, title="AI Concierge Agent — Final") as app:

    gr.Markdown("<h2 style='text-align:center'>🌍 AI Concierge Agent — Diet • Shopping • Travel</h2>")
    gr.Markdown("<div style='text-align:center;color:gray;margin-bottom:8px;'>Select language first: English / Hindi / Marathi / Telugu</div>")

    chat = gr.Chatbot(elem_id="chatbot", label="Concierge Chat", type="messages", height=500)
    state = gr.State({"stage": "choose_language"})
    txt = gr.Textbox(show_label=False, placeholder="Type here...", lines=1)

    with gr.Row():
        send_btn = gr.Button("Send")
        clear_btn = gr.Button("Clear Chat")

    with gr.Row():
        test_btn = gr.Button("Run Self-Tests")
        metrics_btn = gr.Button("Show Metrics")
        memory_btn = gr.Button("Show Memory")

    # ---- THREE FIXED OUTPUT BOXES ----
    tests_box = gr.Textbox(
        label="Self-Test Results",
        lines=12,
        interactive=False
    )
    metrics_box = gr.Textbox(
        label="Metrics",
        lines=12,
        interactive=False
    )
    memory_box = gr.Textbox(
        label="Memory",
        lines=12,
        interactive=False
    )

    # ---------------------
    # Button Bindings
    # ---------------------

    # Send message
    send_btn.click(chat_handler, [txt, chat, state], [chat, state]).then(
        lambda: gr.update(value=""), None, txt
    )
    txt.submit(chat_handler, [txt, chat, state], [chat, state]).then(
        lambda: gr.update(value=""), None, txt
    )

    # Clear chat window only
    clear_btn.click(lambda: ([], {"stage": "choose_language"}), None, [chat, state])

    # Self Tests → writes ONLY to tests_box
    test_btn.click(
        lambda: run_self_tests(),
        None,
        tests_box
    )

    # Metrics → writes ONLY to metrics_box
    metrics_btn.click(
        lambda: json.dumps(metrics, indent=2),
        None,
        metrics_box
    )

    # Memory → writes ONLY to memory_box
    memory_btn.click(
        lambda: json.dumps(memory_bank, indent=2),
        None,
        memory_box
    )

# -------------------------
# Launch app with public share link
# -------------------------
print("Launching AI Concierge Agent UI...")
app.launch(share=True)

# -------------------------
# Final persistent save (ensure memory/metrics are saved)
# -------------------------
save_json(MEMORY_PATH, memory_bank)
save_json(METRICS_PATH, metrics)
logger.info("Memory and metrics saved at shutdown.")
