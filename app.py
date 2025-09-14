
import os, json, uuid
from datetime import datetime, date
from typing import List, Dict, Any, Optional

import streamlit as st
import pandas as pd
import requests

BUILD_TAG = "v10-fastdeploy (REST-only)"

st.set_page_config(page_title=f"RNC — {BUILD_TAG}", page_icon="📝", layout="wide")

# -------- Secrets --------
SUPABASE_URL    = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY    = os.getenv("SUPABASE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "RNC-FOTOS")
QUALITY_PASS    = os.getenv("QUALITY_PASS", "qualidade123")

# Caminhos dentro do bucket (dois JSONs fixos)
DATA_PATH = "rnc_app/data.json"
PEP_PATH  = "rnc_app/peps.json"

def bucket_public_base() -> str:
    # URL pública (bucket deve ser Public)
    return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}"

def bucket_api_base() -> str:
    # API REST (autenticada via anon key)
    return f"{SUPABASE_URL}/storage/v1/object/{SUPABASE_BUCKET}"

def headers_auth():
    return {"Authorization": f"Bearer {SUPABASE_KEY}"}

# --------- JSON helpers (REST direto) ---------
def read_text_via_rest(key: str) -> Optional[str]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    url = f"{bucket_api_base()}/{key}"
    try:
        r = requests.get(url, headers=headers_auth(), timeout=15)
        if r.status_code == 200:
            try:
                return r.content.decode("utf-8")
            except Exception:
                return r.text
        else:
            return None
    except Exception:
        return None

def write_text_via_rest(key: str, text: str, content_type="application/json") -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    url = f"{bucket_api_base()}/{key}?upsert=true"
    try:
        r = requests.put(url, headers={**headers_auth(), "Content-Type": content_type}, data=text.encode("utf-8"), timeout=20)
        return r.status_code in (200, 201)
    except Exception:
        return False

def load_rncs() -> List[Dict[str, Any]]:
    txt = read_text_via_rest(DATA_PATH)
    if not txt:
        return []
    try:
        data = json.loads(txt)
        return data if isinstance(data, list) else []
    except Exception:
        return []

def save_rncs(lst: List[Dict[str, Any]]) -> bool:
    try:
        return write_text_via_rest(DATA_PATH, json.dumps(lst, ensure_ascii=False, indent=2))
    except Exception:
        return False

def load_peps() -> List[str]:
    txt = read_text_via_rest(PEP_PATH)
    if not txt: return []
    try:
        data = json.loads(txt)
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    return []

def save_peps(lst: List[str]) -> bool:
    try:
        return write_text_via_rest(PEP_PATH, json.dumps(lst, ensure_ascii=False, indent=2))
    except Exception:
        return False

# -------- Fotos (REST) --------
def upload_photos(files, rnc_num: str, tipo: str):
    out = []
    if not files: return out
    if not SUPABASE_URL or not SUPABASE_KEY:
        st.error("Supabase não configurado.")
        return out
    for f in files:
        ext = os.path.splitext(f.name)[1].lower() or ".jpg"
        key = f"rnc_app/fotos/{rnc_num}/{tipo}/{uuid.uuid4().hex}{ext}"
        url = f"{bucket_api_base()}/{key}?upsert=true"
        data = f.read(); f.seek(0)
        try:
            r = requests.put(url, headers={**headers_auth(), "Content-Type": f.type or "image/jpeg"}, data=data, timeout=30)
            if r.status_code in (200,201):
                public_url = f"{bucket_public_base()}/{key}"
                out.append({"url": public_url, "path": key, "filename": f.name, "mimetype": f.type or "image/jpeg", "tipo": tipo})
            else:
                st.error(f"Falha ao subir {f.name} ({r.status_code})")
        except Exception as e:
            st.error(f"Falha ao subir {f.name}: {e}")
    return out

# -------- Numeração simples (ano + seq no JSON) --------
def next_rnc_num(rncs: List[Dict[str, Any]]) -> str:
    y = datetime.now().year
    prefix = f"{y}-"
    seqs = []
    for r in rncs:
        num = str(r.get("rnc_num",""))
        if num.startswith(prefix):
            try: seqs.append(int(num.split("-")[1]))
            except: pass
    nxt = (max(seqs) + 1) if seqs else 1
    return f"{y}-{nxt:03d}"

# -------- Auth --------
def is_quality() -> bool:
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

# -------- UI --------
menu = st.sidebar.radio("Menu", ["➕ Nova RNC", "🔎 Consultar", "🏷️ PEPs", "⬇️⬆️ CSV", "ℹ️ Status"])

# ➕ Nova RNC
if menu == "➕ Nova RNC":
    st.title(f"Nova RNC — {BUILD_TAG}")
    with st.form("form_rnc"):
        emitente = st.text_input("Emitente")
        data_insp = st.date_input("Data", value=date.today())
        area = st.text_input("Área/Local")

        peps = load_peps()
        pep = st.selectbox("PEP (código — descrição)", options=[""] + peps)

        titulo = st.text_input("Título")
        descricao = st.text_area("Descrição", height=160)

        fotos = st.file_uploader("Fotos (opcional, múltiplas)", type=["jpg","jpeg","png"], accept_multiple_files=True)

        submitted = st.form_submit_button("Salvar RNC")

    if submitted:
        if not is_quality():
            st.error("Somente Qualidade pode salvar. Faça login na barra lateral.")
        elif not SUPABASE_URL or not SUPABASE_KEY:
            st.error("Supabase não configurado (ver Secrets).")
        else:
            rncs = load_rncs()
            rnc_num = next_rnc_num(rncs)
            fotos_meta = upload_photos(fotos or [], rnc_num, "abertura")
            novo = {
                "id": uuid.uuid4().hex,
                "data": str(datetime.combine(data_insp, datetime.min.time())),
                "rnc_num": rnc_num,
                "emitente": emitente, "area": area, "pep": pep,
                "titulo": titulo, "descricao": descricao,
                "status": "Aberta",
                "fotos_abertura": fotos_meta
            }
            rncs.insert(0, novo)
            if save_rncs(rncs):
                st.success(f"RNC salva! Nº {rnc_num}")
            else:
                st.error("Falha ao salvar RNC.")

# 🔎 Consultar
elif menu == "🔎 Consultar":
    st.title("Consultar RNCs")
    rncs = load_rncs()
    if not rncs:
        st.info("Sem registros.")
    else:
        df = pd.DataFrame([{
            "id": r["id"],
            "data": r.get("data","")[:10],
            "rnc_num": r.get("rnc_num",""),
            "titulo": r.get("titulo",""),
            "emitente": r.get("emitente",""),
            "area": r.get("area",""),
            "pep": r.get("pep",""),
            "status": r.get("status",""),
        } for r in rncs])
        st.dataframe(df, use_container_width=True, height=320)
        sel = st.selectbox("Escolha a RNC", options=df["id"].tolist())
        r = next(x for x in rncs if x["id"] == sel)
        st.subheader(f"RNC {r['rnc_num']} — {r['status']}")
        st.write(f"**Título:** {r.get('titulo','')}")
        st.write(f"**Descrição:** {r.get('descricao','')}")
        for fo in (r.get("fotos_abertura") or [])[:12]:
            st.image(fo.get("url") or fo.get("path"), use_column_width=True)

# 🏷️ PEPs
elif menu == "🏷️ PEPs":
    st.title("Gerenciar PEPs")
    lst = load_peps()
    st.write(f"Total: {len(lst)} PEP(s)")
    st.dataframe(pd.DataFrame({"code": lst}), use_container_width=True, height=300)

    st.subheader("Importar PEPs por CSV")
    up = st.file_uploader("CSV com coluna 'code' (ou 1 PEP por linha).", type=["csv"], key="up_pep")
    if up and st.button("Importar agora"):
        try:
            df = pd.read_csv(up)
            if 'code' in df.columns:
                vals = [str(x) for x in df['code'].fillna('') if str(x).strip()]
            else:
                up.seek(0)
                import csv, io as _io
                reader = csv.reader(_io.StringIO(up.getvalue().decode('utf-8')))
                vals = [row[0] for row in reader if row and str(row[0]).strip()]
        except Exception:
            up.seek(0)
            import csv, io as _io
            reader = csv.reader(_io.StringIO(up.getvalue().decode('utf-8')))
            vals = [row[0] for row in reader if row and str(row[0]).strip()]
        s = set(lst)
        for v in vals: s.add(v.strip())
        if save_peps(sorted(s)):
            st.success(f"Importados {len(vals)} PEPs.")

    st.subheader("Adicionar manualmente")
    many = st.text_area("Um PEP por linha (código — descrição).", height=120)
    if st.button("Adicionar em lote"):
        s = set(lst)
        for ln in (many or "").splitlines():
            v = ln.strip()
            if v: s.add(v)
        if save_peps(sorted(s)):
            st.success("PEPs adicionados.")

# ⬇️⬆️ CSV
elif menu == "⬇️⬆️ CSV":
    st.title("Importar / Exportar CSV de RNCs")
    rncs = load_rncs()
    df = pd.DataFrame(rncs)
    st.download_button("⬇️ Exportar CSV", data=df.to_csv(index=False).encode("utf-8-sig"),
                       file_name="rnc_export_fastdeploy.csv", mime="text/csv")

    st.subheader("Importar CSV de RNCs")
    up = st.file_uploader("Selecione um CSV (sem 'id').", type=["csv"])
    if up and st.button("Importar agora"):
        try:
            imp = pd.read_csv(up)
        except Exception:
            up.seek(0); imp = pd.read_csv(up, sep=";")
        inserted = 0
        rncs = load_rncs()
        for _, r in imp.fillna("").iterrows():
            num = str(r.get("rnc_num","")).strip() or next_rnc_num(rncs)
            novo = dict(r); novo["id"] = uuid.uuid4().hex; novo["rnc_num"] = num
            rncs.insert(0, novo); inserted += 1
        if save_rncs(rncs):
            st.success(f"Importação concluída. Inseridos: {inserted}.")

# ℹ️ Status
elif menu == "ℹ️ Status":
    st.title("Status do App")
    ok = bool(SUPABASE_URL and SUPABASE_KEY)
    st.write(f"**Build:** {BUILD_TAG}")
    st.write("**Supabase REST:** " + ("OK (verifique bucket 'public')" if ok else "Não configurado"))
    st.code(f"SUPABASE_URL={'set' if bool(SUPABASE_URL) else 'not set'}; SUPABASE_KEY={'set' if bool(SUPABASE_KEY) else 'not set'}; SUPABASE_BUCKET={SUPABASE_BUCKET}")
