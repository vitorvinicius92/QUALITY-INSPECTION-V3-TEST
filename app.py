import os, sys, platform, streamlit as st

st.set_page_config(page_title="Probe", page_icon="✅", layout="centered")
st.title("✅ Probe: app subiu")

st.write("Python:", sys.version)
st.write("Platform:", platform.platform())
st.write("CWD:", os.getcwd())

st.subheader("Secrets (apenas chaves conhecidas, parcialmente)")
for k in ["SUPABASE_DB_URL", "QUALITY_PASS"]:
    v = os.getenv(k, "")
    if v and "@" in v:
        userinfo, rest = v.split("@", 1)
        if ":" in userinfo:
            u, p = userinfo.split(":", 1)
            p = p[:2] + "…" if len(p) > 2 else p
            userinfo = f"{u}:{p}"
        v = f"{userinfo}@{rest}"
    st.code(f"{k} = {v or '(vazio)'}")

st.success("Se você está vendo esta página, o problema NÃO é no Streamlit Cloud.")
st.info("Próximo passo: trocar de volta para o app_safe_boot.py e clicar em 🔌 Conectar.")
