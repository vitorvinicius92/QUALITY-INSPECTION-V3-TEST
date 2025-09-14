
import os
from datetime import datetime, date

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

st.set_page_config(page_title="RNC - Supabase (auto-connect)", page_icon="🛠️", layout="wide")

DB_URL = os.getenv("SUPABASE_DB_URL", "")
QUALITY_PASS = os.getenv("QUALITY_PASS", "qualidade123")

# ------------- helpers de URL/driver -------------
def _as_pg8000(url: str):
    if not url:
        return url, {}
    connect_args = {}
    if "postgresql+psycopg2" in url:
        url = url.replace("postgresql+psycopg2", "postgresql+pg8000")
        connect_args = {"ssl": True}
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+pg8000://", 1)
        connect_args = {"ssl": True}
    elif "postgresql+pg8000" in url:
        connect_args = {"ssl": True}
    return url, connect_args

@st.cache_resource(show_spinner=False)
def get_engine() -> Engine:
    if not DB_URL:
        raise RuntimeError("SUPABASE_DB_URL não definido nos Secrets.")

    # 1) tenta direto como veio
    try:
        eng = create_engine(DB_URL, pool_pre_ping=True)
        # sanity check de conexão
        with eng.connect() as c:
            c.execute(text("select 1"))
        st.sidebar.success("Banco conectado (driver conforme URL).")
        return eng
    except Exception as e1:
        # 2) fallback para pg8000 com SSL
        url2, connect_args = _as_pg8000(DB_URL)
        try:
            eng2 = create_engine(url2, pool_pre_ping=True, connect_args=connect_args)
            with eng2.connect() as c:
                c.execute(text("select 1"))
            st.sidebar.warning("Conectado via fallback pg8000 (SSL).")
            return eng2
        except Exception as e2:
            raise RuntimeError(f"Falha ao conectar. Primário: {e1}; Fallback: {e2}")

def init_db():
    eng = get_engine()
    with eng.begin() as conn:
        conn.exec_driver_sql(\"\"\"
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
        \"\"\")
        conn.exec_driver_sql(\"\"\"
        CREATE TABLE IF NOT EXISTS rnc_counters (
            year INT PRIMARY KEY,
            last_seq INT NOT NULL
        );
        \"\"\")

def next_rnc_num_tx(conn) -> str:
    y = datetime.now().year
    seq = conn.exec_driver_sql(
        \"\"\"
        INSERT INTO rnc_counters (year, last_seq)
        VALUES (%(y)s, 1)
        ON CONFLICT (year)
        DO UPDATE SET last_seq = rnc_counters.last_seq + 1
        RETURNING last_seq;
        \"\"\", {\"y\": y}
    ).scalar_one()
    return f\"{y}-{int(seq):03d}\"

def insert_rnc(emitente: str, data_insp: date, area: str, pep: str, titulo: str, descricao: str) -> str:
    eng = get_engine()
    with eng.begin() as conn:
        rnc_num = next_rnc_num_tx(conn)
        conn.exec_driver_sql(
            \"\"\"
            INSERT INTO inspecoes (rnc_num, data, emitente, area, pep, titulo, descricao, status)
            VALUES (%(rnc)s, %(data)s, %(emit)s, %(area)s, %(pep)s, %(tit)s, %(desc)s, 'Aberta');
            \"\"\", {
                \"rnc\": rnc_num,
                \"data\": datetime.combine(data_insp, datetime.min.time()),
                \"emit\": emitente, \"area\": area, \"pep\": pep,
                \"tit\": titulo, \"desc\": descricao
            }
        )
        return rnc_num

def list_rncs_df() -> pd.DataFrame:
    eng = get_engine()
    with eng.connect() as conn:
        return pd.read_sql(
            text(\"SELECT id, rnc_num, data, emitente, area, pep, titulo, descricao, status FROM inspecoes ORDER BY id DESC\"),
            conn
        )

def update_status(rnc_id: int, new_status: str):
    eng = get_engine()
    with eng.begin() as conn:
        conn.exec_driver_sql(\"UPDATE inspecoes SET status = %(s)s WHERE id = %(i)s\", {\"s\": new_status, \"i\": rnc_id})

# -------- Auth simples --------
def is_quality() -> bool:
    return st.session_state.get(\"is_quality\", False)

def auth_box():
    with st.sidebar.expander(\"🔐 Acesso Qualidade\"):
        pwd = st.text_input(\"Senha (QUALITY_PASS)\", type=\"password\")
        c1, c2 = st.columns(2)
        if c1.button(\"Entrar\"):
            if pwd == QUALITY_PASS:
                st.session_state.is_quality = True
                st.success(\"Perfil Qualidade ativo.\")
            else:
                st.error(\"Senha incorreta.\")
        if c2.button(\"Sair\"):
            st.session_state.is_quality = False
            st.info(\"Saiu do perfil Qualidade.\")

# -------- UI --------
st.sidebar.caption(\"Conexão automática com Supabase (psycopg2 → pg8000 se necessário)\")
try:
    init_db()
except Exception as e:
    st.error(f\"Falha ao inicializar o banco: {e}\")
    st.stop()

auth_box()
menu = st.sidebar.radio(\"Menu\", [\"➕ Nova RNC\", \"🔎 Consultar\", \"⬇️⬆️ CSV\", \"ℹ️ Status\"])

if menu == \"➕ Nova RNC\":
    st.title(\"Nova RNC (SQL)\")
    with st.form(\"form_new\"):
        c1, c2 = st.columns(2)
        emitente = c1.text_input(\"Emitente\")
        data_insp = c2.date_input(\"Data\", value=date.today())
        c3, c4 = st.columns(2)
        area = c3.text_input(\"Área/Local\")
        pep  = c4.text_input(\"PEP (código — descrição)\")
        titulo = st.text_input(\"Título\")
        descricao = st.text_area(\"Descrição\", height=160)
        submitted = st.form_submit_button(\"Salvar RNC\")

    if submitted:
        if not is_quality():
            st.error(\"Somente Qualidade pode salvar. Faça login na barra lateral.\")
        else:
            try:
                rnc_num = insert_rnc(emitente, data_insp, area, pep, titulo, descricao)
                st.success(f\"RNC salva! Nº {rnc_num}\")
            except Exception as e:
                st.error(f\"Erro ao salvar: {e}\")

elif menu == \"🔎 Consultar\":
    st.title(\"Consultar RNCs\")
    try:
        df = list_rncs_df()
    except Exception as e:
        st.error(f\"Falha ao carregar RNCs: {e}\")
        st.stop()

    if df.empty:
        st.info(\"Sem registros.\")
    else:
        st.dataframe(df, width='stretch', height=400)
        st.subheader(\"Alterar status\")
        sel = st.selectbox(\"Escolha o ID\", options=df[\"id\"].tolist())
        new_status = st.selectbox(\"Novo status\", [\"Aberta\", \"Em ação\", \"Encerrada\", \"Cancelada\"])
        if st.button(\"Atualizar status\"):
            try:
                update_status(int(sel), new_status)
                st.success(\"Status atualizado.\")
            except Exception as e:
                st.error(f\"Falha ao atualizar: {e}\")

elif menu == \"⬇️⬆️ CSV\":
    st.title(\"Importar / Exportar CSV\")
    try:
        df = list_rncs_df()
    except Exception as e:
        st.error(f\"Falha ao carregar para exportação: {e}\")
        df = pd.DataFrame()

    st.download_button(
        \"⬇️ Exportar CSV\",
        data=df.to_csv(index=False).encode(\"utf-8-sig\"),
        file_name=\"rnc_export_sql.csv\",
        mime=\"text/csv\"
    )

    st.subheader(\"Importar CSV\")
    up = st.file_uploader(\"CSV com colunas (emitente, data, area, pep, titulo, descricao). 'data' pode ser YYYY-MM-DD.\", type=[\"csv\"])  # noqa: E501
    if up and st.button(\"Importar agora\"):
        try:
            imp = pd.read_csv(up).fillna(\"\")
            if \"data\" in imp.columns:
                try:
                    imp[\"data\"] = pd.to_datetime(imp[\"data\"]).dt.date
                except Exception:
                    imp[\"data\"] = date.today()
            else:
                imp[\"data\"] = date.today()

            inserted = 0
            for _, r in imp.iterrows():
                d = r.get(\"data\", date.today())
                if not isinstance(d, date):
                    try:
                        d = pd.to_datetime(d).date()
                    except Exception:
                        d = date.today()
                insert_rnc(
                    str(r.get(\"emitente\",\"\")),
                    d,
                    str(r.get(\"area\",\"\")),
                    str(r.get(\"pep\",\"\")),
                    str(r.get(\"titulo\",\"\")),
                    str(r.get(\"descricao\",\"\")),
                )
                inserted += 1
            st.success(f\"Importação concluída. Inseridos: {inserted}.\")
        except Exception as e:
            st.error(f\"Falha na importação: {e}\")

elif menu == \"ℹ️ Status\":
    st.title(\"Status\")
    show = DB_URL
    if \"@\" in show:
        userinfo, rest = show.split(\"@\", 1)
        userinfo = userinfo[: min(40, len(userinfo))] + (\"…\" if len(userinfo) > 40 else \"\")
        show = f\"{userinfo}@{rest}\"
    st.code(f\"SUPABASE_DB_URL = {show or '(vazio)'}\")
    st.info(\"Conexão automática: tenta driver da URL e cai para pg8000+SSL se necessário. Placeholders: `%(nome)s`.\")
