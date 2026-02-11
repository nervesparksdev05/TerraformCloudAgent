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
.block-container {padding-top: 1.5rem;}
.tca-card {
  background-color: #262730;
  border: 1px solid #3f3f46;
  border-radius: 14px;
  padding: 0.9rem 1rem;
}
.tca-title {font-weight: 700; color: #fafafa; margin-bottom: 0.15rem;}
.tca-sub {color: #a1a1aa; font-size: 0.9rem;}
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


def start_new_conversation() -> None:
    try:
        with st.spinner("Starting conversation..."):
            result = api_client.create_conversation(provider="aws")
        st.session_state.session_id = result["session_id"]
        st.session_state.messages = [{"role": "assistant", "content": result["bot_response"], "suggestions": []}]
        st.session_state.conversation_complete = False
        st.session_state.collected_parameters = {}
        st.session_state.run_id = None
    except Exception as exc:
        st.error(f"Failed to start conversation: {exc}")


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
        st.markdown('<div class="tca-sub">Your friendly cloud infrastructure buddy 👋</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.write("")

        if st.session_state.session_id:
            st.success("Conversation active")
            st.caption(f"Session: {st.session_state.session_id[:12]}...")
            if st.session_state.conversation_complete:
                st.success("Parameters complete")
            else:
                st.info("Collecting parameters")
            if st.button("New Conversation", use_container_width=True):
                start_new_conversation()
                st.rerun()
        else:
            st.warning("No active conversation")
            if st.button("Start Conversation", type="primary", use_container_width=True):
                start_new_conversation()
                st.rerun()

        if st.session_state.collected_parameters:
            with st.expander("Collected Parameters", expanded=False):
                st.json(st.session_state.collected_parameters)

        if st.session_state.run_id:
            st.caption(f"Run: {st.session_state.run_id[:12]}...")


def render_chat_tab() -> None:
    st.subheader("Conversation")
    st.caption("Chat with your friendly cloud expert. Just answer naturally - no technical knowledge needed!")

    if not st.session_state.session_id:
        st.info("Start a conversation from the sidebar.")
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
    tabs = st.tabs(["📄 main.tf", "⚙️ variables.tf", "📤 outputs.tf"])
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
                    st.caption(f"📊 {line_count} lines")
                with col2:
                    st.caption(f"💾 {size_bytes} bytes")
                with col3:
                    st.download_button(
                        "⬇️ Download",
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
