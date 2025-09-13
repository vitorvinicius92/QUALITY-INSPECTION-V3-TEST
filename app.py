
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from supabase import create_client, Client
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
import io, uuid, datetime as dt

st.set_page_config(page_title="RNC App v08 (Supabase)", page_icon="🧰", layout="wide")

# -------------- Secrets & Clients --------------

@st.cache_resource(show_spinner=False)
def get_secrets():
    required = [
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "SUPABASE_DB_URL",
        "SUPABASE_BUCKET",
        "QUALITY_PASS",
        "INIT_DB",
    ]
    missing = [k for k in required if k not in st.secrets]
    if missing:
        raise RuntimeError(f"Faltam secrets: {', '.join(missing)}")
    return st.secrets

@st.cache_resource(show_spinner=False)
def get_engine() -> Engine:
    s = get_secrets()
    eng = create_engine(s["SUPABASE_DB_URL"], pool_pre_ping=True)
    return eng

@st.cache_resource(show_spinner=False)
def get_supabase() -> Client:
    s = get_secrets()
    return create_client(s["SUPABASE_URL"], s["SUPABASE_KEY"])

def storage_upload_bytes(path: str, data: bytes, content_type: str = "image/jpeg") -> str:
    sb = get_supabase()
    bucket = get_secrets()["SUPABASE_BUCKET"]
    # Ensure bucket exists (idempotent best-effort)
    try:
        sb.storage.create_bucket(bucket, public=True)
    except Exception:
        pass  # already exists
    # Remove leading slash
    path = path[1:] if path.startswith("/") else path
    # Upload; overwrite if exists
    sb.storage.from_(bucket).upload(path, data, {"content-type": content_type, "upsert": True})
    # Build public URL
    pub = sb.storage.from_(bucket).get_public_url(path)
    return pub

# -------------- DB Init --------------

INIT_SQL = """
CREATE TABLE IF NOT EXISTS rnc_counters (
    ano INTEGER PRIMARY KEY,
    counter INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS peps (
    pep TEXT PRIMARY KEY,
    descricao TEXT
);

CREATE TABLE IF NOT EXISTS rnc (
    id BIGSERIAL PRIMARY KEY,
    rnc_num TEXT UNIQUE NOT NULL,
    data_abertura TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    solicitante TEXT,
    descricao TEXT,
    categoria TEXT,
    severidade TEXT,
    pep TEXT REFERENCES peps(pep) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'ABERTA',
    encerramento_obs TEXT,
    reabertura_obs TEXT,
    cancelado BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS rnc_fotos (
    id BIGSERIAL PRIMARY KEY,
    rnc_num TEXT NOT NULL REFERENCES rnc(rnc_num) ON DELETE CASCADE,
    etapa TEXT NOT NULL, -- abertura|encerramento|reabertura
    path TEXT NOT NULL,
    url TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rnc_status ON rnc(status);
CREATE INDEX IF NOT EXISTS idx_rnc_pep ON rnc(pep);
"""

GEN_NUM_SQL = """
WITH up AS (
    INSERT INTO rnc_counters(ano, counter)
    VALUES (:ano, 1)
    ON CONFLICT (ano) DO UPDATE SET counter = rnc_counters.counter + 1
    RETURNING counter
)
SELECT counter FROM up;
"""

def init_db_if_needed():
    if str(get_secrets().get("INIT_DB", "false")).lower() == "true":
        with get_engine().begin() as conn:
            for stmt in [s for s in INIT_SQL.split(";\n") if s.strip()]:
                conn.execute(text(stmt))
        st.success("Tabelas verificadas/criadas (INIT_DB=true). Altere INIT_DB para 'false' após o primeiro run.")

# -------------- Auth (Qualidade) --------------

def auth_block():
    st.sidebar.subheader("🔐 Acesso Qualidade")
    if "auth_ok" not in st.session_state:
        st.session_state.auth_ok = False
    if st.session_state.auth_ok:
        st.sidebar.success("Acesso liberado.")
        if st.sidebar.button("Sair"):
            st.session_state.auth_ok = False
        return
    pwd = st.sidebar.text_input("Senha", type="password", placeholder="QUALITY_PASS")
    if st.sidebar.button("Entrar"):
        if pwd == get_secrets()["QUALITY_PASS"]:
            st.session_state.auth_ok = True
            st.sidebar.success("Acesso liberado.")
        else:
            st.sidebar.error("Senha inválida.")

# -------------- Logo upload (para PDF) --------------

def logo_uploader():
    st.sidebar.subheader("🏷️ Logo (opcional para PDF)")
    file = st.sidebar.file_uploader("Imagem da logo (PNG/JPG)", type=["png","jpg","jpeg"], key="logo_up")
    if file:
        st.session_state["logo_bytes"] = file.read()
        st.sidebar.success("Logo carregada.")
    if st.sidebar.button("Remover logo"):
        st.session_state.pop("logo_bytes", None)

# -------------- Helpers --------------

def next_rnc_number(conn) -> str:
    ano = dt.datetime.now().year
    res = conn.execute(text(GEN_NUM_SQL), {"ano": ano}).scalar_one()
    return f"{ano}-{res:03d}"

def df_rncs(conn, filtro_texto: str = "", status: str | None = None) -> pd.DataFrame:
    q = "SELECT rnc_num, data_abertura, solicitante, pep, categoria, severidade, status, cancelado FROM rnc WHERE 1=1"
    params = {}
    if filtro_texto:
        q += " AND (rnc_num ILIKE :q OR solicitante ILIKE :q OR pep ILIKE :q OR categoria ILIKE :q OR severidade ILIKE :q)"
        params["q"] = f"%{filtro_texto}%"
    if status and status != "TODAS":
        q += " AND status = :status"
        params["status"] = status
    q += " ORDER BY data_abertura DESC"
    return pd.read_sql(text(q), conn, params=params)

def listar_fotos(conn, rnc_num: str, etapa: str | None = None) -> pd.DataFrame:
    q = "SELECT id, etapa, url, path, created_at FROM rnc_fotos WHERE rnc_num=:r ORDER BY created_at"
    p = {"r": rnc_num}
    if etapa:
        q = "SELECT id, etapa, url, path, created_at FROM rnc_fotos WHERE rnc_num=:r AND etapa=:e ORDER BY created_at"
        p = {"r": rnc_num, "e": etapa}
    return pd.read_sql(text(q), conn, params=p)

def add_foto(conn, rnc_num: str, etapa: str, file_bytes: bytes, mime: str):
    name = f"{uuid.uuid4().hex}.jpg" if not mime or 'jpeg' in mime or 'jpg' in mime else f"{uuid.uuid4().hex}.png"
    path = f"RNC/{etapa}/{name}"
    url = storage_upload_bytes(path, file_bytes, content_type=mime or "image/jpeg")
    with conn.begin():
        conn.execute(text("INSERT INTO rnc_fotos(rnc_num, etapa, path, url) VALUES (:r,:e,:p,:u)"),
                     {"r": rnc_num, "e": etapa, "p": path, "u": url})
    st.success(f"Foto enviada para {etapa}.")

def gerar_pdf(rnc_row: dict, fotos: dict[str, list[str]]):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    # Header
    if "logo_bytes" in st.session_state:
        try:
            logo = ImageReader(io.BytesIO(st.session_state["logo_bytes"]))
            c.drawImage(logo, 15*mm, H-30*mm, width=40*mm, height=20*mm, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    c.setFont("Helvetica-Bold", 14)
    c.drawString(60*mm, H-20*mm, "Relatório de Não Conformidade (RNC)")
    c.setFont("Helvetica", 10)
    c.drawString(60*mm, H-27*mm, f"RNC: {rnc_row.get('rnc_num','')} — Status: {rnc_row.get('status','')}")

    y = H - 40*mm
    def line(txt):
        nonlocal y
        c.setFont("Helvetica", 10)
        c.drawString(15*mm, y, txt)
        y -= 6*mm

    line(f"Abertura: {rnc_row.get('data_abertura','')}")
    line(f"Solicitante: {rnc_row.get('solicitante','')}")
    line(f"PEP: {rnc_row.get('pep','')}")
    line(f"Categoria: {rnc_row.get('categoria','')}  |  Severidade: {rnc_row.get('severidade','')}")
    line("Descrição:")
    # wrap description
    desc = (rnc_row.get('descricao') or "").strip().splitlines()
    for ln in desc:
        for chunk in [ln[i:i+120] for i in range(0, len(ln), 120)]:
            line("  " + chunk)

    # Observações de encerramento/reabertura
    if rnc_row.get("encerramento_obs"):
        line("")
        line("Encerramento:")
        for ln in str(rnc_row["encerramento_obs"]).splitlines():
            for chunk in [ln[i:i+120] for i in range(0, len(ln), 120)]:
                line("  " + chunk)
    if rnc_row.get("reabertura_obs"):
        line("")
        line("Reabertura:")
        for ln in str(rnc_row["reabertura_obs"]).splitlines():
            for chunk in [ln[i:i+120] for i in range(0, len(ln), 120)]:
                line("  " + chunk)

    # Fotos (miniaturas como links)
    def fotos_sec(titulo, urls):
        nonlocal y
        if not urls:
            return
        y -= 4*mm
        c.setFont("Helvetica-Bold", 11)
        c.drawString(15*mm, y, titulo)
        y -= 8*mm
        c.setFont("Helvetica", 9)
        for u in urls:
            for chunk in [u[i:i+90] for i in range(0, len(u), 90)]:
                if y < 20*mm:
                    c.showPage()
                    y = H - 20*mm
                c.drawString(20*mm, y, chunk)
                y -= 5*mm

    c.setFont("Helvetica-Bold", 11)
    fotos_sec("Fotos de Abertura", fotos.get("abertura", []))
    fotos_sec("Fotos de Encerramento", fotos.get("encerramento", []))
    fotos_sec("Fotos de Reabertura", fotos.get("reabertura", []))

    c.showPage()
    c.save()
    buf.seek(0)
    return buf

# -------------- UI Pages --------------

def page_status():
    st.header("ℹ️ Status do Sistema")
    ok_sb, ok_db = False, False
    with st.expander("Secrets"):
        try:
            s = get_secrets()
            st.json({k: ("***" if "KEY" in k or "PASS" in k or "SENHA" in k else str(v)) for k,v in s.items()})
            st.success("Secrets lidos.")
        except Exception as e:
            st.error(f"Erro ao ler secrets: {e}")
    with st.expander("Conexão Banco (SQLAlchemy)"):
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            st.success("Conectado.")
            ok_db = True
        except Exception as e:
            st.error(f"Falhou: {e}")
    with st.expander("Supabase Storage"):
        try:
            url = storage_upload_bytes(f"healthcheck/{uuid.uuid4().hex}.txt", b"ok", "text/plain")
            st.write("Upload OK:", url)
            st.success("Storage disponível.")
            ok_sb = True
        except Exception as e:
            st.error(f"Falhou: {e}")
    st.info(f"DB OK: {ok_db} | Storage OK: {ok_sb}")

def page_nova_rnc():
    st.header("➕ Nova RNC")
    if not st.session_state.get("auth_ok"):
        st.warning("Acesso restrito. Faça login no menu lateral.")
        return
    with get_engine().begin() as conn:
        rnc_num = next_rnc_number(conn)
    st.info(f"Número sugerido: **{rnc_num}**")
    with st.form("nova_rnc"):
        solicitante = st.text_input("Solicitante")
        pep = st.text_input("PEP (existente em PEPs, opcional)")
        categoria = st.selectbox("Categoria", ["Processo","Produto","Serviço","Documentação","Outro"])
        severidade = st.selectbox("Severidade", ["Baixa","Média","Alta","Crítica"])
        descricao = st.text_area("Descrição detalhada")
        fotos_abertura = st.file_uploader("Fotos de Abertura", type=["png","jpg","jpeg"], accept_multiple_files=True)
        ok = st.form_submit_button("Salvar RNC")
    if ok:
        with get_engine().begin() as conn:
            conn.execute(text("""
                INSERT INTO rnc(rnc_num, solicitante, descricao, categoria, severidade, pep, status)
                VALUES (:n,:s,:d,:c,:sev,:p,'ABERTA')
            """), {"n": rnc_num, "s": solicitante, "d": descricao, "c": categoria, "sev": severidade, "p": pep or None})
        st.success(f"RNC {rnc_num} criada.")
        if fotos_abertura:
            with get_engine().begin() as conn:
                for f in fotos_abertura:
                    add_foto(conn, rnc_num, "abertura", f.read(), f.type)

def page_consultar():
    st.header("🔎 Consultar / Editar")
    filtro = st.text_input("Buscar (número, solicitante, PEP, categoria, severidade)")
    status_sel = st.selectbox("Status", ["TODAS","ABERTA","ENCERRADA","REABERTA","CANCELADA"])
    with get_engine().begin() as conn:
        df = df_rncs(conn, filtro, None if status_sel=="TODAS" else status_sel)
    st.dataframe(df, use_container_width=True, hide_index=True)
    rnc_num = st.text_input("Abrir RNC (digite o número exato e pressione Enter)", key="abrir_rnc")
    if rnc_num:
        with get_engine().begin() as conn:
            row = conn.execute(text("SELECT * FROM rnc WHERE rnc_num=:n"), {"n": rnc_num}).mappings().first()
            if not row:
                st.error("RNC não encontrada.")
                return
            st.subheader(f"RNC {rnc_num} — Status: {row['status']}")
            tabs = st.tabs(["📄 Detalhes","🖼️ Fotos","📑 PDF"])

            with tabs[0]:
                if not st.session_state.get("auth_ok"):
                    st.warning("Acesso de edição restrito. Faça login.")
                solicitante = st.text_input("Solicitante", value=row["solicitante"] or "")
                pep = st.text_input("PEP", value=row["pep"] or "")
                categoria = st.selectbox("Categoria", ["Processo","Produto","Serviço","Documentação","Outro"], index=["Processo","Produto","Serviço","Documentação","Outro"].index(row["categoria"] or "Processo"))
                severidade = st.selectbox("Severidade", ["Baixa","Média","Alta","Crítica"], index=["Baixa","Média","Alta","Crítica"].index(row["severidade"] or "Baixa"))
                descricao = st.text_area("Descrição", value=row["descricao"] or "", height=150)
                colA, colB, colC, colD = st.columns(4)
                with colA:
                    if st.button("💾 Salvar", disabled=not st.session_state.get("auth_ok")):
                        with get_engine().begin() as c2:
                            c2.execute(text("""
                                UPDATE rnc SET solicitante=:s, pep=:p, categoria=:c, severidade=:sev, descricao=:d
                                WHERE rnc_num=:n
                            """), {"s": solicitante, "p": pep or None, "c": categoria, "sev": severidade, "d": descricao, "n": rnc_num})
                        st.success("Atualizado.")
                with colB:
                    enc_obs = st.text_input("Obs. Encerramento", value=row["encerramento_obs"] or "")
                    if st.button("✅ Encerrar", disabled=not st.session_state.get("auth_ok")):
                        with get_engine().begin() as c2:
                            c2.execute(text("UPDATE rnc SET status='ENCERRADA', encerramento_obs=:o WHERE rnc_num=:n"),
                                       {"o": enc_obs, "n": rnc_num})
                        st.success("RNC encerrada.")
                with colC:
                    reab_obs = st.text_input("Obs. Reabertura", value=row["reabertura_obs"] or "")
                    if st.button("♻️ Reabrir", disabled=not st.session_state.get("auth_ok")):
                        with get_engine().begin() as c2:
                            c2.execute(text("UPDATE rnc SET status='REABERTA', reabertura_obs=:o WHERE rnc_num=:n"),
                                       {"o": reab_obs, "n": rnc_num})
                        st.success("RNC reaberta.")
                with colD:
                    if st.button("⛔ Cancelar", disabled=not st.session_state.get("auth_ok")):
                        with get_engine().begin() as c2:
                            c2.execute(text("UPDATE rnc SET status='CANCELADA', cancelado=true WHERE rnc_num=:n"),
                                       {"n": rnc_num})
                        st.success("RNC cancelada.")

            with tabs[1]:
                with get_engine().begin() as c3:
                    df_ab = listar_fotos(c3, rnc_num, "abertura")
                    df_en = listar_fotos(c3, rnc_num, "encerramento")
                    df_re = listar_fotos(c3, rnc_num, "reabertura")
                st.write("**Abertura**")
                if not df_ab.empty:
                    st.dataframe(df_ab[["url","created_at"]], use_container_width=True, hide_index=True)
                up1 = st.file_uploader("Adicionar fotos (abertura)", type=["png","jpg","jpeg"], accept_multiple_files=True, key="up_ab")
                if up1 and st.session_state.get("auth_ok"):
                    with get_engine().begin() as c4:
                        for f in up1:
                            add_foto(c4, rnc_num, "abertura", f.read(), f.type)
                st.write("---")
                st.write("**Encerramento**")
                if not df_en.empty:
                    st.dataframe(df_en[["url","created_at"]], use_container_width=True, hide_index=True)
                up2 = st.file_uploader("Adicionar fotos (encerramento)", type=["png","jpg","jpeg"], accept_multiple_files=True, key="up_en")
                if up2 and st.session_state.get("auth_ok"):
                    with get_engine().begin() as c5:
                        for f in up2:
                            add_foto(c5, rnc_num, "encerramento", f.read(), f.type)
                st.write("---")
                st.write("**Reabertura**")
                if not df_re.empty:
                    st.dataframe(df_re[["url","created_at"]], use_container_width=True, hide_index=True)
                up3 = st.file_uploader("Adicionar fotos (reabertura)", type=["png","jpg","jpeg"], accept_multiple_files=True, key="up_re")
                if up3 and st.session_state.get("auth_ok"):
                    with get_engine().begin() as c6:
                        for f in up3:
                            add_foto(c6, rnc_num, "reabertura", f.read(), f.type)

            with tabs[2]:
                if st.button("📄 Gerar PDF"):
                    with get_engine().begin() as c7:
                        rr = c7.execute(text("SELECT * FROM rnc WHERE rnc_num=:n"), {"n": rnc_num}).mappings().first()
                        fotos = {
                            "abertura": listar_fotos(c7, rnc_num, "abertura")["url"].tolist(),
                            "encerramento": listar_fotos(c7, rnc_num, "encerramento")["url"].tolist(),
                            "reabertura": listar_fotos(c7, rnc_num, "reabertura")["url"].tolist(),
                        }
                    pdf = gerar_pdf(dict(rr), fotos)
                    st.download_button("⬇️ Baixar PDF", data=pdf.read(), file_name=f"RNC_{rnc_num}.pdf", mime="application/pdf")

def page_csv():
    st.header("⬇️⬆️ CSV de RNCs")
    if st.button("Exportar CSV de RNCs"):
        with get_engine().begin() as conn:
            df = pd.read_sql(text("SELECT * FROM rnc ORDER BY data_abertura DESC"), conn)
        st.download_button("Baixar RNCs.csv", df.to_csv(index=False).encode("utf-8"), "RNCs.csv", "text/csv")
    st.write("---")
    st.subheader("Importar RNCs (opcional)")
    up = st.file_uploader("CSV com colunas: rnc_num, solicitante, descricao, categoria, severidade, pep, status", type=["csv"])
    if up and st.session_state.get("auth_ok"):
        df = pd.read_csv(up)
        required = {"rnc_num","status"}
        if not required.issubset(set(map(str.lower, df.columns))):
            st.error("CSV inválido. Exige colunas ao menos: rnc_num, status (+ demais campos opcionais).")
        else:
            with get_engine().begin() as conn:
                for _, r in df.iterrows():
                    conn.execute(text("""
                        INSERT INTO rnc(rnc_num, solicitante, descricao, categoria, severidade, pep, status)
                        VALUES (:n,:s,:d,:c,:sev,:p,:st)
                        ON CONFLICT (rnc_num) DO UPDATE SET
                          solicitante=EXCLUDED.solicitante,
                          descricao=EXCLUDED.descricao,
                          categoria=EXCLUDED.categoria,
                          severidade=EXCLUDED.severidade,
                          pep=EXCLUDED.pep,
                          status=EXCLUDED.status
                    """), {
                        "n": r.get("rnc_num"),
                        "s": r.get("solicitante"),
                        "d": r.get("descricao"),
                        "c": r.get("categoria"),
                        "sev": r.get("severidade"),
                        "p": r.get("pep"),
                        "st": r.get("status") or "ABERTA"
                    })
            st.success("Importação concluída.")

def page_peps():
    st.header("🏷️ PEPs")
    with get_engine().begin() as conn:
        df = pd.read_sql(text("SELECT * FROM peps ORDER BY pep"), conn)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.subheader("Importar CSV de PEPs")
    up = st.file_uploader("CSV com colunas: pep, descricao", type=["csv"], key="peps_csv")
    if up and st.session_state.get("auth_ok"):
        df_in = pd.read_csv(up)
        if not {"pep","descricao"}.issubset(set(map(str.lower, df_in.columns))):
            st.error("CSV inválido. Deve conter colunas: pep, descricao")
        else:
            with get_engine().begin() as conn:
                for _, r in df_in.iterrows():
                    conn.execute(text("""
                        INSERT INTO peps(pep, descricao) VALUES (:p,:d)
                        ON CONFLICT (pep) DO UPDATE SET descricao=EXCLUDED.descricao
                    """), {"p": r.get("pep"), "d": r.get("descricao")})
            st.success("PEPs importados/atualizados.")
    st.download_button("⬇️ Baixar modelo (exemplos/peps_exemplo.csv)",
                       data="pep,descricao\nC016598,Projeto exemplo\nC018199,Outro exemplo\n".encode("utf-8"),
                       file_name="peps_exemplo.csv", mime="text/csv")

# -------------- Main --------------

def main():
    st.title("RNC App — v08 (Supabase + Streamlit)")
    init_db_if_needed()
    auth_block()
    logo_uploader()

    pagina = st.sidebar.radio("Navegação", ["➕ Nova RNC","🔎 Consultar/Editar","🏷️ PEPs","⬇️⬆️ CSV","ℹ️ Status"], index=0)
    if pagina == "➕ Nova RNC":
        page_nova_rnc()
    elif pagina == "🔎 Consultar/Editar":
        page_consultar()
    elif pagina == "🏷️ PEPs":
        page_peps()
    elif pagina == "⬇️⬆️ CSV":
        page_csv()
    else:
        page_status()

if __name__ == "__main__":
    main()
