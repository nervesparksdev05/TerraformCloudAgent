"""
Terraform Cloud Agent - Premium B&W Experience (Tailwind v4)
"""
import time
import json
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

import streamlit as st
from api_client import TerraformAPIClient

# Page configuration
st.set_page_config(
    page_title="Terraform Cloud Agent",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- Tailwind v4 & Custom Styling ---
st.markdown(
    """
    <script src="https://unpkg.com/@tailwindcss/browser@4"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        
        :root {
            --st-background-color: #0F172A; /* Slate-900 */
            --st-secondary-background-color: #1E293B; /* Slate-800 */
            --st-text-color: #F8FAFC; /* Slate-50 */
        }

        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif !important;
            color: #F8FAFC !important;
        }

        /* Hide Streamlit elements for a cleaner look */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}

        .glass-card {
            background: rgba(30, 41, 59, 0.7); /* Slate-800 with opacity */
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 2.5rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        }

        /* Button Styling */
        .stButton button {
            background-color: #F8FAFC !important;
            color: #0F172A !important;
            border-radius: 8px !important;
            border: none !important;
            font-weight: 600 !important;
            letter-spacing: -0.01em !important;
            padding: 0.6rem 1.2rem !important;
            transition: all 0.2s ease !important;
        }
        .stButton button:hover {
            background-color: #E2E8F0 !important; /* Slate-200 */
            transform: translateY(-1px);
            box-shadow: 0 10px 15px -3px rgba(255, 255, 255, 0.1);
        }
        
        /* Input Styling */
        .stTextInput input {
            background-color: rgba(15, 23, 42, 0.6) !important; /* Slate-900 with opacity */
            color: #F8FAFC !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            border-radius: 8px !important;
            padding: 0.6rem 1rem !important;
        }
        .stTextInput input:focus {
            border-color: #F8FAFC !important;
            box-shadow: 0 0 0 2px rgba(248, 250, 252, 0.1) !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- API Client ---
@st.cache_resource
def get_api_client() -> TerraformAPIClient:
    return TerraformAPIClient(base_url="http://localhost:8000")

api_client = get_api_client()

# --- App State ---
def init_state() -> None:
    defaults: Dict[str, Any] = {
        "page": "CONNECT",  # CONNECT, DISCOVERY, SUMMARY, REFINE, DEPLOY
        "session_id": None,
        "github_url": "",
        "repo_name": "",
        "messages": [],
        "collected_parameters": {},
        "is_complete": False,
        "run_id": None,
        "terraform_files": {},
        "current_step": 1,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def set_page(page: str):
    st.session_state.page = page
    st.rerun()

# --- Logic Actions ---
def start_session(github_url: str, token: str = ""):
    try:
        with st.spinner("Connecting to repository..."):
            result = api_client.create_conversation(github_url, github_token=token)
            st.session_state.session_id = result["session_id"]
            st.session_state.github_url = github_url
            st.session_state.repo_name = github_url.split("/")[-1].replace(".git", "")
            
            # Auto-analyze to get discovery started
            analysis = api_client.analyze_readme(result["session_id"])
            st.session_state.messages = [{"role": "assistant", "content": analysis["bot_response"]}]
            
            set_page("DISCOVERY")
    except Exception as e:
        st.error(f"Connection failed: {e}")

def send_chat(msg: str):
    if not st.session_state.session_id: return
    st.session_state.messages.append({"role": "user", "content": msg})
    try:
        with st.spinner("Analyzing architecturally..."):
            resp = api_client.send_message(st.session_state.session_id, msg)
            st.session_state.messages.append({"role": "assistant", "content": resp["bot_response"]})
            st.session_state.is_complete = resp.get("is_complete", False)
            st.session_state.collected_parameters = resp.get("collected_parameters", {})
            if st.session_state.is_complete:
                # If complete, let's pre-generate the summary
                generate_code()
    except Exception as e:
        st.error(f"Chat error: {e}")

def generate_code():
    try:
        with st.spinner("Forging Terraform infrastructure..."):
            resp = api_client.generate_terraform(st.session_state.session_id)
            st.session_state.run_id = resp["run_id"]
            files_resp = api_client.get_run_files(resp["run_id"])
            st.session_state.terraform_files = files_resp.get("files", {})
            set_page("SUMMARY")
    except Exception as e:
        st.error(f"Generation error: {e}")

# --- Pages ---

def render_connect():
    st.markdown('<div class="flex flex-col items-center justify-center min-h-[70vh]">', unsafe_allow_html=True)
    
    # Hero
    st.markdown("""
        <div class="text-center mb-12">
            <h1 class="text-6xl font-bold tracking-tight text-white mb-4">Terraform Cloud Agent</h1>
            <p class="text-gray-400 text-xl max-w-2xl mx-auto">
                The most intelligent way to deploy GitHub repositories. <br/>
                Analyze. Architect. Automate.
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    # Input Card
    with st.container():
        st.markdown('<div class="glass-card w-full max-w-2xl mx-auto">', unsafe_allow_html=True)
        repo_url = st.text_input("GitHub Repository URL", placeholder="https://github.com/org/repo")
        repo_name_override = st.text_input("Repository Name (Optional)", placeholder="My Project")
        token = st.text_input("Access Token (Optional)", type="password", placeholder="ghp_...")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("Initialize Deployment", use_container_width=True):
                if repo_url:
                    if repo_name_override:
                        st.session_state.repo_name = repo_name_override
                    start_session(repo_url, token)
                else:
                    st.warning("Please enter a valid GitHub URL.")
        st.markdown('</div>', unsafe_allow_html=True)

    # Recent Sessions
    st.markdown('<div class="mt-16 w-full max-w-4xl mx-auto">', unsafe_allow_html=True)
    st.markdown('<h3 class="text-white text-lg font-semibold mb-6 border-b border-white/10 pb-2">Recent Sessions</h3>', unsafe_allow_html=True)
    try:
        sessions = api_client.get_sessions(limit=3)
        if sessions:
            cols = st.columns(3)
            for i, s in enumerate(sessions):
                with cols[i]:
                    st.markdown(f"""
                        <div class="glass-card bg-white/5 border-white/5 p-4 h-full">
                            <div class="text-sm text-gray-400 mb-1">{s['session_id'][:8]}</div>
                            <div class="text-white font-medium truncate">{s['github_url'].split('/')[-1]}</div>
                            <div class="mt-4 text-xs {'text-green-400' if s.get('is_complete') else 'text-yellow-400'}">
                                {'● Ready' if s.get('is_complete') else '● In Progress'}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    if st.button("Resume", key=f"res_{s['session_id']}", use_container_width=True):
                        st.session_state.session_id = s['session_id']
                        st.session_state.github_url = s['github_url']
                        st.session_state.repo_name = s['github_url'].split('/')[-1]
                        set_page("DISCOVERY")
        else:
            st.caption("No recent deployments found.")
    except:
        st.caption("Ready to start something new.")
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

def render_discovery():
    # Progress Header
    st.markdown(f"""
        <div class="flex items-center justify-between mb-8 border-b border-white/10 pb-4">
            <div>
                <h2 class="text-2xl font-bold text-white tracking-tight">{st.session_state.repo_name}</h2>
                <div class="text-gray-400 text-sm">Step 2: Architecture Discovery & Logic Gathering</div>
            </div>
            <div class="text-right">
                <div class="text-xs text-gray-500 uppercase tracking-widest">Architect</div>
                <div class="text-white font-semibold">DevOps Friend GPT</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    col_chat, col_meta = st.columns([2, 1])

    with col_chat:
        st.markdown('<div class="glass-card min-h-[500px] flex flex-col justify-between p-4">', unsafe_allow_html=True)
        # Chat container
        chat_placeholder = st.container()
        with chat_placeholder:
            for m in st.session_state.messages:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])
        
        # Spacer
        st.write("")
        
        # User input
        if not st.session_state.is_complete:
            query = st.chat_input("Explain your deployment constraints...")
            # Only rerun if query was actually sent
            if query:
                send_chat(query)
                st.rerun()
        else:
            st.success("Configuration finalized. Proceeding to Summary.")
            if st.button("View Infrastructure Draft"):
                set_page("SUMMARY")
        st.markdown('</div>', unsafe_allow_html=True)

    with col_meta:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown('<h4 class="text-white font-bold mb-4">Detected Model</h4>', unsafe_allow_html=True)
        if st.session_state.collected_parameters:
            for k, v in st.session_state.collected_parameters.items():
                if isinstance(v, list): v = ", ".join(v)
                st.markdown(f"""
                    <div class="mb-3">
                        <div class="text-xs text-gray-500 uppercase">{k.replace("_", " ")}</div>
                        <div class="text-white font-medium">{v}</div>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("Discovery ongoing...")
        st.markdown('</div>', unsafe_allow_html=True)

def render_summary():
    st.markdown("""
        <div class="mb-8">
            <h2 class="text-3xl font-bold text-white leading-tight">Infrastructure Blueprint</h2>
            <p class="text-gray-400">Review the generated Terraform manifest for your workload.</p>
        </div>
    """, unsafe_allow_html=True)

    files = st.session_state.terraform_files
    if not files:
        st.warning("No code generated yet.")
        if st.button("Regenerate"): generate_code()
        return

    col_files, col_actions = st.columns([2, 1])

    with col_files:
        st.markdown('<div class="glass-card p-0 overflow-hidden">', unsafe_allow_html=True)
        tabs = st.tabs([f"📄 {fn}" for fn in files.keys()])
        for i, (fn, content) in enumerate(files.items()):
            with tabs[i]:
                st.code(content, language="hcl", line_numbers=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col_actions:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown('<h4 class="text-white font-bold mb-6">Workflow Selection</h4>', unsafe_allow_html=True)
        
        if st.button("✏️ Refine & Edit Manually", use_container_width=True):
            set_page("REFINE")
            
        st.write("")
        if st.button("🚀 Push to Cloud (Deploy)", type="primary", use_container_width=True):
            api_client.approve_run(st.session_state.run_id)
            set_page("DEPLOY")
            
        st.markdown('<div class="mt-8 border-t border-white/10 pt-4">', unsafe_allow_html=True)
        st.caption("Summary of resources:")
        # Simple counts
        res_count = len(re.findall(r'resource\s+"', files.get("main.tf", "")))
        st.markdown(f"**{res_count}** Cloud Resources detected.")
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

def render_refine():
    st.markdown("""
        <div class="mb-8">
            <h2 class="text-3xl font-bold text-white">Refinement Lab</h2>
            <p class="text-gray-400">Modify the HCL or prompt the agent to adjust the architecture.</p>
        </div>
    """, unsafe_allow_html=True)

    col_edit, col_chat = st.columns([1, 1])

    with col_edit:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.write("Manual HCL Override")
        files = st.session_state.terraform_files
        editing_file = st.selectbox("Select file to edit", list(files.keys()))
        new_content = st.text_area("HCL Content", value=files.get(editing_file), height=400)
        if st.button("Save Changes"):
            st.session_state.terraform_files[editing_file] = new_content
            st.success("File updated localy.")
        st.markdown('</div>', unsafe_allow_html=True)

    with col_chat:
        st.markdown('<div class="glass-card min-h-[500px] flex flex-col justify-between p-4">', unsafe_allow_html=True)
        st.write("Chat-based Adjustment")
        edit_msg = st.text_area("What should I change?", placeholder="e.g. 'Add a backup policy', 'Switch to t4g instances'...")
        if st.button("Apply AI Refinement", type="primary"):
            try:
                with st.spinner("Adjusting architecture..."):
                    resp = api_client.edit_run_message(st.session_state.run_id, edit_msg)
                    st.info(f"Agent: {resp['bot_response']}")
                    # Re-fetch files
                    files_resp = api_client.get_run_files(st.session_state.run_id)
                    st.session_state.terraform_files = files_resp.get("files", {})
                    st.rerun()
            except Exception as e:
                st.error(e)
        
        st.divider()
        if st.button("← Back to Review"): set_page("SUMMARY")
        st.markdown('</div>', unsafe_allow_html=True)

def render_deploy():
    st.markdown("""
        <div class="mb-12 text-center">
            <h2 class="text-4xl font-bold text-white">Deployment Control Tower</h2>
            <p class="text-gray-400">Orchestrating infrastructure across your cloud provider.</p>
        </div>
    """, unsafe_allow_html=True)

    try:
        run = api_client.get_run(st.session_state.run_id)
        status = run.get("status", "pending")
        
        st.markdown(f"""
            <div class="glass-card max-w-4xl mx-auto text-center py-12">
                <div class="text-sm uppercase tracking-[0.2em] text-gray-500 mb-2">Current Operation Status</div>
                <div class="text-6xl font-black text-white mb-6">
                    {status.upper()}
                </div>
                <div class="flex justify-center gap-4">
                    <div class="px-4 py-2 bg-white/5 rounded-full text-xs text-gray-300">Provider: AWS</div>
                    <div class="px-4 py-2 bg-white/5 rounded-full text-xs text-gray-300">Region: us-east-1</div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="mt-8 glass-card max-w-4xl mx-auto">', unsafe_allow_html=True)
        st.subheader("Action History & Logs")
        if run.get("error"):
            st.error(run["error"])
        else:
            st.code("Plan phase completed.\nApply phase in progress...\nOutputs will appear here.", language="text")
        
        col1, col2 = st.columns(2)
        with col1:
             if st.button("Refresh Status"): st.rerun()
        with col2:
            if status in ["completed", "applied"]:
                if st.button("Destroy Environment", type="secondary"):
                    api_client.destroy_run(st.session_state.run_id)
                    st.rerun()
        
        if st.button("Return Home"):
            st.session_state.clear()
            set_page("CONNECT")
        st.markdown('</div>', unsafe_allow_html=True)

    except Exception as e:
        st.error(e)

# --- Routing ---
def main():
    init_state()
    
    # Simple navigation bar for non-CONNECT pages
    if st.session_state.page != "CONNECT":
        st.markdown(f"""
            <div class="flex items-center gap-8 py-4 mb-12 border-b border-white/5">
                <div class="text-white font-black text-xl cursor-pointer" onclick="window.location.reload()">TCA</div>
                <div class="flex gap-4">
                    <span class="text-sm {'text-white font-bold' if st.session_state.page == 'DISCOVERY' else 'text-gray-500'}">Discovery</span>
                    <span class="text-sm text-gray-800">/</span>
                    <span class="text-sm {'text-white font-bold' if st.session_state.page == 'SUMMARY' else 'text-gray-500'}">Review</span>
                    <span class="text-sm text-gray-800">/</span>
                    <span class="text-sm {'text-white font-bold' if st.session_state.page == 'REFINE' else 'text-gray-500'}">Refine</span>
                    <span class="text-sm text-gray-800">/</span>
                    <span class="text-sm {'text-white font-bold' if st.session_state.page == 'DEPLOY' else 'text-gray-500'}">Deploy</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

    if st.session_state.page == "CONNECT":
        render_connect()
    elif st.session_state.page == "DISCOVERY":
        render_discovery()
    elif st.session_state.page == "SUMMARY":
        render_summary()
    elif st.session_state.page == "REFINE":
        render_refine()
    elif st.session_state.page == "DEPLOY":
        render_deploy()

if __name__ == "__main__":
    main()
