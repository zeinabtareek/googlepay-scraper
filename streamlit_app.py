import streamlit as st
import subprocess
import sys
import os
import time
import threading
import queue
import contextlib
import io
import tempfile
import traceback
from datetime import datetime

# Set page config
st.set_page_config(
    page_title="Google Pay Scraper Professional",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS styling (unchanged)
st.markdown("""
<style>
    /* Your existing CSS styles remain unchanged */
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'forms' not in st.session_state:
    st.session_state.forms = [{'id': 1}]
if 'form_counter' not in st.session_state:
    st.session_state.form_counter = 1
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'scraper_running' not in st.session_state:
    st.session_state.scraper_running = False
if 'scraper_status' not in st.session_state:
    st.session_state.scraper_status = ""

# Define scraper functions (unchanged)
def run_scraper_in_process(email, password, pages, auto_bypass):
    """Run scraper in-process and return results"""
    logs = []
    success = False
    try:
        logs.append("🚀 Starting Google Pay Scraper...")
        logs.append(f"📧 Email: {email}")
        logs.append(f"🔐 Password: {'*' * len(password)}")
        logs.append(f"📄 Pages: {pages}")
        logs.append(f"🤖 Auto-bypass: {auto_bypass}")
        logs.append("-" * 50)
        try:
            import scraping
            if hasattr(scraping, 'run_scraper'):
                output_buffer = io.StringIO()
                with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(output_buffer):
                    try:
                        scraping.run_scraper(email, password, pages, auto_bypass)
                        logs.append("✅ Scraper completed successfully!")
                        success = True
                    except SystemExit as se:
                        code = getattr(se, 'code', 1) or 0
                        if code == 0:
                            logs.append("✅ Scraper completed!")
                            success = True
                        else:
                            logs.append(f"❌ Exit code: {code}")
                    except Exception as e:
                        logs.append(f"❌ Error: {str(e)}")
                output = output_buffer.getvalue()
                if output:
                    for line in output.strip().split('\n'):
                        if line.strip():
                            logs.append(line)
            else:
                logs.append("⚠️ Scraper function not available.")
        except ImportError:
            logs.append("⚠️ Scraper module not available.")
        except Exception as e:
            logs.append(f"❌ Import error: {str(e)}")
    except Exception as e:
        logs.append(f"💥 Unexpected error: {str(e)}")
    return success, logs

def run_scraper_subprocess(email, password, pages, auto_bypass):
    """Run scraper as subprocess"""
    logs = []
    success = False
    try:
        if not os.path.exists("scraping.py"):
            logs.append("⚠️ Scraper file not found.")
            return False, logs
        cmd = [
            sys.executable, "scraping.py",
            "--email", email,
            "--password", password,
            "--pages", str(pages)
        ]
        if auto_bypass:
            cmd.append("--auto-bypass")
        logs.append("🚀 Starting scraper subprocess...")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                logs.append(line.strip())
        exit_code = process.returncode
        if exit_code == 0:
            logs.append("✅ Scraper completed successfully!")
            success = True
        else:
            logs.append(f"❌ Scraper failed with exit code: {exit_code}")
    except Exception as e:
        logs.append(f"💥 Subprocess error: {str(e)}")
    return success, logs

# Header
st.markdown("""
<div class="header-container">
    <h1 class="main-title">🚀 Welcome Again</h1>
    <p class="subtitle">Professional Google Pay Data Extraction Tool</p>
</div>
""", unsafe_allow_html=True)

# Add form management
col1, col2 = st.columns([3, 1])
with col2:
    add_account = st.button("➕ Add Account", type="secondary", key="add_account")
    if add_account:
        # Increment form counter and add new form
        st.session_state.form_counter += 1
        st.session_state.forms.append({'id': st.session_state.form_counter})

# Display forms
for form in st.session_state.forms[:]:  # Create a copy to avoid modification issues
    st.markdown(f"""
    <div class="form-container">
        <div class="form-title">📝 Account Configuration #{form['id']}</div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns([4, 1])
    
    with col1:
        with st.container():
            # Email input
            email = st.text_input(
                "📧 Email Address:",
                placeholder="Enter your email address (e.g., user@gmail.com)",
                key=f"email_{form['id']}"
            )
            
            # Password input
            password = st.text_input(
                "🔐 Password:",
                type="password",
                placeholder="Enter your password",
                key=f"password_{form['id']}"
            )
            
            # Pages and auto-bypass
            col_pages, col_bypass = st.columns([1, 2])
            
            with col_pages:
                pages = st.number_input(
                    "📄 Number of Pages:",
                    min_value=1,
                    value=1,
                    key=f"pages_{form['id']}"
                )
            
            with col_bypass:
                auto_bypass = st.checkbox(
                    "🤖 Enable Auto-bypass",
                    value=True,
                    help="Automatically handle passkey prompts",
                    key=f"auto_bypass_{form['id']}"
                )
            
            # Submit button
            if st.button(f"🚀 Start Scraping", key=f"submit_{form['id']}", type="primary"):
                if not email or not password:
                    st.error("⚠️ Please enter both email and password!")
                else:
                    st.session_state.scraper_running = True
                    st.session_state.logs = []
                    st.session_state.scraper_status = "running"
                    
                    with st.spinner("🔄 Scraper is running..."):
                        success, logs = run_scraper_in_process(email, password, pages, auto_bypass)
                        if not success and not logs:
                            success, logs = run_scraper_subprocess(email, password, pages, auto_bypass)
                    
                    st.session_state.logs = logs
                    st.session_state.scraper_running = False
                    st.session_state.scraper_status = "success" if success else "error"
                    st.rerun()
    
    with col2:
        if len(st.session_state.forms) > 1:
            if st.button(f"🗑️ Remove", key=f"remove_{form['id']}", type="secondary"):
                st.session_state.forms = [f for f in st.session_state.forms if f['id'] != form['id']]

    st.markdown("---")

# Display logs and status
if st.session_state.logs or st.session_state.scraper_running:
    st.markdown("## 📊 Scraper Status")
    
    # Status indicator
    if st.session_state.scraper_running:
        st.markdown('<div class="status-running">🔄 Scraper is running...</div>', unsafe_allow_html=True)
    elif st.session_state.scraper_status == "success":
        st.markdown('<div class="status-success">✅ Completed successfully</div>', unsafe_allow_html=True)
    elif st.session_state.scraper_status == "error":
        st.markdown('<div class="status-error">❌ Process failed</div>', unsafe_allow_html=True)
    
    # Logs display
    if st.session_state.logs:
        st.markdown("### 📝 Live Logs")
        log_text = "\n".join(st.session_state.logs)
        st.markdown(f'<div class="log-container">{log_text.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
        
        # Clear logs button
        if st.button("🗑️ Clear Logs"):
            st.session_state.logs = []
            st.session_state.scraper_status = ""
            st.rerun()

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #bdc3c7; margin: 20px 0;">
    <p>🚀 Google Pay Scraper Professional Edition v2.0</p>
    <p>Built with Streamlit • Secure • Professional</p>
</div>
""", unsafe_allow_html=True)
