
import os
import re
import urllib.parse
from datetime import datetime, date

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

st.set_page_config(page_title="RNC - SQL (AutoFix URL + pg8000)", page_icon="🛠️", layout="wide")

# Lida com:
# - SUPABASE_DB_URL "errada": db.<ref>.supabase.co:6543  -> converte p/ pooler
# - Troca driver para pg8000 (100% Python)
DB_URL_RAW = os.getenv("SUPABASE_DB_URL", "")
QUALITY_PASS = os.getenv("QUALITY_PASS", "qualidade123")

POOLER_HOST_DEFAULT = "aws-1-sa-east-1.pooler.supabase.com"  # região do seu projeto

def redact_url(url: str) -> str:
    if not url:
        return "(vazio)"
    try:
        # oculta parte da senha e limita userinfo
        if "@" in url:
            userinfo, rest = url.split("@", 1)
            if ":" in userinfo:
                u, p = userinfo.split(":", 1)
                if len(p) > 4:
                    p = p[:2] + "…"
                userinfo = f"{u}:{p}"
            userinfo = userinfo[: min(40, len(userinfo))] + ("…" if len(userinfo) > 40 else "")
            return f"{userinfo}@{rest}"
        return url
    except Exception:
        return url

def ensure_sslmode(qs: str) -> str:
    # garante sslmode=require na query string
    if not qs:
        return "sslmode=require"
    kv = urllib.parse.parse_qs(qs, keep_blank_values=True)
    if "sslmode" not in kv:
        sep = "&" if qs else ""
        return qs + f"{sep}sslmode=require"
    return qs

def build_netloc(userinfo: str, host: str, port: int | None) -> str:
    if port is not None:
        return f"{userinfo}@{host}:{port}"
    return f"{userinfo}@{host}"

def autofix_db_url(db_url: str) -> tuple[str, dict]:
    """
    Regras:
    - Sempre força driver pg8000.
    - Se host for db.<ref>.supabase.co e porta 6543 => troca para pooler + user postgres.<ref> + porta 6543
    - Se host já for pooler mas sem porta 6543 => ajusta
    - Garante sslmode=require
    """
    if not db_url:
        return db_url, {}

    # 1) parse
    p = urllib.parse.urlparse(db_url)

    # 2) força driver pg8000
    scheme = p.scheme
    if scheme.startswith("postgresql+psycopg2"):
        scheme = "postgresql+pg8000"
    elif scheme == "postgresql":
        scheme = "postgresql+pg8000"
    elif not scheme.startswith("postgresql+pg8000"):
        scheme = "postgresql+pg8000"

    # 3) extrai userinfo/host/port
    # netloc = "user:pass@host:port"
    if "@" not in p.netloc:
        raise RuntimeError("URL sem user@host:porta. Use a string SQLAlchemy do Supabase.")
    userinfo, hostport = p.netloc.split("@", 1)

    host = hostport
    port = None
    if ":" in hostport:
        host, port_str = hostport.rsplit(":", 1)
        try:
            port = int(port_str)
        except Exception:
            port = None

    # 4) detecta ref do projeto a partir do host db.<ref>.supabase.co
    ref = None
    m = re.match(r"^db\.([a-z0-9]+)\.supabase\.co$", host)
    if m:
        ref = m.group(1)

    # 5) regras de correção de host/porta/usuario
    user = userinfo
    if ref and port == 6543:
        # estava usando host "db" com porta do pooler => corrige para o host do pooler
        host = POOLER_HOST_DEFAULT
        # usuário recomendado para pooler: postgres.<ref>
        if not user.startswith("postgres."):
            user = f"postgres.{ref}"
    elif host.endswith(".pooler.supabase.com"):
        # já está no pooler: força porta 6543
        port = 6543

    # 6) remonta netloc e querystring com sslmode
    qs = ensure_sslmode(p.query)
    netloc = build_netloc(user, host, port or 6543)  # porta padrão 6543 para pooler
    fixed = urllib.parse.urlunparse((
        scheme,
        netloc,
        p.path or "/postgres",
        p.params,
        qs,
        p.fragment,
    ))

    # 7) connect_args para pg8000 com SSL
    connect_args = {"ssl": True}
    return fixed, connect_args

@st.cache_resource(show_spinner=False)
def get_engine() -> Engine:
    if not DB_URL_RAW:
        raise RuntimeError("SUPABASE_DB_URL não definido nos Secrets.")
    fixed_url, connect_args = autofix_db_url(DB_URL_RAW)
    st.sidebar.info("URL ajustada: " + redact_url(fixed_url))
    return create_engine(fixed_url, pool_pre_ping=True, connect_args=connect_args)

def init_db():
    eng = get_engine()
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
    eng = get_engine()
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
    eng = get_engine()
    with eng.connect() as conn:
        return pd.read_sql(
            text("SELECT id, rnc_num, data, emitente, area, pep, titulo, descricao, status FROM inspecoes ORDER BY id DESC"),
            conn,
        )

def update_status(rnc_id: int, new_status: str):
    eng = get_engine()
    with eng.begin() as conn:
        conn.exec_driver_sql(
            "UPDATE inspecoes SET status = %(s)s WHERE id = %(i)s",
            {"s": new_status, "i": rnc_id},
        )

def is_quality() -> bool:
    return st.session_state.get("is_quality", False)

def auth_box():
    with st.sidebar.expander("🔐 Acesso Qualidade"):
        pwd = st.text_input("Senha (QUALITY_PASS)", type="password")
        c1, c2 = st.columns(2)
        if c1.button("Entrar"):
            if pwd == QUALITY_PASS:
                st.session_state.is_quality = True
                st.success("Perfil Qualidade ativo.")
            else:
                st.error("Senha incorreta.")
        if c2.button("Sair"):
            st.session_state.is_quality = False
            st.info("Saiu do perfil Qualidade.")

# ---------------- UI ----------------
try:
    init_db()
except Exception as e:
    st.error(f"Falha ao inicializar o banco: {e}")
    st.stop()

auth_box()

menu = st.sidebar.radio("Menu", ["➕ Nova RNC", "🔎 Consultar", "⬇️⬆️ CSV", "ℹ️ Status"])

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
        if not is_quality():
            st.error("Somente Qualidade pode salvar. Faça login na barra lateral.")
        else:
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
        st.info("Sem registros.")
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
    st.code("URL lida (parcial): " + redact_url(DB_URL_RAW))
    fixed_url, _ = autofix_db_url(DB_URL_RAW or "")
    st.code("URL usada (parcial): " + redact_url(fixed_url or ""))
    st.info("Driver: pg8000 (sem binários). SSL ativo. Auto-correção para host/porta do pooler quando necessário.")
