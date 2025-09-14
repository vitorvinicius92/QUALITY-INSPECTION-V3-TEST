import os
import urllib.parse
from datetime import datetime, date

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(page_title="RNC - Supabase (Safe Boot)", page_icon="🧰", layout="wide")

# ------------------------------------------------------------------
# Lê Secrets (SUPABASE_DB_URL, QUALITY_PASS). Não conecta automaticamente.
# ------------------------------------------------------------------
DB_URL_RAW = os.getenv("SUPABASE_DB_URL", "")
QUALITY_PASS = os.getenv("QUALITY_PASS", "qualidade123")

# Estado da sessão
if "connected" not in st.session_state:
    st.session_state.connected = False
if "db_url_fixed" not in st.session_state:
    st.session_state.db_url_fixed = ""
if "engine" not in st.session_state:
    st.session_state.engine = None

POOLER_HOST_DEFAULT = "aws-1-sa-east-1.pooler.supabase.com"

def redact(u: str) -> str:
    if not u:
        return "(vazio)"
    try:
        if "@" in u:
            userinfo, rest = u.split("@", 1)
            if ":" in userinfo:
                u_, p_ = userinfo.split(":", 1)
                if len(p_) > 4:
                    p_ = p_[:2] + "…"
                userinfo = f"{u_}:{p_}"
            userinfo = userinfo[:40] + ("…" if len(userinfo) > 40 else "")
            return f"{userinfo}@{rest}"
        return u
    except Exception:
        return u

def force_pg8000_scheme(p):
    return "postgresql+pg8000"

def ensure_sslmode(qs: str) -> str:
    if not qs:
        return "sslmode=require&connect_timeout=8"
    parsed = urllib.parse.parse_qs(qs, keep_blank_values=True)
    if "sslmode" not in parsed:
        qs += "&sslmode=require"
    if "connect_timeout" not in parsed:
        qs += "&connect_timeout=8"
    return qs

def autofix_url(raw: str) -> tuple[str, dict]:
    """
    - Força driver pg8000
    - Se host for db.<ref>.supabase.co com porta 6543, troca para pooler e ajusta user para postgres.<ref>
    - Se host já for pooler, força porta 6543
    - Garante sslmode=require e connect_timeout=8
    """
    if not raw:
        raise RuntimeError("SUPABASE_DB_URL não definido.")
    p = urllib.parse.urlparse(raw)

    scheme = force_pg8000_scheme(p)
    if "@" not in p.netloc:
        raise RuntimeError("URL inválida (sem user@host). Use a string SQLAlchemy do Supabase.")

    userinfo, hostport = p.netloc.split("@", 1)
    host = hostport
    port = None
    if ":" in hostport:
        host, port_s = hostport.rsplit(":", 1)
        try:
            port = int(port_s)
        except Exception:
            port = None

    # Detecta ref do projeto
    ref = None
    if host.startswith("db.") and host.endswith(".supabase.co"):
        parts = host.split(".")
        if len(parts) >= 3:
            ref = parts[1]

    # Corrige pooler/porta
    if host.endswith(".pooler.supabase.com"):
        port = 6543
    elif ref and port == 6543:
        host = POOLER_HOST_DEFAULT
        if not userinfo.startswith("postgres."):
            # preserva senha após os dois pontos
            if ":" in userinfo:
                _, password = userinfo.split(":", 1)
                userinfo = f"postgres.{ref}:{password}"
            else:
                userinfo = f"postgres.{ref}"

    if host.startswith("db.") and host.endswith(".supabase.co") and (port is None):
        port = 5432

    qs = ensure_sslmode(p.query)
    fixed = urllib.parse.urlunparse((
        scheme,
        f"{userinfo}@{host}:{port or 5432}",
        p.path or "/postgres",
        p.params,
        qs,
        p.fragment,
    ))
    connect_args = {"ssl": True, "timeout": 8}
    return fixed, connect_args

def try_connect():
    url, connect_args = autofix_url(DB_URL_RAW)
    st.session_state.db_url_fixed = url
    eng = create_engine(url, pool_size=1, max_overflow=0, pool_pre_ping=False, connect_args=connect_args)
    with eng.connect() as conn:
        conn.exec_driver_sql("SELECT 1;")
    st.session_state.engine = eng
    st.session_state.connected = True

def init_db_if_needed():
    eng = st.session_state.engine
    if not eng:
        return
    with eng.begin() as conn:
        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS inspecoes (
            id BIGSERIAL PRIMARY KEY,
            rnc_num TEXT UNIQUE,
            data TIMESTAMP NOT NULL,
            emitente TEXT,
            area TEXT,
            pep TEXT,
            titulo TEXT,
            descricao TEXT,
            status TEXT DEFAULT 'Aberta'
        );
        """)
        conn.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS rnc_counters (
            year INT PRIMARY KEY,
            last_seq INT NOT NULL
        );
        """)

def next_rnc_num_tx(conn) -> str:
    y = datetime.now().year
    seq = conn.exec_driver_sql(
        """
        INSERT INTO rnc_counters (year, last_seq)
        VALUES (%(y)s, 1)
        ON CONFLICT (year)
        DO UPDATE SET last_seq = rnc_counters.last_seq + 1
        RETURNING last_seq;
        """,
        {"y": y}
    ).scalar_one()
    return f"{y}-{int(seq):03d}"

def insert_rnc(emitente: str, data_insp: date, area: str, pep: str, titulo: str, descricao: str) -> str:
    eng = st.session_state.engine
    with eng.begin() as conn:
        rnc_num = next_rnc_num_tx(conn)
        conn.exec_driver_sql(
            """
            INSERT INTO inspecoes (rnc_num, data, emitente, area, pep, titulo, descricao, status)
            VALUES (%(rnc)s, %(data)s, %(emit)s, %(area)s, %(pep)s, %(tit)s, %(desc)s, 'Aberta');
            """,
            {
                "rnc": rnc_num,
                "data": datetime.combine(data_insp, datetime.min.time()),
                "emit": emitente,
                "area": area,
                "pep": pep,
                "tit": titulo,
                "desc": descricao,
            }
        )
        return rnc_num

def list_rncs_df() -> pd.DataFrame:
    eng = st.session_state.engine
    with eng.connect() as conn:
        return pd.read_sql(
            text("SELECT id, rnc_num, data, emitente, area, pep, titulo, descricao, status FROM inspecoes ORDER BY id DESC"),
            conn,
        )

def update_status(rnc_id: int, new_status: str):
    eng = st.session_state.engine
    with eng.begin() as conn:
        conn.exec_driver_sql(
            "UPDATE inspecoes SET status = %(s)s WHERE id = %(i)s",
            {"s": new_status, "i": rnc_id},
        )

# ---------------- UI ----------------
st.sidebar.subheader("Conexão com Banco (Safe Boot)")
st.sidebar.code("Lida (parcial): " + redact(DB_URL_RAW))
if st.session_state.db_url_fixed:
    st.sidebar.code("Usada (parcial): " + redact(st.session_state.db_url_fixed))
btn = st.sidebar.button("🔌 Conectar", type="primary", disabled=st.session_state.connected)

if btn and not st.session_state.connected:
    with st.status("Conectando ao banco...", expanded=True) as s:
        try:
            try_connect()
            init_db_if_needed()
            s.update(label="✅ Conectado!", state="complete")
            st.sidebar.success("Conectado com sucesso.")
        except Exception as e:
            s.update(label="❌ Falha na conexão", state="error")
            st.sidebar.error(f"Erro: {e}")
            st.stop()

menu = st.sidebar.radio("Menu", ["➕ Nova RNC", "🔎 Consultar", "⬇️⬆️ CSV", "ℹ️ Status"])

if not st.session_state.connected:
    st.info("Clique em **🔌 Conectar** na barra lateral para iniciar a conexão (timeout curto para não travar).");
    st.stop()

if menu == "➕ Nova RNC":
    st.title("Nova RNC (SQL)")
    with st.form("form_new"):
        col1, col2 = st.columns(2)
        emitente = col1.text_input("Emitente")
        data_insp = col2.date_input("Data", value=date.today())
        col3, col4 = st.columns(2)
        area = col3.text_input("Área/Local")
        pep  = col4.text_input("PEP (código — descrição)")
        titulo = st.text_input("Título")
        descricao = st.text_area("Descrição", height=160)
        submitted = st.form_submit_button("Salvar RNC")

    if submitted:
        try:
            rnc_num = insert_rnc(emitente, data_insp, area, pep, titulo, descricao)
            st.success(f"RNC salva! Nº {rnc_num}")
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")

elif menu == "🔎 Consultar":
    st.title("Consultar RNCs")
    try:
        df = list_rncs_df()
    except Exception as e:
        st.error(f"Falha ao carregar RNCs: {e}")
        st.stop()

    if df.empty:
        st.info("Sem registros.");
    else:
        st.dataframe(df, width='stretch', height=400)
        st.subheader("Alterar status")
        sel = st.selectbox("Escolha o ID", options=df["id"].tolist())
        new_status = st.selectbox("Novo status", ["Aberta", "Em ação", "Encerrada", "Cancelada"])
        if st.button("Atualizar status"):
            try:
                update_status(int(sel), new_status)
                st.success("Status atualizado.")
            except Exception as e:
                st.error(f"Falha ao atualizar: {e}")

elif menu == "⬇️⬆️ CSV":
    st.title("Importar / Exportar CSV")
    try:
        df = list_rncs_df()
    except Exception as e:
        st.error(f"Falha ao carregar para exportação: {e}")
        df = pd.DataFrame()

    st.download_button(
        "⬇️ Exportar CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="rnc_export_sql.csv",
        mime="text/csv"
    )

    st.subheader("Importar CSV")
    up = st.file_uploader("CSV com colunas (emitente, data, area, pep, titulo, descricao). 'data' pode ser YYYY-MM-DD.", type=["csv"])
    if up and st.button("Importar agora"):
        try:
            imp = pd.read_csv(up).fillna("")
            if "data" in imp.columns:
                try:
                    imp["data"] = pd.to_datetime(imp["data"]).dt.date
                except Exception:
                    imp["data"] = date.today()
            else:
                imp["data"] = date.today()

            inserted = 0
            for _, r in imp.iterrows():
                d = r.get("data", date.today())
                if not isinstance(d, date):
                    try:
                        d = pd.to_datetime(d).date()
                    except Exception:
                        d = date.today()
                insert_rnc(
                    str(r.get("emitente","")),
                    d,
                    str(r.get("area","")),
                    str(r.get("pep","")),
                    str(r.get("titulo","")),
                    str(r.get("descricao","")),
                )
                inserted += 1
            st.success(f"Importação concluída. Inseridos: {inserted}.")
        except Exception as e:
            st.error(f"Falha na importação: {e}")

elif menu == "ℹ️ Status":
    st.title("Status")
    try:
        import pg8000
        st.success(f"pg8000 importado: v{pg8000.__version__}")
    except Exception as e:
        st.error("pg8000 NÃO está instalado.")
        st.exception(e)
    st.code("SUPABASE_DB_URL (parcial): " + redact(DB_URL_RAW))
    st.code("URL usada (parcial): " + redact(st.session_state.db_url_fixed))
    st.info("Modo Safe Boot: conexão só quando você clicar em 'Conectar', com timeout curto (8s).");
