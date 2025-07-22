import os

try:
    import streamlit as st
    from streamlit.runtime.runtime import Runtime
    IN_STREAMLIT = Runtime.exists()
except:
    IN_STREAMLIT = False

if IN_STREAMLIT:
    user = st.session_state.get("username", "admin")  # safer: use "username"
    if "users" in st.secrets and user in st.secrets["users"]:
        secrets = st.secrets["users"][user]
        API_KEY = secrets["api_key"]
        WORKSPACE_ID = secrets["workspace_id"]
        BASE_URL = secrets.get("base_url", "https://api.clockify.me/api/v1")
    else:
        st.error("🔐 Пользователь не найден в secrets.toml!")
        st.stop()
else:
    from dotenv import load_dotenv
    load_dotenv()
    API_KEY = os.getenv("CLOCKIFY_API_KEY")
    WORKSPACE_ID = os.getenv("CLOCKIFY_WORKSPACE_ID")
    BASE_URL = os.getenv("CLOCKIFY_BASE_URL", "https://api.clockify.me/api/v1")

HEADERS = {"X-Api-Key": API_KEY, "Content-Type": "application/json"}