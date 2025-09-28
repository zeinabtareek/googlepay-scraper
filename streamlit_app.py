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

# Custom CSS styling
st.markdown("""
<style>
    /* Main background */
    .main {
        background: linear-gradient(135deg, #2c3e50 0%, #34495e 50%, #2c3e50 100%);
        color: white;
    }
    
    /* Header styling */
    .header-container {
        background: linear-gradient(90deg, rgba(52, 152, 219, 0.2) 0%, rgba(155, 89, 182, 0.2) 50%, rgba(52, 152, 219, 0.2) 100%);
        border: 2px solid rgba(52, 152, 219, 0.5);
        border-radius: 15px;
        padding: 30px;
        margin: 20px 0;
        text-align: center;
    }
    
    .main-title {
        background: linear-gradient(90deg, #3498db 0%, #9b59b6 50%, #3498db 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.5rem;
        font-weight: bold;
        margin: 10px 0;
    }
    
    .subtitle {
        color: #bdc3c7;
        font-size: 1.2rem;
        font-style: italic;
        margin: 10px 0;
    }
    
    /* Form styling */
    .form-container {
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.95) 0%, rgba(248, 249, 250, 0.95) 100%);
        border: 2px solid #3498db;
        border-radius: 15px;
        padding: 25px;
        margin: 20px 0;
        color: #2c3e50;
    }
    
    .form-title {
        color: #3498db;
        font-size: 1.5rem;
        font-weight: bold;
        margin-bottom: 20px;
        text-align: center;
        background-color: rgba(52, 152, 219, 0.1);
        padding: 15px;
        border-radius: 8px;
    }
    
    /* Button styling */
    .stButton > button {
        background: linear-gradient(180deg, #3498db 0%, #2980b9 100%);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 12px 24px;
        font-size: 16px;
        font-weight: bold;
        width: 100%;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        background: linear-gradient(180deg, #2980b9 0%, #1f4e79 100%);
        transform: translateY(-2px);
    }
    
    /* Input styling */
    .stTextInput > div > div > input {
        background-color: white;
        color: #2c3e50;
        border: 2px solid #bdc3c7;
        border-radius: 8px;
        padding: 12px 15px;
        font-size: 14px;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #3498db;
        box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2);
    }
    
    /* Log container */
    .log-container {
        background-color: #1e1e1e;
        color: #ffffff;
        border: 2px solid #3498db;
        border-radius: 8px;
        padding: 15px;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 12px;
        max-height: 400px;
        overflow-y: auto;
    }
    
    /* Status indicators */
    .status-success {
        background-color: rgba(46, 204, 113, 0.2);
        border: 2px solid #2ecc71;
        border-radius: 8px;
        padding: 10px;
        color: #2ecc71;
        font-weight: bold;
    }
    
    .status-error {
        background-color: rgba(231, 76, 60, 0.2);
        border: 2px solid #e74c3c;
        border-radius: 8px;
        padding: 10px;
        color: #e74c3c;
        font-weight: bold;
    }
    
    .status-running {
        background-color: rgba(52, 152, 219, 0.2);
        border: 2px solid #3498db;
        border-radius: 8px;
        padding: 10px;
        color: #3498db;
        font-weight: bold;
    }
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
        
        # Try to import and run scraper
        try:
            import scraping
            if hasattr(scraping, 'run_scraper'):
                # Capture output
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
                
                # Add captured output to logs
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
        
        # Read output line by line
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
    if st.button("➕ Add Account", type="secondary"):
        st.session_state.form_counter += 1
        st.session_state.forms.append({'id': st.session_state.form_counter})
        st.rerun()

# Display forms
for i, form in enumerate(st.session_state.forms):
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
                        # Try in-process first, then subprocess
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
                st.rerun()
    
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
