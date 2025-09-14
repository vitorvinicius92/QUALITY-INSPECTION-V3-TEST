
import os, io, uuid, traceback, csv, time
from datetime import datetime, date
from typing import Optional

import streamlit as st
import pandas as pd

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

# Supabase (para fotos via Storage)
try:
    from supabase import create_client
except Exception:
    create_client = None

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

BUILD_TAG = "v08-v6.3-counter-no-returning"

st.set_page_config(page_title=f"RNC — {BUILD_TAG}", page_icon="📝", layout="wide")

# ----------------- Secrets / Env -----------------
SUPABASE_URL    = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY    = os.getenv("SUPABASE_KEY", "")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "RNC-FOTOS")
QUALITY_PASS    = os.getenv("QUALITY_PASS", "qualidade123")
INIT_DB_FLAG    = os.getenv("INIT_DB", "true").lower() == "true"

# ----------------- Conexões -----------------
def get_engine():
    if SUPABASE_DB_URL:
        try:
            eng = create_engine(SUPABASE_DB_URL, poolclass=NullPool, future=True)
            with eng.connect() as c:
                c.exec_driver_sql("SELECT 1;")
            st.info("🔌 Banco conectado (Supabase).")
            return eng
        except Exception as e:
            st.warning("Não conectou ao Supabase. Usando SQLite local (rnc.db).")
            with st.expander("Detalhes de conexão"):
                st.code(f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}")
    eng = create_engine("sqlite:///rnc.db", poolclass=NullPool, future=True)
    with eng.connect() as c:
        c.exec_driver_sql("SELECT 1;")
    st.warning("⚠️ Banco local (SQLite) em uso.")
    return eng

def get_supabase():
    if not (SUPABASE_URL and SUPABASE_KEY and create_client):
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None

engine = get_engine()
DB_KIND = engine.url.get_backend_name()
supabase = get_supabase()

# ----------------- Migrações -----------------
def try_sql(conn, sql: str):
    try:
        conn.exec_driver_sql(sql)
        return None
    except Exception as e:
        return f"{type(e).__name__}: {e}"

def init_db():
    with engine.begin() as conn:
        if DB_KIND == "postgresql":
            # forçar schema padrão
            err = try_sql(conn, "SET search_path TO public;")
            if err:
                try_sql(conn, "CREATE SCHEMA IF NOT EXISTS app;")
                try_sql(conn, "SET search_path TO app, public;")
            stmts = [
                """
                CREATE TABLE IF NOT EXISTS inspecoes (
                    id BIGSERIAL PRIMARY KEY,
                    data TIMESTAMP NULL,
                    rnc_num TEXT UNIQUE,
                    emitente TEXT,
                    area TEXT,
                    pep TEXT,
                    titulo TEXT,
                    responsavel TEXT,
                    descricao TEXT,
                    referencias TEXT,
                    causador TEXT,
                    processo_envolvido TEXT,
                    origem TEXT,
                    severidade TEXT,
                    categoria TEXT,
                    acoes TEXT,
                    status TEXT DEFAULT 'Aberta',
                    encerrada_em TIMESTAMP NULL,
                    encerrada_por TEXT,
                    encerramento_obs TEXT,
                    encerramento_desc TEXT,
                    eficacia TEXT,
                    responsavel_acao TEXT,
                    reaberta_em TIMESTAMP NULL,
                    reaberta_por TEXT,
                    reabertura_motivo TEXT,
                    reabertura_desc TEXT,
                    cancelada_em TIMESTAMP NULL,
                    cancelada_por TEXT,
                    cancelamento_motivo TEXT
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS fotos (
                    id BIGSERIAL PRIMARY KEY,
                    inspecao_id BIGINT NOT NULL,
                    tipo TEXT,
                    url TEXT,
                    path TEXT,
                    filename TEXT,
                    mimetype TEXT
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS peps (
                    id BIGSERIAL PRIMARY KEY,
                    code TEXT UNIQUE
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    blob BYTEA,
                    text TEXT
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS rnc_counters (
                    year INTEGER PRIMARY KEY,
                    last_seq INTEGER NOT NULL
                );
                """,
                "CREATE UNIQUE INDEX IF NOT EXISTS uidx_inspecoes_rnc ON inspecoes (rnc_num);",
            ]
            diag = []
            for s in stmts:
                er = try_sql(conn, s)
                if er: diag.append(er)
            if diag:
                with st.expander("📋 Diagnóstico de migração (Postgres)"):
                    st.code("\n".join(diag))
        else:
            stmts = [
                """
                CREATE TABLE IF NOT EXISTS inspecoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TIMESTAMP NULL,
                    rnc_num TEXT UNIQUE,
                    emitente TEXT,
                    area TEXT,
                    pep TEXT,
                    titulo TEXT,
                    responsavel TEXT,
                    descricao TEXT,
                    referencias TEXT,
                    causador TEXT,
                    processo_envolvido TEXT,
                    origem TEXT,
                    severidade TEXT,
                    categoria TEXT,
                    acoes TEXT,
                    status TEXT DEFAULT 'Aberta',
                    encerrada_em TIMESTAMP NULL,
                    encerrada_por TEXT,
                    encerramento_obs TEXT,
                    encerramento_desc TEXT,
                    eficacia TEXT,
                    responsavel_acao TEXT,
                    reaberta_em TIMESTAMP NULL,
                    reaberta_por TEXT,
                    reabertura_motivo TEXT,
                    reabertura_desc TEXT,
                    cancelada_em TIMESTAMP NULL,
                    cancelada_por TEXT,
                    cancelamento_motivo TEXT
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS fotos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inspecao_id INTEGER NOT NULL,
                    tipo TEXT,
                    url TEXT,
                    path TEXT,
                    filename TEXT,
                    mimetype TEXT
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS peps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    blob BLOB,
                    text TEXT
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS rnc_counters (
                    year INTEGER PRIMARY KEY,
                    last_seq INTEGER NOT NULL
                );
                """,
                "CREATE UNIQUE INDEX IF NOT EXISTS uidx_inspecoes_rnc ON inspecoes (rnc_num);",
            ]
            for s in stmts:
                try_sql(conn, s)

if INIT_DB_FLAG:
    init_db()

# ----------------- Helpers -----------------
def is_quality() -> bool:
    return st.session_state.get("is_quality", False)

def auth_box():
    with st.sidebar.expander("🔐 Acesso Qualidade"):
        pwd = st.text_input("Senha", type="password", key="pwd_q")
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

    with st.sidebar.expander("🖼️ Logo da empresa (PDF)"):
        up = st.file_uploader("Enviar logo (PNG/JPG)", type=["png","jpg","jpeg"], key="uplogo")
        if up is not None:
            set_logo(up.getbuffer().tobytes())
            st.success("Logo atualizada.")
        if st.button("Remover logo"):
            clear_logo(); st.warning("Logo removida.")

def set_logo(image_bytes: bytes):
    with engine.begin() as conn:
        if DB_KIND == "postgresql":
            conn.exec_driver_sql("INSERT INTO settings(key, blob) VALUES('logo', %(b)s) ON CONFLICT (key) DO UPDATE SET blob=EXCLUDED.blob", {"b": image_bytes})
        else:
            conn.exec_driver_sql("INSERT OR REPLACE INTO settings(key, blob) VALUES('logo', %(b)s)", {"b": image_bytes})

def get_logo() -> Optional[bytes]:
    with engine.begin() as conn:
        r = conn.exec_driver_sql("SELECT blob FROM settings WHERE key='logo'").fetchone()
    return bytes(r[0]) if (r and r[0] is not None) else None

def clear_logo():
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM settings WHERE key='logo'")

def get_supabase_bucket():
    if not supabase:
        return None
    try:
        supabase.storage.create_bucket(SUPABASE_BUCKET, public=True)
    except Exception:
        pass
    return supabase.storage.from_(SUPABASE_BUCKET)

def upload_photos(files, rnc_num: str, tipo: str):
    out = []
    if not files:
        return out
    bucket = get_supabase_bucket()
    if not bucket:
        st.warning("Supabase Storage não configurado — as fotos não serão enviadas para a nuvem.")
        return out
    for f in files:
        try:
            ext = os.path.splitext(f.name)[1].lower() or ".jpg"
            key = f"{rnc_num}/{tipo}/{uuid.uuid4().hex}{ext}"
            data = f.read(); f.seek(0)
            bucket.upload(key, data, {"content-type": f.type or "image/jpeg"})
            url = bucket.get_public_url(key)
            out.append({"url": url, "path": key, "filename": f.name, "mimetype": f.type or "image/jpeg", "tipo": tipo})
        except Exception as e:
            st.error(f"Falha ao subir {f.name}: {e}")
    return out

# ---------- Contador por ano (sem RETURNING) ----------
def next_rnc_num_tx(conn) -> str:
    y = int(datetime.now().year)
    if DB_KIND == "postgresql":
        # 1) UPSERT sem RETURNING
        conn.exec_driver_sql("""
            INSERT INTO rnc_counters (year, last_seq)
            VALUES (%(y)s, 1)
            ON CONFLICT (year)
            DO UPDATE SET last_seq = rnc_counters.last_seq + 1;
        """, {"y": y})
        # 2) Lê o valor final
        seq = conn.exec_driver_sql("SELECT last_seq FROM rnc_counters WHERE year=%(y)s", {"y": y}).scalar_one()
    else:
        try:
            conn.exec_driver_sql("""
                INSERT INTO rnc_counters(year, last_seq) VALUES (%(y)s, 1)
                ON CONFLICT(year) DO UPDATE SET last_seq = last_seq + 1;
            """, {"y": y})
            seq = conn.exec_driver_sql("SELECT last_seq FROM rnc_counters WHERE year=%(y)s", {"y": y}).scalar_one()
        except Exception:
            row = conn.exec_driver_sql("SELECT last_seq FROM rnc_counters WHERE year=%(y)s", {"y": y}).fetchone()
            if row is None:
                conn.exec_driver_sql("INSERT INTO rnc_counters(year, last_seq) VALUES (%(y)s, 1)", {"y": y})
                seq = 1
            else:
                seq = int(row[0]) + 1
                conn.exec_driver_sql("UPDATE rnc_counters SET last_seq=%(s)s WHERE year=%(y)s", {"s": seq, "y": y})
    return f"{y}-{int(seq):03d}"

def insert_rnc_with_counter(conn, payload: dict):
    # Tenta até 20 vezes caso duas pessoas salvem ao mesmo tempo
    for _ in range(20):
        num = next_rnc_num_tx(conn)
        payload2 = dict(payload); payload2["rnc"] = num
        try:
            if DB_KIND == "postgresql":
                rid = conn.exec_driver_sql("""
                    INSERT INTO inspecoes
                    (data, rnc_num, emitente, area, pep, titulo, responsavel, descricao, referencias, causador,
                     processo_envolvido, origem, severidade, categoria, acoes, status)
                    VALUES (%(data)s, %(rnc)s, %(emit)s, %(area)s, %(pep)s, %(tit)s, '', %(desc)s, %(refs)s, %(cau)s, %(proc)s, %(ori)s, %(sev)s, %(cat)s, '', 'Aberta')
                    ON CONFLICT (rnc_num) DO NOTHING
                    RETURNING id;
                """, payload2).scalar()
                if rid is not None:
                    return int(rid), num
            else:
                conn.exec_driver_sql("""
                    INSERT OR IGNORE INTO inspecoes
                    (data, rnc_num, emitente, area, pep, titulo, responsavel, descricao, referencias, causador,
                     processo_envolvido, origem, severidade, categoria, acoes, status)
                    VALUES (%(data)s, %(rnc)s, %(emit)s, %(area)s, %(pep)s, %(tit)s, '', %(desc)s, %(refs)s, %(cau)s, %(proc)s, %(ori)s, %(sev)s, %(cat)s, '', 'Aberta');
                """, payload2)
                lrid = conn.exec_driver_sql("SELECT last_insert_rowid()").scalar()
                if lrid and int(lrid) > 0:
                    return int(lrid), num
        except Exception:
            pass
        time.sleep(0.02)
    raise RuntimeError("Não foi possível alocar número de RNC.")

# ----------------- UI (igual às versões anteriores) -----------------
def is_quality() -> bool:
    return st.session_state.get("is_quality", False)

def auth_box():
    with st.sidebar.expander("🔐 Acesso Qualidade"):
        pwd = st.text_input("Senha", type="password", key="pwd_q")
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

    with st.sidebar.expander("🖼️ Logo da empresa (PDF)"):
        up = st.file_uploader("Enviar logo (PNG/JPG)", type=["png","jpg","jpeg"], key="uplogo")
        if up is not None:
            set_logo(up.getbuffer().tobytes())
            st.success("Logo atualizada.")
        if st.button("Remover logo"):
            clear_logo(); st.warning("Logo removida.")

def set_logo(image_bytes: bytes):
    with engine.begin() as conn:
        if DB_KIND == "postgresql":
            conn.exec_driver_sql("INSERT INTO settings(key, blob) VALUES('logo', %(b)s) ON CONFLICT (key) DO UPDATE SET blob=EXCLUDED.blob", {"b": image_bytes})
        else:
            conn.exec_driver_sql("INSERT OR REPLACE INTO settings(key, blob) VALUES('logo', %(b)s)", {"b": image_bytes})

def clear_logo():
    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM settings WHERE key='logo'")

auth_box()
menu = st.sidebar.radio("Menu", ["➕ Nova RNC", "🔎 Consultar/Editar", "🏷️ PEPs", "⬇️⬆️ CSV", "ℹ️ Status"])

# ➕ Nova RNC
if menu == "➕ Nova RNC":
    st.title(f"Nova RNC — {BUILD_TAG}")
    with st.form("form_rnc"):
        col0, col1, col2 = st.columns(3)
        emitente = col0.text_input("Emitente")
        data_insp = col1.date_input("Data", value=date.today())
        col2.text_input("RNC Nº (gerado ao salvar)", value="(será gerado automaticamente)", disabled=True)

        area = st.text_input("Área/Local", placeholder="Ex.: Correia TR-2011KS-07")
        categoria = st.selectbox("Categoria", ["Segurança","Qualidade","Meio Ambiente","Operação","Manutenção","Outros"])
        severidade = st.selectbox("Severidade", ["Baixa","Média","Alta","Crítica"])
        with engine.begin() as conn:
            peps = [r[0] for r in conn.exec_driver_sql("SELECT code FROM peps ORDER BY code").fetchall()]
        pep = st.selectbox("PEP (código — descrição)", options=[""] + peps)

        causador = st.selectbox("Causador", ["Solda","Pintura","Engenharia","Fornecedor","Cliente","Caldeiraria","Usinagem","Planejamento","Qualidade","RH","Outros"])
        processo = st.selectbox("Processo envolvido", ["Comercial","Compras","Planejamento","Recebimento","Produção","Inspeção Final","Segurança","Meio Ambiente","5S","RH","Outros"])
        origem = st.selectbox("Origem", ["Pintura","Orçamento","Usinagem","Almoxarifado","Solda","Montagem","Cliente","Expedição","Preparação","RH","Outros"])

        titulo = st.text_input("Título", placeholder="Resumo curto da não conformidade")
        descricao = st.text_area("Descrição da não conformidade", height=160)
        referencias = st.text_area("Referências", height=80)

        fotos_ab = st.file_uploader("Fotos da abertura", type=["jpg","jpeg","png"], accept_multiple_files=True)

        submitted = st.form_submit_button("Salvar RNC")

    if submitted:
        if not is_quality():
            st.error("Somente Qualidade pode salvar. Faça login na barra lateral.")
        else:
            payload = {
                "data": datetime.combine(data_insp, datetime.min.time()),
                "emit": emitente, "area": area, "pep": pep, "tit": titulo,
                "desc": descricao, "refs": referencias, "cau": causador,
                "proc": processo, "ori": origem, "sev": severidade, "cat": categoria
            }
            with engine.begin() as conn:
                new_id, rnc = insert_rnc_with_counter(conn, payload)
            metas = upload_photos(fotos_ab or [], rnc, "abertura")
            with engine.begin() as conn:
                for m in metas:
                    conn.exec_driver_sql("""
                        INSERT INTO fotos (inspecao_id, tipo, url, path, filename, mimetype)
                        VALUES (%(i)s,%(t)s,%(u)s,%(p)s,%(n)s,%(m)s)
                    """, {"i": new_id, "t": m["tipo"], "u": m["url"], "p": m["path"], "n": m["filename"], "m": m["mimetype"]})
            st.success(f"RNC salva! Nº {rnc} (ID {new_id})")

# 🔎 Consultar/Editar
elif menu == "🔎 Consultar/Editar":
    st.title("Consultar / Editar RNCs")
    df = pd.read_sql("SELECT id, data, rnc_num, titulo, emitente, area, pep, categoria, severidade, status FROM inspecoes ORDER BY id DESC", engine)
    st.dataframe(df, width='stretch', height=320)
    if df.empty:
        st.info("Sem registros.")
    else:
        sel = st.number_input("Ver RNC (ID)", min_value=int(df["id"].min()), max_value=int(df["id"].max()), value=int(df["id"].iloc[0]), step=1)
        with engine.begin() as conn:
            row = conn.exec_driver_sql("SELECT * FROM inspecoes WHERE id=%(i)s", {"i": int(sel)}).mappings().first()
            fotosA = conn.exec_driver_sql("SELECT * FROM fotos WHERE inspecao_id=%(i)s AND tipo='abertura'", {"i": int(sel)}).mappings().all()
            fotosE = conn.exec_driver_sql("SELECT * FROM fotos WHERE inspecao_id=%(i)s AND tipo='encerramento'", {"i": int(sel)}).mappings().all()
            fotosR = conn.exec_driver_sql("SELECT * FROM fotos WHERE inspecao_id=%(i)s AND tipo='reabertura'", {"i": int(sel)}).mappings().all()

        if not row:
            st.error("ID não encontrado.")
        else:
            st.subheader(f"RNC {row['rnc_num']} — {row['status']}")
            st.write(f"**Título:** {row['titulo']}")
            st.write(f"**Descrição:** {row['descricao']}")
            st.write(f"**Referências:** {row['referencias']}")

            cols = st.columns(4)
            for i, fo in enumerate(fotosA[:8]):
                with cols[i % 4]:
                    st.image(fo["url"] or fo["path"], use_column_width=True, caption="Abertura")
            for i, fo in enumerate(fotosE[:8]):
                with cols[i % 4]:
                    st.image(fo["url"] or fo["path"], use_column_width=True, caption="Encerramento")
            for i, fo in enumerate(fotosR[:8]):
                with cols[i % 4]:
                    st.image(fo["url"] or fo["path"], use_column_width=True, caption="Reabertura")

            st.markdown("---")
            if st.session_state.get("is_quality"):
                with st.expander("✅ Encerrar RNC"):
                    encerr_por = st.text_input("Encerrada por", key=f"encpor_{row['id']}")
                    encerr_obs = st.text_area("Observações", key=f"encobs_{row['id']}")
                    encerr_desc = st.text_area("Descrição do fechamento", key=f"encdesc_{row['id']}")
                    eficacia = st.selectbox("Eficácia", ["A verificar","Eficaz","Não eficaz"], key=f"ef_{row['id']}")
                    fotos_enc = st.file_uploader("Evidências (fotos)", type=["jpg","jpeg","png"], accept_multiple_files=True, key=f"encf_{row['id']}")
                    if st.button("Encerrar agora", key=f"encok_{row['id']}"):
                        metas = upload_photos(fotos_enc or [], row["rnc_num"], "encerramento")
                        with engine.begin() as conn:
                            conn.exec_driver_sql("""
                                UPDATE inspecoes SET status='Encerrada', encerrada_em=%(dt)s, encerrada_por=%(por)s,
                                    encerramento_obs=%(obs)s, encerramento_desc=%(desc)s, eficacia=%(ef)s WHERE id=%(i)s
                            """, {"dt": datetime.now(), "por": encerr_por, "obs": encerr_obs, "desc": encerr_desc, "ef": eficacia, "i": int(sel)})
                            for m in metas:
                                conn.exec_driver_sql("""
                                    INSERT INTO fotos (inspecao_id, tipo, url, path, filename, mimetype)
                                    VALUES (%(i)s,%(t)s,%(u)s,%(p)s,%(n)s,%(m)s)
                                """, {"i": int(sel), "t": m["tipo"], "u": m["url"], "p": m["path"], "n": m["filename"], "m": m["mimetype"]})
                        st.success("RNC encerrada.")

                with st.expander("♻️ Reabrir RNC"):
                    reab_por = st.text_input("Reaberta por", key=f"repor_{row['id']}")
                    reab_motivo = st.text_input("Motivo", key=f"remot_{row['id']}")
                    reab_desc = st.text_area("Descrição da reabertura", key=f"redesc_{row['id']}")
                    fotos_rea = st.file_uploader("Fotos (opcional)", type=["jpg","jpeg","png"], accept_multiple_files=True, key=f"ref_{row['id']}")
                    if st.button("Reabrir agora", key=f"reok_{row['id']}"):
                        metas = upload_photos(fotos_rea or [], row["rnc_num"], "reabertura")
                        with engine.begin() as conn:
                            conn.exec_driver_sql("""
                                UPDATE inspecoes SET status='Em ação', reaberta_em=%(dt)s, reaberta_por=%(por)s,
                                    reabertura_motivo=%(mot)s, reabertura_desc=%(desc)s WHERE id=%(i)s
                            """, {"dt": datetime.now(), "por": reab_por, "mot": reab_motivo, "desc": reab_desc, "i": int(sel)})
                            for m in metas:
                                conn.exec_driver_sql("""
                                    INSERT INTO fotos (inspecao_id, tipo, url, path, filename, mimetype)
                                    VALUES (%(i)s,%(t)s,%(u)s,%(p)s,%(n)s,%(m)s)
                                """, {"i": int(sel), "t": m["tipo"], "u": m["url"], "p": m["path"], "n": m["filename"], "m": m["mimetype"]})
                        st.success("RNC reaberta.")

                with st.expander("🚫 Cancelar RNC"):
                    c_por = st.text_input("Cancelada por", key=f"canpor_{row['id']}")
                    c_mot = st.text_area("Motivo", key=f"canmot_{row['id']}")
                    if st.button("Cancelar", key=f"canok_{row['id']}"):
                        with engine.begin() as conn:
                            conn.exec_driver_sql("""
                                UPDATE inspecoes SET status='Cancelada', cancelada_em=%(dt)s, cancelada_por=%(por)s, cancelamento_motivo=%(mot)s WHERE id=%(i)s
                            """, {"dt": datetime.now(), "por": c_por, "mot": c_mot, "i": int(sel)})
                        st.success("RNC cancelada.")

                with st.expander("🗑️ Excluir permanentemente"):
                    conf = st.text_input("Digite CONFIRMAR para excluir", key=f"del_{row['id']}")
                    if st.button("Excluir RNC", key=f"delok_{row['id']}"):
                        if conf.strip().upper() == "CONFIRMAR":
                            with engine.begin() as conn:
                                conn.exec_driver_sql("DELETE FROM fotos WHERE inspecao_id=%(i)s", {"i": int(sel)})
                                conn.exec_driver_sql("DELETE FROM inspecoes WHERE id=%(i)s", {"i": int(sel)})
                            st.success("RNC excluída.")
                        else:
                            st.warning("Digite CONFIRMAR exatamente.")
            else:
                st.info("Entre como Qualidade para encerrar/reabrir/cancelar/excluir.")

# 🏷️ PEPs
elif menu == "🏷️ PEPs":
    st.title("Gerenciar PEPs")
    dfp = pd.read_sql("SELECT id, code FROM peps ORDER BY code", engine)
    st.dataframe(dfp, width='stretch', height=300)

    st.subheader("Importar PEPs por CSV")
    up_pep = st.file_uploader("CSV com coluna 'code' (ou 1 PEP por linha sem cabeçalho).", type=["csv"], key="up_pep")
    if up_pep and st.button("Importar PEPs do CSV"):
        try:
            dfp_in = pd.read_csv(up_pep)
            if 'code' in dfp_in.columns:
                lst = [str(x) for x in dfp_in['code'].fillna('') if str(x).strip()]
            else:
                up_pep.seek(0)
                import io as _io, csv as _csv
                reader = _csv.reader(_io.StringIO(up_pep.getvalue().decode('utf-8')))
                lst = [row[0] for row in reader if row and str(row[0]).strip()]
        except Exception:
            up_pep.seek(0)
            import io as _io, csv as _csv
            reader = _csv.reader(_io.StringIO(up_pep.getvalue().decode('utf-8')))
            lst = [row[0] for row in reader if row and str(row[0]).strip()]
        n = add_peps_bulk(lst)
        st.success(f"{n} PEP(s) adicionados.")

    st.subheader("Adicionar PEPs manualmente")
    many = st.text_area("Vários (um por linha, formato livre: código — descrição).", height=140)
    if st.button("Adicionar em lote"):
        codes = [l.strip() for l in many.splitlines() if l.strip()]
        n = add_peps_bulk(codes)
        st.success(f"{n} PEP(s) adicionados.")
    c = st.text_input("Adicionar único PEP (código — descrição)")
    if st.button("Adicionar PEP"):
        n = add_peps_bulk([c])
        st.success(f"{n} adicionado(s).")

# ⬇️⬆️ CSV
elif menu == "⬇️⬆️ CSV":
    st.title("Importar / Exportar CSV de RNCs")
    df_all = pd.read_sql("SELECT * FROM inspecoes ORDER BY id DESC", engine)
    st.download_button("⬇️ Exportar CSV", data=df_all.to_csv(index=False).encode("utf-8-sig"), file_name="rnc_export_v08.csv", mime="text/csv")

    st.subheader("Importar CSV de RNCs")
    up = st.file_uploader("Selecione um CSV com colunas compatíveis (não inclua 'id').", type=["csv"])

    def norm_dt(val):
        if pd.isna(val) or str(val).strip() == "":
            return None
        try:
            return pd.to_datetime(val, errors="coerce")
        except Exception:
            return None

    if up and st.button("Importar agora"):
        try:
            imp = pd.read_csv(up)
        except Exception:
            up.seek(0)
            imp = pd.read_csv(up, sep=";")

        if 'id' in imp.columns:
            imp = imp.drop(columns=['id'])

        allowed = [
            "data","rnc_num","emitente","area","pep","titulo","responsavel","descricao","referencias",
            "causador","processo_envolvido","origem","severidade","categoria","acoes","status",
            "encerrada_em","encerrada_por","encerramento_obs","encerramento_desc","eficacia",
            "responsavel_acao","reaberta_em","reaberta_por","reabertura_motivo","reabertura_desc",
            "cancelada_em","cancelada_por","cancelamento_motivo"
        ]
        cols = [c for c in imp.columns if c in allowed]
        if not cols:
            st.error("CSV sem colunas compatíveis com 'inspecoes'.")
        else:
            imp2 = imp[cols].copy()
            for dc in ["data","encerrada_em","reaberta_em","cancelada_em"]:
                if dc in imp2.columns:
                    imp2[dc] = imp2[dc].apply(norm_dt)

            inserted, auto_num, honored = 0, 0, 0
            with engine.begin() as conn:
                for _, r in imp2.fillna("").iterrows():
                    payload = {
                        "data": r.get("data") if "data" in cols else None,
                        "emit": r.get("emitente") if "emitente" in cols else None,
                        "area": r.get("area") if "area" in cols else None,
                        "pep": r.get("pep") if "pep" in cols else None,
                        "tit": r.get("titulo") if "titulo" in cols else None,
                        "desc": r.get("descricao") if "descricao" in cols else None,
                        "refs": r.get("referencias") if "referencias" in cols else None,
                        "cau": r.get("causador") if "causador" in cols else None,
                        "proc": r.get("processo_envolvido") if "processo_envolvido" in cols else None,
                        "ori": r.get("origem") if "origem" in cols else None,
                        "sev": r.get("severidade") if "severidade" in cols else None,
                        "cat": r.get("categoria") if "categoria" in cols else None,
                    }
                    csv_num = str(r.get("rnc_num")).strip() if "rnc_num" in cols else ""
                    rid = None
                    if csv_num:
                        try:
                            if DB_KIND == "postgresql":
                                rid = conn.exec_driver_sql("""
                                    INSERT INTO inspecoes
                                    (data, rnc_num, emitente, area, pep, titulo, responsavel, descricao, referencias, causador,
                                     processo_envolvido, origem, severidade, categoria, acoes, status)
                                    VALUES (%(data)s, %(rnc)s, %(emit)s, %(area)s, %(pep)s, %(tit)s, '', %(desc)s, %(refs)s, %(cau)s, %(proc)s, %(ori)s, %(sev)s, %(cat)s, '', 'Aberta')
                                    ON CONFLICT (rnc_num) DO NOTHING
                                    RETURNING id;
                                """, dict(payload, rnc=csv_num)).scalar()
                                if rid is not None: honored += 1
                            else:
                                conn.exec_driver_sql("""
                                    INSERT OR IGNORE INTO inspecoes
                                    (data, rnc_num, emitente, area, pep, titulo, responsavel, descricao, referencias, causador,
                                     processo_envolvido, origem, severidade, categoria, acoes, status)
                                    VALUES (%(data)s, %(rnc)s, %(emit)s, %(area)s, %(pep)s, %(tit)s, '', %(desc)s, %(refs)s, %(cau)s, %(proc)s, %(ori)s, %(sev)s, %(cat)s, '', 'Aberta');
                                """, dict(payload, rnc=csv_num))
                                lrid = conn.exec_driver_sql("SELECT last_insert_rowid()").scalar()
                                if lrid and int(lrid) > 0: honored += 1; rid = int(lrid)
                        except Exception:
                            rid = None
                    if not rid:
                        rid, gen = insert_rnc_with_counter(conn, payload)
                        auto_num += 1
                    inserted += 1
            st.success(f"Importação concluída. Inseridos: {inserted}. Respeitados do CSV: {honored}. Gerados automaticamente: {auto_num}.")

# ℹ️ Status
elif menu == "ℹ️ Status":
    st.title("Status do App")
    st.write(f"**Build:** {BUILD_TAG}")
    st.write(f"**DB:** {DB_KIND}")
    st.write("**Variáveis:**")
    st.code(f"SUPABASE_URL={'set' if bool(SUPABASE_URL) else 'not set'}; SUPABASE_DB_URL={'set' if bool(SUPABASE_DB_URL) else 'not set'}; SUPABASE_BUCKET={SUPABASE_BUCKET}; INIT_DB={str(INIT_DB_FLAG)}")
    try:
        with engine.connect() as c:
            v = c.exec_driver_sql("SELECT CURRENT_DATE").scalar()
        st.success(f"Ping DB OK — {v}")
    except Exception as e:
        st.error(f"Falha no ping: {e}")
