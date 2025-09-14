
import os, json, uuid
from datetime import datetime, date
import streamlit as st
import pandas as pd

try:
    from supabase import create_client
except Exception:
    create_client = None

st.set_page_config(page_title="RNC App v09-min", page_icon="📝", layout="wide")

SUPABASE_URL    = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY    = os.getenv("SUPABASE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "RNC-FOTOS")
QUALITY_PASS    = os.getenv("QUALITY_PASS", "qualidade123")
USE_LOCAL       = os.getenv("USE_LOCAL_STORAGE", "0") == "1"

DATA_PATH = "rnc_app/data.json"
LOCAL_ROOT = ".rnc_data"
LOCAL_DATA = os.path.join(LOCAL_ROOT, "data.json")

def ensure_local():
    os.makedirs(LOCAL_ROOT, exist_ok=True)

def get_bucket():
    if USE_LOCAL or not (SUPABASE_URL and SUPABASE_KEY and create_client):
        return None
    try:
        sb = create_client(SUPABASE_URL, SUPABASE_KEY)
        try:
            sb.storage.create_bucket(SUPABASE_BUCKET, public=True)
        except Exception:
            pass
        return sb.storage.from_(SUPABASE_BUCKET)
    except Exception:
        return None

bucket = get_bucket()

def read_text():
    if USE_LOCAL:
        ensure_local()
        if os.path.exists(LOCAL_DATA):
            return Path(LOCAL_DATA).read_text(encoding="utf-8")
        return None
    if not bucket:
        return None
    try:
        res = bucket.download(DATA_PATH)
        return res.decode("utf-8") if hasattr(res, "decode") else res
    except Exception:
        return None

def write_text(text: str):
    if USE_LOCAL:
        ensure_local()
        Path(LOCAL_DATA).write_text(text, encoding="utf-8")
        return True
    if not bucket:
        return False
    try:
        bucket.upload(DATA_PATH, text.encode("utf-8"),
                      {"content-type": "application/json"}, upsert=True)
        return True
    except Exception as e:
        st.error(f"Falha ao salvar dados: {e}")
        return False

def load_rncs():
    txt = read_text()
    if not txt:
        return []
    try:
        data = json.loads(txt)
        return data if isinstance(data, list) else []
    except Exception:
        return []

def save_rncs(lst):
    try:
        return write_text(json.dumps(lst, ensure_ascii=False, indent=2))
    except Exception:
        return False

def next_rnc_num(rncs):
    y = datetime.now().year
    prefix = f"{y}-"
    seqs = []
    for r in rncs:
        num = str(r.get("rnc_num", ""))
        if num.startswith(prefix):
            try:
                seqs.append(int(num.split("-")[1]))
            except:
                pass
    nxt = (max(seqs) + 1) if seqs else 1
    return f"{y}-{nxt:03d}"

def is_quality():
    return st.session_state.get("is_quality", False)

def auth_box():
    with st.sidebar.expander("🔐 Acesso Qualidade"):
        pwd = st.text_input("Senha", type="password")
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

auth_box()

menu = st.sidebar.radio("Menu", ["➕ Nova RNC", "🔎 Consultar", "⬇️⬆️ CSV", "ℹ️ Status"])

if menu == "➕ Nova RNC":
    st.title("Nova RNC")
    with st.form("form_rnc_min"):
        emitente = st.text_input("Emitente")
        data_insp = st.date_input("Data", value=date.today())
        titulo = st.text_input("Título")
        descricao = st.text_area("Descrição", height=160)
        submitted = st.form_submit_button("Salvar RNC")

    if submitted:
        if not is_quality():
            st.error("Somente Qualidade pode salvar. Faça login.")
        else:
            rncs = load_rncs()
            rnc_num = next_rnc_num(rncs)
            novo = {
                "id": uuid.uuid4().hex,
                "data": str(datetime.combine(data_insp, datetime.min.time())),
                "rnc_num": rnc_num,
                "emitente": emitente,
                "titulo": titulo,
                "descricao": descricao,
                "status": "Aberta",
            }
            rncs.insert(0, novo)
            if save_rncs(rncs):
                st.success(f"RNC salva! Nº {rnc_num}")
            else:
                st.error("Falha ao salvar RNC.")

elif menu == "🔎 Consultar":
    st.title("Consultar RNCs")
    rncs = load_rncs()
    if not rncs:
        st.info("Sem registros.")
    else:
        df = pd.DataFrame([{
            "id": r["id"], "data": r.get("data","")[:10],
            "rnc_num": r.get("rnc_num",""),
            "titulo": r.get("titulo",""),
            "emitente": r.get("emitente",""),
            "status": r.get("status","")
        } for r in rncs])
        st.dataframe(df, use_container_width=True, height=340)

elif menu == "⬇️⬆️ CSV":
    st.title("Importar / Exportar CSV de RNCs")
    rncs = load_rncs()
    df = pd.DataFrame(rncs)
    st.download_button("⬇️ Exportar CSV",
                       data=df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="rnc_export_min.csv",
                       mime="text/csv")

elif menu == "ℹ️ Status":
    st.title("Status do App")
    st.write("Armazenamento: " +
             ("LOCAL" if USE_LOCAL else ("Supabase" if bucket else "Não configurado")))
