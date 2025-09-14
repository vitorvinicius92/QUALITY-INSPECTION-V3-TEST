
import os
import urllib.parse
import streamlit as st
from sqlalchemy import create_engine, text

st.set_page_config(page_title="RNC - Diagnóstico SQL", page_icon="🩺", layout="centered")

st.title("🔎 Diagnóstico de Conexão com Supabase (SQL)")

DB_URL = os.getenv("SUPABASE_DB_URL", "")

with st.expander("🔐 Variáveis detectadas (parciais)"):
    redacted = DB_URL
    if "@" in redacted:
        userinfo, rest = redacted.split("@", 1)
        userinfo = userinfo[: min(40, len(userinfo))] + ("…" if len(userinfo) > 40 else "")
        redacted = f"{userinfo}@{rest}"
    st.code(f"SUPABASE_DB_URL = {redacted or '(vazia)'}")

def tips():
    st.markdown(
        """
**Checklist rápido:**
1. Copie a string **SQLAlchemy** direto do Supabase (Project settings → Database → Connection string → SQLAlchemy).
2. Confirme a **porta 6543** e o **host** `aws-1-<região>.pooler.supabase.com`.
3. Se a **senha** tiver `@` ou caracteres especiais, **URL-encode** (ex.: `@` vira `%40`).
4. Acrescente `?sslmode=require` no final, se não vier.
5. `requirements.txt` deve conter:
   ```
   streamlit==1.37.1
   sqlalchemy==2.0.32
   psycopg2-binary==2.9.9
   pandas==2.2.2
   ```
6. No Streamlit Cloud: **Manage app → Advanced → Clear cache** e redeploy.
"""
    )

if not DB_URL:
    st.error("SUPABASE_DB_URL está vazio nos Secrets.")
    tips()
    st.stop()

st.subheader("1) Validando formato da URL")
try:
    parsed = urllib.parse.urlparse(DB_URL)
    st.write(f"- **Scheme**: `{parsed.scheme}`")
    st.write(f"- **Netloc**: `{parsed.netloc}`")
    st.write(f"- **Path**: `{parsed.path}`")
    assert parsed.scheme.startswith("postgresql"), "Scheme precisa iniciar com postgresql (ex.: postgresql+psycopg2)"
    assert ":" in parsed.netloc and "@" in DB_URL, "Netloc deve conter usuário@host:porta"
    st.success("Formato básico OK.")
except Exception as e:
    st.error(f"Formato inválido: {e}")
    tips()
    st.stop()

st.subheader("2) Testando conexão")
try:
    eng = create_engine(DB_URL, pool_pre_ping=True)
    with eng.connect() as conn:
        version = conn.execute(text("select version()")).scalar()
        st.success("Conectou no banco! ✅")
        st.code(version)
except Exception as e:
    st.error("Falha ao conectar no banco.")
    st.exception(e)
    tips()
    st.stop()

st.subheader("3) Teste de escrita controlada")
st.caption("Cria/usa uma tabela temporária para garantir permissões básicas.")
try:
    with eng.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE IF NOT EXISTS _diag_write_test (id serial primary key, note text);")
        conn.exec_driver_sql("INSERT INTO _diag_write_test (note) VALUES ('ok');")
        cnt = conn.execute(text("SELECT count(*) FROM _diag_write_test")).scalar()
    st.success(f"Escrita OK. Registros na tabela de teste: {cnt}")
except Exception as e:
    st.error("Conexão OK, mas a escrita falhou (permissões/URL?).")
    st.exception(e)
    tips()
    st.stop()

st.success("✅ Diagnóstico concluído: conexão e escrita básicas OK.")
st.info("Agora você pode voltar ao app principal com tranquilidade.")
