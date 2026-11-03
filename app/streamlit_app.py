"""Chat UI for the Study Assistant (run with: streamlit run app/streamlit_app.py).

Streamlit re-runs this whole script on every interaction, so anything that must
survive (chat history, the session id) lives in st.session_state.
"""
import uuid

import streamlit as st
import streamlit.components.v1 as components

import agent_client
import voice

st.set_page_config(page_title="Study Assistant", page_icon="📚")
st.title("📚 Study Assistant")

try:
    config = agent_client.load_config()
except agent_client.ConfigError as error:
    st.error(str(error))
    st.stop()

# A session id lets the agent remember the conversation; "New conversation" makes a fresh one.
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []

VOICES = ["Ruth", "Matthew", "Danielle", "Joanna", "Stephen"]  # natural-sounding US English Polly voices

with st.sidebar:
    student_id = st.text_input("Student ID", value="me")
    show_trace = st.toggle("Show agent reasoning", value=False)
    speak_replies = st.toggle("Speak replies (Polly)", value=False)
    voice_name = config.get("polly_voice", voice.DEFAULT_VOICE)
    if speak_replies:
        voice_name = st.selectbox("Voice", VOICES, index=VOICES.index(voice_name) if voice_name in VOICES else 0)
    if st.button("New conversation"):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()


# The little iframes that carry audio are invisible helpers: hide them (hidden iframes still run their script).
st.html("<style>[data-testid='stElementContainer']:has(> iframe), iframe { display: none; }</style>")


def run_script(html: str) -> None:
    """Run a small invisible script in the page. (st.iframe replaces the older components.html.)"""
    if hasattr(st, "iframe"):
        st.iframe(html, height=1)
    else:
        components.html(html, height=0)


def play(clips: list[bytes]) -> None:
    """Hand audio clips to the browser, which queues them and plays them in order."""
    if clips:
        run_script(voice.player_html(clips))


def render_trace(steps: list[dict]) -> None:
    with st.expander("Agent reasoning"):
        for step in steps:
            if step["kind"] == "rationale":
                st.markdown(f"💭 {step['text']}")
            elif step["kind"] == "tool_call":
                st.markdown(f"🔧 **{step['function']}**")
                st.json(step["parameters"])
            else:
                st.code(step["text"])


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("trace"):
            render_trace(message["trace"])

if prompt := st.chat_input("Ask about your courses, grades or tasks"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        try:
            speaker = None
            if speak_replies:
                run_script(voice.stop_html())  # stop the previous answer if it is still being read
                speaker = voice.StreamingSpeaker(voice_name, config["region"], config.get("polly_engine", voice.DEFAULT_ENGINE))
            status = st.empty()
            status.caption("Thinking...")
            steps = []

            def words():
                """Pass the answer's words to Streamlit as they arrive; collect trace steps and speech on the side."""
                for event in agent_client.stream_agent(prompt, st.session_state.session_id, student_id):
                    if event["type"] == "working":
                        status.caption("🔧 Using " + ", ".join(event["tools"]) + "...")
                    elif event["type"] == "step":
                        steps.append(event["step"])
                    elif event["type"] == "text":
                        status.empty()
                        if speaker:
                            play(speaker.feed(event["text"]))
                        yield event["text"]

            reply = st.write_stream(words())
            status.empty()
            if speaker:
                for clip in speaker.finish():  # each clip is played as soon as it is ready
                    play([clip])
                if speaker.error:
                    st.warning(f"I couldn't speak that reply: {speaker.error}")
            if show_trace and steps:
                render_trace(steps)
            st.session_state.messages.append({"role": "assistant", "content": reply, "trace": steps if show_trace else []})
        except Exception as error:  # noqa: BLE001 - show every failure as friendly advice
            st.error(agent_client.friendly_error(error))
