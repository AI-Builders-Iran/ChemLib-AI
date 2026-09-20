from __future__ import annotations

import requests
import streamlit as st


API_URL = "http://127.0.0.1:8000"


st.set_page_config(
    page_title="Chemistry AI",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------- Styling ----------
st.markdown(
    """
    <style>
        /* Main background */
        .stApp {
            background: #f7f8fa;
        }

        /* Sidebar */
        section[data-testid="stSidebar"] {
            background: #ffffff;
            border-right: 1px solid #e6e8ec;
        }

        section[data-testid="stSidebar"] > div {
            padding-top: 1.5rem;
        }

        /* Hide Streamlit chrome */
        #MainMenu, footer {
            visibility: hidden;
        }

        /* Header */
        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 1.5rem;
        }

        .brand-icon {
            width: 42px;
            height: 42px;
            border-radius: 12px;
            background: #111827;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
        }

        .brand-title {
            font-size: 24px;
            font-weight: 700;
            color: #111827;
            margin: 0;
        }

        .brand-subtitle {
            color: #6b7280;
            font-size: 13px;
            margin: 2px 0 0;
        }

        /* Chat area */
        .chat-container {
            max-width: 900px;
            margin: 0 auto;
        }

        .welcome {
            text-align: center;
            padding: 10vh 20px 5vh;
        }

        .welcome-icon {
            font-size: 48px;
            margin-bottom: 10px;
        }

        .welcome h1 {
            color: #111827;
            font-size: 32px;
            margin-bottom: 8px;
        }

        .welcome p {
            color: #6b7280;
            font-size: 15px;
        }

        /* History items */
        .history-title {
            color: #6b7280;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            margin: 20px 0 8px;
        }

        /* Upload page */
        .upload-card {
            max-width: 850px;
            margin: 40px auto;
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 18px;
            padding: 42px;
            text-align: center;
        }

        .upload-card h1 {
            margin-bottom: 8px;
            color: #111827;
        }

        .upload-card p {
            color: #6b7280;
        }

        /* Buttons */
        div.stButton > button {
            border-radius: 10px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------- Session state ----------
if "messages" not in st.session_state:
    st.session_state.messages = []

if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []

if "api_key" not in st.session_state:
    st.session_state.api_key = ""


def send_question(question: str, uploaded_file=None) -> str:
    """
    Calls the FastAPI backend when available.
    The optional API key is preserved as a user input and passed
    through the Authorization header.
    """
    headers = {}
    if st.session_state.api_key.strip():
        headers["Authorization"] = f"Bearer {st.session_state.api_key.strip()}"

    try:
        response = requests.post(
            f"{API_URL}/chat",
            json={"question": question},
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("answer", "پاسخی دریافت نشد.")
    except requests.RequestException:
        return (
            "این پاسخ نمایشی است. رابط کاربری Streamlit آماده است، "
            "اما FastAPI هنوز به سرویس واقعی RAG متصل نشده است."
        )


# ---------- Sidebar ----------
with st.sidebar:
    st.markdown(
        """
        <div class="brand">
            <div class="brand-icon">🧪</div>
            <div>
                <div class="brand-title">Chemistry AI</div>
                <div class="brand-subtitle">Scientific document assistant</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="history-title">Chat history</div>', unsafe_allow_html=True)

    previous_questions = [
        message["content"]
        for message in st.session_state.messages
        if message["role"] == "user"
    ]

    if not previous_questions:
        st.caption("No previous questions yet.")
    else:
        for i, question in enumerate(reversed(previous_questions)):
            st.caption(f"{i + 1}. {question[:55]}")

    st.divider()

    # Keep API key as an input because some project/demo configurations
    # provide the key directly from Streamlit.
    st.text_input(
        "API Key",
        type="password",
        key="api_key",
        placeholder="Enter API key if required",
        help="Optional. Used when the backend requires a key.",
    )

    st.caption("Chemistry Library RAG")
    st.caption("Backend: FastAPI")


# ---------- Main ----------
st.markdown('<div class="chat-container">', unsafe_allow_html=True)

chat_tab, uploader_tab = st.tabs(["💬 Chat", "📄 Uploader"])


# =========================
# CHAT
# =========================
with chat_tab:
    messages = st.session_state.messages

    if not messages:
        st.markdown(
            """
            <div class="welcome">
                <div class="welcome-icon">🧪</div>
                <h1>How can I help you?</h1>
                <p>
                    Ask a chemistry question or attach a document
                    to work with your scientific library.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Current conversation
    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            if message.get("file"):
                st.caption(f"📎 {message['file']}")

    # Small attachment area above the composer
    attached_file = st.file_uploader(
        "＋ Attach a document",
        type=["pdf", "txt", "docx"],
        key="chat_attachment",
        label_visibility="collapsed",
    )

    question = st.chat_input("Ask a chemistry question...")

    if question:
        file_name = attached_file.name if attached_file else None

        messages.append(
            {
                "role": "user",
                "content": question,
                "file": file_name,
            }
        )

        answer = send_question(question, attached_file)

        messages.append(
            {
                "role": "assistant",
                "content": answer,
            }
        )

        st.rerun()


# =========================
# UPLOADER
# =========================
with uploader_tab:
    st.markdown(
        """
        <div class="upload-card">
            <div style="font-size: 48px;">📄</div>
            <h1>Upload documents</h1>
            <p>
                Upload chemistry books, papers, notes, or other
                supported documents to add them to the library.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    files = st.file_uploader(
        "Choose documents",
        type=["pdf", "txt", "docx"],
        accept_multiple_files=True,
        key="library_uploader",
    )

    if files:
        st.session_state.uploaded_files = files

        st.subheader("Selected documents")

        for file in files:
            col1, col2 = st.columns([5, 1])
            with col1:
                st.write(f"📄 **{file.name}**")
            with col2:
                st.caption(f"{file.size / 1024:.1f} KB")

        if st.button("Upload to library", type="primary", use_container_width=True):
            st.success(
                "Documents selected successfully. "
                "The real ingestion/indexing pipeline will be connected later."
            )

st.markdown("</div>", unsafe_allow_html=True)
