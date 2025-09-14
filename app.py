
import os, io, json, uuid, traceback
from datetime import datetime, date
from typing import List, Dict, Any, Optional

import streamlit as st
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# -------- Supabase (apenas Storage) --------
try:
    from supabase import create_client
except Exception:
    create_client = None

BUILD_TAG = "v10-storage-only"

st.set_page_config(page_title=f"RNC — {BUILD_TAG}", page_icon="📝", layout="wide")

# -------- Secrets --------
SUPABASE_URL    = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY    = os.getenv("SUPABASE_KEY", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "RNC-FOTOS")
QUALITY_PASS    = os.getenv("QUALITY_PASS", "qualidade123")

# -------- Caminhos no bucket --------
DATA_PATH   = "rnc_app/data.json"   # lista de RNCs
PEP_PATH    = "rnc_app/peps.json"   # lista de PEPs (lista simples de strings)
LOGO_PATH   = "rnc_app/logo.bin"    # imagem da logo para PDF

# -------- Cliente Supabase + bucket --------
def get_bucket():
    if not (SUPABASE_URL and SUPABASE_KEY and create_client):
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

# -------- Helpers Storage --------
def storage_download_text(key: str) -> Optional[str]:
    if not bucket: return None
    try:
        res = bucket.download(key)
        return res.decode("utf-8") if hasattr(res, "decode") else res
    except Exception:
        return None

def storage_download_bytes(key: str) -> Optional[bytes]:
    if not bucket: return None
    try:
        res = bucket.download(key)
        return res if isinstance(res, (bytes, bytearray)) else None
    except Exception:
        return None

def storage_upload_bytes(key: str, data: bytes, content_type: str) -> bool:
    if not bucket: return False
    try:
        bucket.upload(key, data, {"content-type": content_type}, upsert=True)
        return True
    except Exception as e:
        st.error(f"Falha ao subir {key}: {e}")
        return False

def storage_delete(key: str) -> bool:
    if not bucket: return False
    try:
        bucket.remove([key]); return True
    except Exception:
        return False

# -------- JSON helpers --------
def load_json_list(key: str) -> List[Dict[str, Any]]:
    txt = storage_download_text(key)
    if not txt: return []
    try:
        data = json.loads(txt)
        return data if isinstance(data, list) else []
    except Exception:
        return []

def save_json_list(key: str, data: List[Dict[str, Any]]) -> bool:
    try:
        raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        return storage_upload_bytes(key, raw, "application/json")
    except Exception:
        return False

# -------- Dados principais --------
def load_all_rncs() -> List[Dict[str, Any]]:
    return load_json_list(DATA_PATH)

def save_all_rncs(lst: List[Dict[str, Any]]) -> bool:
    return save_json_list(DATA_PATH, lst)

def load_peps() -> List[str]:
    txt = storage_download_text(PEP_PATH)
    if not txt: return []
    try:
        data = json.loads(txt)
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    return []

def save_peps(codes: List[str]) -> bool:
    try:
        raw = json.dumps(codes, ensure_ascii=False, indent=2).encode("utf-8")
        return storage_upload_bytes(PEP_PATH, raw, "application/json")
    except Exception:
        return False

def get_logo() -> Optional[bytes]:
    return storage_download_bytes(LOGO_PATH)

def set_logo(image_bytes: bytes) -> bool:
    return storage_upload_bytes(LOGO_PATH, image_bytes, "image/png")

def clear_logo() -> bool:
    return storage_delete(LOGO_PATH)

# -------- Numeração (ano + seq do JSON) --------
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

# -------- Upload de fotos --------
def upload_photos(files, rnc_num: str, tipo: str):
    out = []
    if not files: return out
    if not bucket:
        st.error("Supabase Storage não configurado.")
        return out
    for f in files:
        try:
            ext = os.path.splitext(f.name)[1].lower() or ".jpg"
            key = f"rnc_app/fotos/{rnc_num}/{tipo}/{uuid.uuid4().hex}{ext}"
            data = f.read(); f.seek(0)
            bucket.upload(key, data, {"content-type": f.type or "image/jpeg"}, upsert=True)
            url = bucket.get_public_url(key)
            out.append({"url": url, "path": key, "filename": f.name, "mimetype": f.type or "image/jpeg", "tipo": tipo})
        except Exception as e:
            st.error(f"Falha ao subir {f.name}: {e}")
    return out

# -------- PDF --------
def generate_pdf(r: Dict[str, Any]):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    y = H - 30

    logo = get_logo()
    if logo:
        try:
            c.drawImage(ImageReader(io.BytesIO(logo)), 30, y-25, width=120, height=25, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

    def line(label, val):
        nonlocal y
        try:
            c.setFont("Helvetica-Bold", 10); c.drawString(30, y, f"{label}: ")
            c.setFont("Helvetica", 10); c.drawString(160, y, str(val or "")); y -= 14
        except Exception:
            y -= 14

    def block(title, textv):
        nonlocal y
        try:
            c.setFont("Helvetica-Bold", 11); c.drawString(30, y, title); y -= 12
            c.setFont("Helvetica", 10)
            for ln in str(textv or "").splitlines():
                c.drawString(30, y, ln[:110]); y -= 12
                if y < 80: c.showPage(); y = H - 30
            y -= 6
        except Exception:
            y -= 6

    c.setFont("Helvetica-Bold", 14)
    c.drawString(170, y-10, "RNC - RELATÓRIO DE NÃO CONFORMIDADE"); y -= 40

    line("RNC Nº", r.get("rnc_num"))
    line("Data", str(r.get("data") or "")[:10])
    line("Emitente", r.get("emitente"))
    line("Área/Local", r.get("area"))
    line("PEP", r.get("pep"))
    line("Categoria", r.get("categoria"))
    line("Severidade", r.get("severidade"))
    line("Causador / Processo / Origem", f"{r.get('causador','')} / {r.get('processo','')} / {r.get('origem','')}")
    line("Responsável", r.get("responsavel"))

    block("Título", r.get("titulo"))
    block("Descrição da não conformidade", r.get("descricao"))
    block("Referências", r.get("referencias"))

    if (r.get("encerrada_em") or r.get("encerramento_desc") or r.get("eficacia")):
        block("Encerramento (observações / descrição / eficácia)",
              f"{r.get('encerramento_obs','')}\n{r.get('encerramento_desc','')}\nEficácia: {r.get('eficacia','')}")
    if (r.get("reaberta_em") or r.get("reabertura_desc") or r.get("reabertura_motivo")):
        block("Reabertura (motivo / descrição)",
              f"{r.get('reabertura_motivo','')}\n{r.get('reabertura_desc','')}")
    if r.get("status") == "Cancelada":
        block("Cancelamento", f"Motivo: {r.get('cancelamento_motivo','')}")

    c.showPage(); c.save()
    buf.seek(0)
    return buf.read()

# -------- Auth Qualidade --------
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

    with st.sidebar.expander("🖼️ Logo (PDF)"):
        up = st.file_uploader("Enviar logo (PNG/JPG)", type=["png","jpg","jpeg"], key="uplogo")
        if up is not None:
            set_logo(up.getbuffer().tobytes())
            st.success("Logo atualizada.")
        if st.button("Remover logo"):
            if clear_logo(): st.warning("Logo removida.")

auth_box()

# -------- UI --------
menu = st.sidebar.radio("Menu", ["➕ Nova RNC", "🔎 Consultar/Editar", "🏷️ PEPs", "⬇️⬆️ CSV", "ℹ️ Status"])

# ➕ Nova RNC
if menu == "➕ Nova RNC":
    st.title(f"Nova RNC — {BUILD_TAG}")
    with st.form("form_rnc"):
        col0, col1, col2 = st.columns(3)
        emitente = col0.text_input("Emitente")
        data_insp = col1.date_input("Data", value=date.today())
        col2.text_input("RNC Nº (gerado ao salvar)", value="(automático)", disabled=True)

        area = st.text_input("Área/Local")
        categoria = st.selectbox("Categoria", ["Segurança","Qualidade","Meio Ambiente","Operação","Manutenção","Outros"])
        severidade = st.selectbox("Severidade", ["Baixa","Média","Alta","Crítica"])

        peps = load_peps()
        pep = st.selectbox("PEP (código — descrição)", options=[""] + peps)

        causador = st.selectbox("Causador", ["Solda","Pintura","Engenharia","Fornecedor","Cliente","Caldeiraria","Usinagem","Planejamento","Qualidade","RH","Outros"])
        processo = st.selectbox("Processo envolvido", ["Comercial","Compras","Planejamento","Recebimento","Produção","Inspeção Final","Segurança","Meio Ambiente","5S","RH","Outros"])
        origem = st.selectbox("Origem", ["Pintura","Orçamento","Usinagem","Almoxarifado","Solda","Montagem","Cliente","Expedição","Preparação","RH","Outros"])

        titulo = st.text_input("Título")
        descricao = st.text_area("Descrição da não conformidade", height=160)
        referencias = st.text_area("Referências", height=80)

        fotos_ab = st.file_uploader("Fotos da abertura", type=["jpg","jpeg","png"], accept_multiple_files=True)

        submitted = st.form_submit_button("Salvar RNC")

    if submitted:
        if not is_quality():
            st.error("Somente Qualidade pode salvar. Faça login na barra lateral.")
        elif not bucket:
            st.error("Supabase Storage não configurado.")
        else:
            rncs = load_all_rncs()
            rnc_num = next_rnc_num(rncs)
            fotos = upload_photos(fotos_ab or [], rnc_num, "abertura")
            novo = {
                "id": uuid.uuid4().hex,
                "data": str(datetime.combine(data_insp, datetime.min.time())),
                "rnc_num": rnc_num,
                "emitente": emitente, "area": area, "pep": pep, "titulo": titulo,
                "responsavel": "", "descricao": descricao, "referencias": referencias,
                "causador": causador, "processo": processo, "origem": origem,
                "severidade": severidade, "categoria": categoria, "acoes": "",
                "status": "Aberta",
                "fotos_abertura": fotos, "fotos_encerramento": [], "fotos_reabertura": []
            }
            rncs.insert(0, novo)
            if save_all_rncs(rncs):
                st.success(f"RNC salva! Nº {rnc_num}")
            else:
                st.error("Falha ao salvar RNC.")

# 🔎 Consultar/Editar
elif menu == "🔎 Consultar/Editar":
    st.title("Consultar / Editar RNCs")
    rncs = load_all_rncs()
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
            "categoria": r.get("categoria",""),
            "severidade": r.get("severidade",""),
            "status": r.get("status",""),
        } for r in rncs])
        st.dataframe(df, use_container_width=True, height=320)
        sel = st.selectbox("Escolha a RNC", options=df["id"].tolist())
        r = next(x for x in rncs if x["id"] == sel)

        st.subheader(f"RNC {r['rnc_num']} — {r['status']}")
        st.write(f"**Título:** {r.get('titulo','')}")
        st.write(f"**Descrição:** {r.get('descricao','')}")
        st.write(f"**Referências:** {r.get('referencias','')}")

        cols = st.columns(4)
        for i, fo in enumerate((r.get("fotos_abertura") or [])[:8]):
            with cols[i % 4]:
                st.image(fo.get("url") or fo.get("path"), use_column_width=True, caption="Abertura")
        for i, fo in enumerate((r.get("fotos_encerramento") or [])[:8]):
            with cols[i % 4]:
                st.image(fo.get("url") or fo.get("path"), use_column_width=True, caption="Encerramento")
        for i, fo in enumerate((r.get("fotos_reabertura") or [])[:8]):
            with cols[i % 4]:
                st.image(fo.get("url") or fo.get("path"), use_column_width=True, caption="Reabertura")

        st.markdown("---")
        if is_quality():
            with st.expander("✅ Encerrar RNC"):
                encerr_por = st.text_input("Encerrada por", key=f"encpor_{r['id']}")
                encerr_obs = st.text_area("Observações", key=f"encobs_{r['id']}")
                encerr_desc = st.text_area("Descrição do fechamento", key=f"encdesc_{r['id']}")
                eficacia = st.selectbox("Eficácia", ["A verificar","Eficaz","Não eficaz"], key=f"ef_{r['id']}")
                fotos_enc = st.file_uploader("Evidências (fotos)", type=["jpg","jpeg","png"], accept_multiple_files=True, key=f"encf_{r['id']}")
                if st.button("Encerrar agora", key=f"encok_{r['id']}"):
                    r["status"] = "Encerrada"
                    r["encerrada_em"] = str(datetime.now())
                    r["encerrada_por"] = encerr_por
                    r["encerramento_obs"] = encerr_obs
                    r["encerramento_desc"] = encerr_desc
                    r["eficacia"] = eficacia
                    r["fotos_encerramento"] = (r.get("fotos_encerramento") or []) + upload_photos(fotos_enc or [], r["rnc_num"], "encerramento")
                    if save_all_rncs(rncs): st.success("RNC encerrada.")

            with st.expander("♻️ Reabrir RNC"):
                reab_por = st.text_input("Reaberta por", key=f"repor_{r['id']}")
                reab_motivo = st.text_input("Motivo", key=f"remot_{r['id']}")
                reab_desc = st.text_area("Descrição da reabertura", key=f"redesc_{r['id']}")
                fotos_rea = st.file_uploader("Fotos (opcional)", type=["jpg","jpeg","png"], accept_multiple_files=True, key=f"ref_{r['id']}")
                if st.button("Reabrir agora", key=f"reok_{r['id']}"):
                    r["status"] = "Em ação"
                    r["reaberta_em"] = str(datetime.now())
                    r["reaberta_por"] = reab_por
                    r["reabertura_motivo"] = reab_motivo
                    r["reabertura_desc"] = reab_desc
                    r["fotos_reabertura"] = (r.get("fotos_reabertura") or []) + upload_photos(fotos_rea or [], r["rnc_num"], "reabertura")
                    if save_all_rncs(rncs): st.success("RNC reaberta.")

            with st.expander("🚫 Cancelar RNC"):
                c_por = st.text_input("Cancelada por", key=f"canpor_{r['id']}")
                c_mot = st.text_area("Motivo", key=f"canmot_{r['id']}")
                if st.button("Cancelar", key=f"canok_{r['id']}"):
                    r["status"] = "Cancelada"
                    r["cancelada_em"] = str(datetime.now())
                    r["cancelada_por"] = c_por
                    r["cancelamento_motivo"] = c_mot
                    if save_all_rncs(rncs): st.success("RNC cancelada.")

            with st.expander("🗑️ Excluir permanentemente"):
                conf = st.text_input("Digite CONFIRMAR para excluir", key=f"del_{r['id']}")
                if st.button("Excluir RNC", key=f"delok_{r['id']}"):
                    if conf.strip().upper() == "CONFIRMAR":
                        rncs = [x for x in rncs if x["id"] != r["id"]]
                        if save_all_rncs(rncs): st.success("RNC excluída.")
                    else:
                        st.warning("Digite CONFIRMAR exatamente.")
        else:
            st.info("Entre como Qualidade para encerrar/reabrir/cancelar/excluir.")

        st.download_button("📄 Baixar PDF desta RNC", data=generate_pdf(r), file_name=f"RNC_{r['rnc_num']}.pdf", mime="application/pdf")

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
    rncs = load_all_rncs()
    df = pd.DataFrame(rncs)
    st.download_button("⬇️ Exportar CSV", data=df.to_csv(index=False).encode("utf-8-sig"), file_name="rnc_export_v10.csv", mime="text/csv")

    st.subheader("Importar CSV de RNCs")
    up = st.file_uploader("Selecione um CSV (sem 'id', app gera).", type=["csv"])
    if up and st.button("Importar agora"):
        try:
            imp = pd.read_csv(up)
        except Exception:
            up.seek(0); imp = pd.read_csv(up, sep=";")
        inserted = 0
        rncs = load_all_rncs()
        for _, r in imp.fillna("").iterrows():
            num = str(r.get("rnc_num","")).strip() or next_rnc_num(rncs)
            novo = dict(r); novo["id"] = uuid.uuid4().hex; novo["rnc_num"] = num
            rncs.insert(0, novo); inserted += 1
        if save_all_rncs(rncs):
            st.success(f"Importação concluída. Inseridos: {inserted}.")

# ℹ️ Status
elif menu == "ℹ️ Status":
    st.title("Status do App")
    ok = bool(bucket)
    st.write(f"**Build:** {BUILD_TAG}")
    st.write("**Supabase Storage:** " + ("OK" if ok else "NÃO CONFIGURADO"))
    st.code(f"SUPABASE_URL={'set' if bool(SUPABASE_URL) else 'not set'}; SUPABASE_KEY={'set' if bool(SUPABASE_KEY) else 'not set'}; SUPABASE_BUCKET={SUPABASE_BUCKET}")
