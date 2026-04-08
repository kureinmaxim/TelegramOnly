import streamlit as st
import docker
import requests
import time
from datetime import datetime
import pandas as pd
import os

# --- Configuration ---
TARGET_CONTAINER = "telegram-helper-lite"
API_URL = "http://telegram-helper:8000"
REFRESH_RATE = 5  # seconds

st.set_page_config(
    page_title="Dockhand Diagnostics",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Docker Client ---
@st.cache_resource
def get_docker_client():
    try:
        return docker.from_env()
    except Exception as e:
        st.error(f"Failed to connect to Docker socket: {e}")
        return None

client = get_docker_client()

# --- Helper Functions ---

def get_container_status(container_name):
    if not client:
        return None, "Docker Connection Failed"
    try:
        container = client.containers.get(container_name)
        return container, container.status
    except docker.errors.NotFound:
        return None, "Not Found"
    except Exception as e:
        return None, f"Error: {str(e)}"

def restart_container(container_name):
    if not client:
        return False, "Docker client unavailable"
    try:
        container = client.containers.get(container_name)
        container.restart()
        return True, "Restart initiated"
    except Exception as e:
        return False, f"Restart failed: {str(e)}"

def get_api_health():
    try:
        response = requests.get(f"{API_URL}/health", timeout=2)
        if response.status_code == 200:
            return True, response.json()
        return False, f"Status Code: {response.status_code}"
    except Exception as e:
        return False, f"Connection Error: {str(e)}"

def get_container_logs(container, lines=100):
    try:
        # Get logs as bytes, decode to string
        logs = container.logs(tail=lines).decode('utf-8')
        return logs
    except Exception as e:
        return f"Error reading logs: {str(e)}"

# --- UI Layout ---

st.title("🩺 Dockhand Diagnostics")
st.markdown(f"Monitoring **{TARGET_CONTAINER}** | API: `{API_URL}`")

# Auto-refresh mechanism
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = time.time()

if time.time() - st.session_state.last_refresh > REFRESH_RATE:
    st.session_state.last_refresh = time.time()
    st.rerun()

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("System Status")
    
    # Check Container
    container, status = get_container_status(TARGET_CONTAINER)
    
    status_color = "green" if status == "running" else "red"
    st.markdown(f"**Container Status:** :{status_color}[{status.upper()}]")
    
    if container:
        # Stats (Basic)
        created = container.attrs['Created']
        st.caption(f"Created: {created}")
        
        # Restart Button
        if st.button("🔄 Restart Container", type="primary"):
            with st.spinner("Restarting..."):
                success, msg = restart_container(TARGET_CONTAINER)
                if success:
                    st.success(msg)
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(msg)
    
    st.divider()
    
    # Check API Health
    st.subheader("API Health")
    is_healthy, health_data = get_api_health()
    
    if is_healthy:
        st.success("API is Online")
        st.json(health_data, expanded=False)
    else:
        st.error(f"API Unreachable: {health_data}")

with col2:
    current_time = datetime.now().strftime('%H:%M:%S')
    st.subheader(f"Live Logs (Updated: {current_time})")
    
    log_lines = st.slider("Log Lines", 50, 500, 100)
    
    if container:
        logs = get_container_logs(container, log_lines)
        st.code(logs, language="text", line_numbers=True)
    else:
        st.warning("Container not found - cannot show logs")

# Footer
st.divider()
st.caption(f"Refresh rate: {REFRESH_RATE}s")
