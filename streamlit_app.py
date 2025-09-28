import streamlit as st
import subprocess
import sys
import os
import io
import contextlib
from datetime import datetime
import pandas as pd  # لو هتتعامل مع داتا لاحقاً

# ---------- Page config ----------
st.set_page_config(
    page_title="Google Pay Scraper Professional",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ---------- CSS ----------
st.markdown("""
<style>
    .main { background: linear-gradient(135deg, #2c3e50 0%, #34495e 50%, #2c3e50 100%); color: white; }
    .header-container {
        background: linear-gradient(90deg, rgba(52,152,219,.2), rgba(155,89,182,.2), rgba(52,152,219,.2));
        border: 2px solid rgba(52,152,219,.5); border-radius: 15px; padding: 30px; margin: 20px 0; text-align: center;
    }
    .main-title { background: linear-gradient(90deg,#3498db, #9b59b6, #3498db); -webkit-background-clip:text; -webkit-text-fill-color:transparent;
        font-size: 2.5rem; font-weight: 700; margin: 10px 0; }
    .subtitle { color:#bdc3c7; font-size:1.2rem; font-style:italic; margin:10px 0; }
    .form-container {
        background: linear-gradient(135deg, rgba(255,255,255,.95), rgba(248,249,250,.95));
        border: 2px solid #3498db; border-radius: 15px; padding: 25px; margin: 20px 0; color:#2c3e50;
    }
    .form-title { color:#3498db; font-size:1.5rem; font-weight:700; margin-bottom:20px; text-align:center;
        background-color: rgba(52,152,219,.1); padding:15px; border-radius:8px; }
    .stButton > button {
        background: linear-gradient(180deg, #3498db, #2980b9); color:#fff; border:none; border-radius:10px;
        padding:12px 24px; font-size:16px; font-weight:700; width:100%; transition:.3s;
    }
    .stButton > button:hover { background: linear-gradient(180deg,#2980b9,#1f4e79); transform: translateY(-2px); }
    .stTextInput > div > div > input {
        background:#fff; color:#2c3e50; border:2px solid #bdc3c7; border-radius:8px; padding:12px 15px; font-size:14px;
    }
    .stTextInput > div > div > input:focus { border-color:#3498db; box-shadow:0 0 0 2px rgba(52,152,219,.2); }
    .log-container {
        background:#1e1e1e; color:#fff; border:2px solid #3498db; border-radius:8px; padding:15px;
        font-family:'Consolas','Monaco',monospace; font-size:12px; max-height:400px; overflow-y:auto;
        white-space:pre-wrap;
    }
    .status-success { background: rgba(46,204,113,.2); border:2px solid #2ecc71; border-radius:8px; padding:10px; color:#2ecc71; font-weight:700; }
    .status-error   { background: rgba(231,76,60,.2);  border:2px solid #e74c3c;  border-radius:8px; padding:10px; color:#e74c3c;  font-weight:700; }
    .status-running { background: rgba(52,152,219,.2);  border:2px solid #3498db;  border-radius:8px; padding:10px; color:#3498db;  font-weight:700; }
</style>
""", unsafe_allow_html=True)

# ---------- Session State ----------
st.session_state.setdefault("forms", [{"id": 1}])
st.session_state.setdefault("form_counter", 1)
st.session_state.setdefault("logs", [])
st.session_state.setdefault("scraper_running", False)
st.session_state.setdefault("scraper_status", "")

# ---------- Scraper runners ----------
def run_scraper_in_process(email, password, pages, auto_bypass):
    logs, success = [], False
    try:
        logs += [
            "🚀 Starting Google Pay Scraper...",
            f"📧 Email: {email}",
            f"🔐 Password: {'*'*len(password)}",
            f"📄 Pages: {pages}",
            f"🤖 Auto-bypass: {auto_bypass}",
            "-"*50,
        ]
        try:
            import scraping
            if hasattr(scraping, "run_scraper"):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    try:
                        scraping.run_scraper(email, password, pages, auto_bypass)
                        success = True
                        logs.append("✅ Scraper completed successfully!")
                    except SystemExit as se:
                        code = int(getattr(se, "code", 1) or 0)
                        success = (code == 0)
                        logs.append("✅ Scraper completed!" if success else f"❌ Exit code: {code}")
                    except Exception as e:
                        logs.append(f"❌ Error: {e}")
                out = buf.getvalue()
                if out:
                    for line in out.splitlines():
                        if line.strip():
                            logs.append(line.strip())
            else:
                logs.append("⚠️ Scraper function not available.")
        except ImportError:
            logs.append("⚠️ Scraper module not available.")
        except Exception as e:
            logs.append(f"❌ Import error: {e}")
    except Exception as e:
        logs.append(f"💥 Unexpected error: {e}")
    return success, logs

def run_scraper_subprocess(email, password, pages, auto_bypass):
    logs, success = [], False
    try:
        if not os.path.exists("scraping.py"):
            logs.append("⚠️ Scraper file not found.")
            return False, logs
        cmd = [sys.executable, "scraping.py", "--email", email, "--password", password, "--pages", str(pages)]
        if auto_bypass:
            cmd.append("--auto-bypass")
        logs.append("🚀 Starting scraper subprocess...")
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
        for line in proc.stdout:
            if line:
                logs.append(line.strip())
        code = proc.wait()
        success = (code == 0)
        logs.append("✅ Scraper completed successfully!" if success else f"❌ Scraper failed with exit code: {code}")
    except Exception as e:
        logs.append(f"💥 Subprocess error: {e}")
    return success, logs

# ---------- Header ----------
st.markdown("""
<div class="header-container">
  <h1 class="main-title">🚀 Welcome Again</h1>
  <p class="subtitle">Professional Google Pay Data Extraction Tool</p>
</div>
""", unsafe_allow_html=True)

# ---------- Add/Remove Forms ----------
cols = st.columns([3, 1])
with cols[1]:
    if st.button("➕ Add Account", type="secondary"):
        st.session_state.form_counter += 1
        st.session_state.forms.append({"id": st.session_state.form_counter})

# ---------- Forms ----------
for form in st.session_state.forms:
    st.markdown(f"""
    <div class="form-container">
        <div class="form-title">📝 Account Configuration #{form['id']}</div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns([4, 1])
    with c1:
        email = st.text_input("📧 Email Address:", placeholder="user@gmail.com", key=f"email_{form['id']}")
        password = st.text_input("🔐 Password:", type="password", placeholder="Enter your password", key=f"password_{form['id']}")
        c_pages, c_bypass = st.columns([1, 2])
        with c_pages:
            pages = st.number_input("📄 Number of Pages:", min_value=1, value=1, key=f"pages_{form['id']}")
        with c_bypass:
            auto_bypass = st.checkbox("🤖 Enable Auto-bypass", value=True, help="Automatically handle passkey prompts", key=f"auto_{form['id']}")

        if st.button("🚀 Start Scraping", key=f"submit_{form['id']}", type="primary"):
            if not email or not password:
                st.error("⚠️ Please enter both email and password!")
            else:
                st.session_state.scraper_running = True
                st.session_state.scraper_status = "running"
                st.session_state.logs = []
                with st.spinner("🔄 Scraper is running..."):
                    success, logs = run_scraper_in_process(email, password, pages, auto_bypass)
                    if not success and not logs:
                        success, logs = run_scraper_subprocess(email, password, pages, auto_bypass)
                st.session_state.logs = logs
                st.session_state.scraper_running = False
                st.session_state.scraper_status = "success" if success else "error"

    with c2:
        if len(st.session_state.forms) > 1:
            if st.button("🗑️ Remove", key=f"remove_{form['id']}", type="secondary"):
                st.session_state.forms = [f for f in st.session_state.forms if f["id"] != form["id"]]

    st.markdown("---")

# ---------- Status & Logs ----------
if st.session_state.logs or st.session_state.scraper_running:
    st.markdown("## 📊 Scraper Status")
    if st.session_state.scraper_running:
        st.markdown('<div class="status-running">🔄 Scraper is running...</div>', unsafe_allow_html=True)
    elif st.session_state.scraper_status == "success":
        st.markdown('<div class="status-success">✅ Completed successfully</div>', unsafe_allow_html=True)
    elif st.session_state.scraper_status == "error":
        st.markdown('<div class="status-error">❌ Process failed</div>', unsafe_allow_html=True)

    if st.session_state.logs:
        st.markdown("### 📝 Live Logs")
        st.markdown(f'<div class="log-container">{"\\n".join(st.session_state.logs)}</div>', unsafe_allow_html=True)
        if st.button("🗑️ Clear Logs"):
            st.session_state.logs = []
            st.session_state.scraper_status = ""

# ---------- Footer ----------
st.markdown("---")
st.markdown("""
<div style="text-align:center;color:#bdc3c7;margin:20px 0;">
  <p>🚀 Google Pay Scraper Professional Edition v2.0</p>
  <p>Built with Streamlit • Secure • Professional</p>
</div>
""", unsafe_allow_html=True)
