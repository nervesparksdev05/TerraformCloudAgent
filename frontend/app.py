"""
Terraform Agent Streamlit frontend.
"""
import time
from typing import Any, Dict

import streamlit as st

from api_client import TerraformAPIClient

st.set_page_config(
    page_title="Terraform Cloud Agent",
    page_icon="TCA",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
/* ── Google Font ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

/* ── Base Typography ── */
html, body, [class*="css"],
[data-testid="stAppViewContainer"],
[data-testid="stSidebar"],
.stMarkdown, .stMarkdown p, .stMarkdown span, .stMarkdown div,
.stMarkdown li, .stMarkdown ul, .stMarkdown ol,
.stCaption, label,
.stTextInput input, .stTextArea textarea,
.stSelectbox, .stMultiSelect {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    color: #0F172A;
}

/* Secondary text */
.stCaption, [data-testid="stCaptionContainer"] {
    color: #475569 !important;
}

/* ── Backgrounds ── */
.stApp {
    background-color: #F8FAFC;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background-color: #FFFFFF;
    border-right: 1px solid #E2E8F0;
}

section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] label {
    color: #0F172A;
}

/* ── Cards & Containers ── */
.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
}

.example-card,
.import-section,
.tca-card {
    background: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 6px !important;
    padding: 1rem;
}

/* Chat messages */
.stChatMessage {
    background: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 6px !important;
}

/* ── Chat Input ── */
[data-testid="stChatInput"] {
    background-color: #FFFFFF !important;
}

[data-testid="stChatInput"] textarea {
    color: #0F172A !important;
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 6px !important;
    font-family: 'Inter', sans-serif;
}

[data-testid="stChatInput"] textarea:focus {
    border-color: #2563EB !important;
    box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15) !important;
}

/* ── Code Blocks ── */
code {
    color: #1E293B !important;
    background: #F1F5F9 !important;
    padding: 0.15rem 0.35rem;
    border-radius: 4px;
    font-size: 0.875em;
}

pre {
    background: #F1F5F9 !important;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
}

pre code {
    color: #1E293B !important;
    background: transparent !important;
}

/* ── Headings ── */
h1, h2, h3, h4, h5, h6 {
    color: #0F172A !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em;
}

h1 { font-size: 1.75rem !important; }
h2 { font-size: 1.375rem !important; }
h3 { font-size: 1.125rem !important; }

/* ── Form Inputs ── */
.stTextInput > div > div > input,
.stTextArea textarea {
    color: #0F172A !important;
    caret-color: #0F172A !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 6px !important;
    transition: border-color 0.15s ease;
}

.stTextInput > div > div > input:focus,
.stTextArea textarea:focus {
    border-color: #2563EB !important;
    box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.15) !important;
}

/* ── Buttons ── */
.stButton > button {
    border-radius: 6px !important;
    font-weight: 500 !important;
    font-family: 'Inter', sans-serif !important;
    transition: background-color 0.15s ease, box-shadow 0.15s ease !important;
}

.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"] {
    background-color: #2563EB !important;
    border: none !important;
    color: #FFFFFF !important;
}

.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="stBaseButton-primary"]:hover {
    background-color: #1D4ED8 !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1) !important;
}

.stButton > button[kind="secondary"],
.stButton > button[data-testid="stBaseButton-secondary"] {
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    color: #0F172A !important;
}

.stButton > button[kind="secondary"]:hover,
.stButton > button[data-testid="stBaseButton-secondary"]:hover {
    background-color: #F1F5F9 !important;
    border-color: #CBD5E1 !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.25rem;
    border-bottom: 1px solid #E2E8F0;
}

.stTabs [data-baseweb="tab"] {
    font-family: 'Inter', sans-serif;
    font-weight: 500;
    color: #475569;
    padding: 0.5rem 1rem;
    border-radius: 6px 6px 0 0;
}

.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: #2563EB;
    border-bottom: 2px solid #2563EB;
}

/* ── Dividers ── */
hr {
    border-color: #E2E8F0 !important;
}

/* ── Metrics ── */
[data-testid="stMetricValue"] {
    color: #0F172A !important;
    font-weight: 600 !important;
}

[data-testid="stMetricLabel"] {
    color: #475569 !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
    font-weight: 500;
    color: #0F172A;
}

/* ── Welcome / Custom Sections ── */
.welcome-header {
    text-align: center;
    padding: 2rem 0 1rem;
}

.welcome-title {
    font-size: 1.75rem;
    font-weight: 600;
    color: #0F172A;
}

.welcome-subtitle {
    font-size: 1rem;
    color: #475569;
    margin-top: 0.25rem;
}

.tca-title {
    font-size: 1.125rem;
    font-weight: 600;
    color: #0F172A;
}

.tca-sub {
    font-size: 0.8125rem;
    color: #475569;
    margin-top: 0.125rem;
}

.section-title {
    font-size: 1rem;
    font-weight: 600;
    color: #0F172A;
    margin-bottom: 0.25rem;
}

.section-subtitle {
    font-size: 0.875rem;
    color: #475569;
    margin-bottom: 0.75rem;
}

</style>
""",
    unsafe_allow_html=True,
)




@st.cache_resource
def get_api_client() -> TerraformAPIClient:
    return TerraformAPIClient(base_url="http://localhost:8000")


api_client = get_api_client()


def init_state() -> None:
    defaults: Dict[str, Any] = {
        "session_id": None,
        "messages": [],
        "conversation_complete": False,
        "collected_parameters": {},
        "run_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def start_new_conversation(github_url: str = "", github_token: str = "", github_branch: str = "") -> None:
    try:
        if github_url:
            # Stage 1: Fetch README
            with st.spinner("📥 Fetching README from GitHub..."):
                result = api_client.create_conversation(provider="aws", github_url=github_url, github_token=github_token, github_branch=github_branch)
            
            # Show fetch success
            st.info("✅ README fetched successfully! Analyzing content...")
            time.sleep(0.5)  # Brief pause to show the message
        else:
            with st.spinner("Starting conversation..."):
                result = api_client.create_conversation(provider="aws", github_url=github_url, github_token=github_token, github_branch=github_branch)
        
        st.session_state.session_id = result["session_id"]
        st.session_state.messages = [{"role": "assistant", "content": result["bot_response"], "suggestions": []}]
        st.session_state.conversation_complete = False
        st.session_state.collected_parameters = {}
        st.session_state.run_id = None
        
        # Show final success indicator if GitHub URL was provided
        if github_url:
            st.success("🎉 README analysis complete!")
            st.balloons()
            
    except Exception as exc:
        st.error(f"Failed to start conversation: {exc}")


def load_session(session_id: str) -> None:
    """Load a past session into state."""
    try:
        with st.spinner("Loading session..."):
            session_data = api_client.get_conversation(session_id)
        
        st.session_state.session_id = session_id
        # Restore messages
        messages = session_data.get("messages", [])
        # Filter for UI-relevant messages only (user/assistant)
        st.session_state.messages = [
            m for m in messages if m.get("role") in ("user", "assistant")
        ]
        
        st.session_state.collected_parameters = session_data.get("collected_parameters", {})
        st.session_state.conversation_complete = session_data.get("is_complete", False)
        
        # Restore run_id if available (take the last one if multiple)
        run_ids = session_data.get("run_ids", [])
        st.session_state.run_id = run_ids[-1] if run_ids else None
        
    except Exception as exc:
        st.error(f"Failed to reload session: {exc}")



def send_user_message(user_message: str) -> None:
    if not st.session_state.session_id:
        st.error("Start a conversation first.")
        return
    st.session_state.messages.append({"role": "user", "content": user_message})
    try:
        with st.spinner("Thinking..."):
            response = api_client.send_message(
                session_id=st.session_state.session_id,
                message=user_message,
            )
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": response["bot_response"],
                "suggestions": response.get("suggestions", []),
            }
        )
        st.session_state.collected_parameters = response["collected_parameters"]
        st.session_state.conversation_complete = bool(response["is_complete"])
    except Exception as exc:
        st.error(f"Failed to send message: {exc}")
        if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
            st.session_state.messages.pop()


def generate_terraform() -> None:
    if not st.session_state.conversation_complete:
        st.warning("Complete the conversation first.")
        return
    try:
        with st.spinner("Generating Terraform..."):
            result = api_client.generate_terraform(st.session_state.session_id)
        st.session_state.run_id = result["run_id"]
        st.success(f"Terraform generated: {result['run_id'][:12]}...")
    except Exception as exc:
        st.error(f"Failed to generate Terraform: {exc}")


def _status_variant(status: str) -> str:
    if status in ("pending_approval", "planned", "reviewing"):
        return "info"
    if status in ("approved", "applying", "applied", "completed"):
        return "success"
    if status in ("failed", "destroyed"):
        return "error"
    return "warning"


def _render_status(status: str) -> None:
    variant = _status_variant(status)
    if variant == "success":
        st.success(f"Status: {status}")
    elif variant == "error":
        st.error(f"Status: {status}")
    elif variant == "warning":
        st.warning(f"Status: {status}")
    else:
        st.info(f"Status: {status}")


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown('<div class="tca-card">', unsafe_allow_html=True)
        st.markdown('<div class="tca-title">Terraform Cloud Agent</div>', unsafe_allow_html=True)
        st.markdown('<div class="tca-sub">Cloud infrastructure deployment</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.write("")

        # New Chat Button
        if st.button("New Chat", use_container_width=True, type="primary"):
            # Clear current session to show welcome screen
            st.session_state.session_id = None
            st.session_state.messages = []
            st.session_state.conversation_complete = False
            st.session_state.collected_parameters = {}
            st.session_state.run_id = None
            st.rerun()

        st.divider()

        # Session History
        st.markdown("### Recent Chats")
        sessions = api_client.get_sessions(limit=10)
        
        for sess in sessions:
            title = sess.get("title", "New Conversation")
            sid = sess.get("session_id")
            
            # Highlight current session
            is_active = (sid == st.session_state.session_id)
            
            # Create columns for session button and delete button
            col1, col2 = st.columns([6, 0.5])
            
            with col1:
                button_type = "primary" if is_active else "secondary"
                if st.button(
                    title, 
                    key=f"btn_{sid}", 
                    use_container_width=True,
                    type=button_type,
                    help=f"Session ID: {sid[:12]}..."
                ):
                    if not is_active:
                        load_session(sid)
                        st.rerun()
            
            with col2:
                if st.button("×", key=f"del_{sid}", help="Delete session"):
                    try:
                        api_client.delete_session(sid)
                        # If deleting active session, clear state
                        if is_active:
                            st.session_state.session_id = None
                            st.session_state.messages = []
                            st.session_state.conversation_complete = False
                            st.session_state.collected_parameters = {}
                            st.session_state.run_id = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to delete: {e}")

        if not sessions:
            st.caption("No history yet.")

        st.divider()

        if st.session_state.session_id:
            st.caption(f"Active: {st.session_state.session_id[:8]}...")
            if st.session_state.conversation_complete:
                st.success("Parameters Complete")
            else:
                st.info("Collecting Params")
        else:
            st.warning("No active conversation")

        if st.session_state.collected_parameters:
            with st.expander("Collected Parameters", expanded=False):
                st.json(st.session_state.collected_parameters)

        if st.session_state.run_id:
            st.caption(f"Run: {st.session_state.run_id[:12]}...")


def render_chat_tab() -> None:
    st.subheader("Conversation")
    st.caption("Answer questions naturally - no technical knowledge needed")

    if not st.session_state.session_id:
        # Minimal welcome header
        st.markdown(
            """
            <div class="welcome-header">
                <div class="welcome-title">Terraform Cloud Agent</div>
                <div class="welcome-subtitle">Simple cloud infrastructure deployment</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # GitHub Import Section
        st.markdown('<div class="import-section">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Import from GitHub</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-subtitle">Enter repository details to detect project requirements</div>', unsafe_allow_html=True)
        
        col_owner, col_repo, col_branch = st.columns([1, 1, 0.7])
        with col_owner:
            github_owner = st.text_input(
                "Owner",
                placeholder="e.g. vercel",
                help="GitHub Organization or Username",
                key="github_owner_input"
            )
            
        with col_repo:
            github_repo = st.text_input(
                "Repository",
                placeholder="e.g. next.js",
                help="Repository Name",
                key="github_repo_input"
            )

        with col_branch:
            github_branch = st.text_input(
                "Branch (Optional)",
                placeholder="main",
                help="Switch branch",
                key="github_branch_input"
            )
 
        github_token = st.text_input(
            "Personal Access Token (Optional)",
            placeholder="ghp_...",
            help="Required for private repos or to avoid rate limits",
            type="password",
            key="github_token_input"
        )
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Import from GitHub", type="primary", use_container_width=True, disabled=not (github_owner.strip() and github_repo.strip())):
                full_url = f"https://github.com/{github_owner.strip()}/{github_repo.strip()}"
                start_new_conversation(github_url=full_url, github_token=github_token.strip(), github_branch=github_branch.strip())
                st.rerun()
        
        with col2:
            if st.button("Start Fresh Chat", use_container_width=True):
                start_new_conversation()
                st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Example projects with cleaner layout
        st.markdown("---")
        st.markdown("### Example Projects")
        
        example_repos = [
            ("Next.js", "https://github.com/vercel/next.js"),
            ("Express", "https://github.com/expressjs/express"),
            ("Django", "https://github.com/django/django"),
        ]
        
        cols = st.columns(len(example_repos))
        for col, (name, url) in zip(cols, example_repos):
            with col:
                st.markdown(f'<div class="example-card">', unsafe_allow_html=True)
                if st.button(name, use_container_width=True, key=f"example_{name}"):
                    start_new_conversation(github_url=url)
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
        
        return

    for msg in st.session_state.messages:
        with st.chat_message("user" if msg["role"] == "user" else "assistant"):
            st.write(msg["content"])
            if msg["role"] == "assistant" and msg.get("suggestions"):
                st.caption("Suggestions: " + " | ".join(msg["suggestions"][:6]))

    if st.session_state.conversation_complete:
        st.success("All required parameters are collected.")
        if not st.session_state.run_id and st.button("Generate Terraform", type="primary", use_container_width=True):
            generate_terraform()
            st.rerun()
    else:
        user_input = st.chat_input("Type one message")
        if user_input and user_input.strip():
            send_user_message(user_input.strip())
            st.rerun()


def render_review_tab() -> None:
    st.subheader("Review")
    if not st.session_state.run_id:
        st.info("Generate Terraform first.")
        return

    try:
        run = api_client.get_run(st.session_state.run_id)
    except Exception as exc:
        st.error(f"Failed to load run: {exc}")
        return

    _render_status(run["status"])
    st.caption(f"Run ID: {run['run_id']}")

    if run.get("error_message"):
        st.error(run["error_message"])

    if run["status"] not in ["pending_approval", "approved", "applied", "completed", "reviewing", "planned"]:
        return

    try:
        files_payload = api_client.get_run_files(st.session_state.run_id)
        files = files_payload.get("files", {})
    except Exception as exc:
        st.error(f"Failed to load files: {exc}")
        return

    # Show all three Terraform files in tabs
    tabs = st.tabs(["main.tf", "variables.tf", "outputs.tf"])
    file_map = {
        "main.tf": files.get("main_tf", "# Not available"),
        "variables.tf": files.get("variables_tf", "# Not available"),
        "outputs.tf": files.get("outputs_tf", "# Not available"),
    }

    for tab, file_name in zip(tabs, file_map.keys()):
        with tab:
            content = file_map[file_name]
            if content and content != "# Not available":
                # Calculate line count and size
                line_count = len(content.split('\n'))
                size_bytes = len(content.encode('utf-8'))
                
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.caption(f"{line_count} lines")
                with col2:
                    st.caption(f"{size_bytes} bytes")
                with col3:
                    st.download_button(
                        "Download",
                        content,
                        file_name=file_name,
                        mime="text/plain",
                        use_container_width=True,
                        key=f"dl_{file_name}"
                    )
                
                st.code(content, language="hcl", line_numbers=True)
            else:
                st.warning(f"{file_name} is not available yet.")

    c1, c2, c3 = st.columns(3)
    with c1:
        if run["status"] in ["pending_approval", "reviewing", "planned"]:
            if st.button("Approve & Deploy", type="primary", use_container_width=True):
                try:
                    api_client.approve_run(st.session_state.run_id)
                    st.success("Deployment started.")
                    time.sleep(0.6)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Approve failed: {exc}")
    with c2:
        if run["status"] in ["pending_approval", "reviewing", "planned"]:
            if st.button("Reject", use_container_width=True):
                try:
                    api_client.reject_run(st.session_state.run_id)
                    st.warning("Run rejected.")
                    time.sleep(0.6)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Reject failed: {exc}")
    with c3:
        if run["status"] in ["applied", "completed"]:
            if st.button("Destroy", use_container_width=True):
                try:
                    api_client.destroy_run(st.session_state.run_id)
                    st.warning("Destroy started.")
                    time.sleep(0.6)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Destroy failed: {exc}")


def render_manage_tab() -> None:
    st.subheader("Manage")
    if not st.session_state.run_id:
        st.info("No active run.")
        return

    try:
        run = api_client.get_run(st.session_state.run_id)
    except Exception as exc:
        st.error(f"Failed to load run: {exc}")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Provider", str(run.get("provider", "aws")).upper())
    c2.metric("Status", str(run.get("status", "unknown")))
    c3.metric("Created", str(run.get("created_at", "n/a"))[:19])

    st.markdown("### Request Changes")
    edit_message = st.text_area(
        "Describe changes",
        placeholder="Example: change instance type to t3.medium and enable autoscaling",
        height=110,
        label_visibility="collapsed",
    )
    if st.button("Submit Change Request", use_container_width=True):
        if not edit_message.strip():
            st.warning("Enter requested changes first.")
        else:
            try:
                api_client.edit_run_message(st.session_state.run_id, edit_message.strip())
                st.success("Change request submitted.")
                time.sleep(0.6)
                st.rerun()
            except Exception as exc:
                st.error(f"Change request failed: {exc}")

    st.markdown("### Ask About This Run")
    question = st.text_input(
        "Ask a question",
        placeholder="Example: what ports are exposed?",
        label_visibility="collapsed",
    )
    if st.button("Ask", use_container_width=True) and question.strip():
        try:
            response = api_client.chat_about_run(st.session_state.run_id, question.strip())
            st.info(response.get("response", "No response"))
        except Exception as exc:
            st.error(f"Run chat failed: {exc}")


def main() -> None:
    init_state()
    render_sidebar()
    tab_chat, tab_review, tab_manage = st.tabs(["Chat", "Review", "Manage"])
    with tab_chat:
        render_chat_tab()
    with tab_review:
        render_review_tab()
    with tab_manage:
        render_manage_tab()


if __name__ == "__main__":
    main()
