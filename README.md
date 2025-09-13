# 🧰 RNC App — Qualidade (v08)

Sistema completo para **Registro de Não Conformidades (RNC)** com integração ao **Supabase** e interface no **Streamlit**.

---

## ⚙️ Funcionalidades
- Login com senha (QUALITY_PASS)
- Criação de RNC com numeração automática (ex: 2025-001)
- Upload de fotos em etapas (abertura, encerramento, reabertura) no Supabase Storage
- Cadastro e importação de PEPs
- Exportação / importação de RNCs via CSV
- Geração de relatório PDF com logo
- Tela de status do sistema (banco, storage, secrets)

---

## 🚀 Como publicar no Streamlit Cloud
1. Crie um repositório no GitHub e envie estes arquivos para a raiz:
   - `app.py`
   - `requirements.txt`
   - `runtime.txt`
   - `README.md` (opcional, para exibição no GitHub)

2. No painel do [Streamlit Cloud](https://share.streamlit.io):
   - Clique em **New app**
   - Selecione seu repositório e arquivo principal `app.py`

3. Em **Settings → Secrets**, cole o seguinte (substitua com os dados do seu projeto Supabase):
   ```toml
   SUPABASE_URL="https://SEU_ID.supabase.co"
   SUPABASE_KEY="SUA_ANON_KEY"
   SUPABASE_DB_URL="postgresql+psycopg2://postgres:SUA_SENHA_URLENCODE@db.SEU_ID.supabase.co:6543/postgres?sslmode=require"
   SUPABASE_BUCKET="RNC-FOTOS"
   QUALITY_PASS="qualidade123"
   INIT_DB="true"
   ```

   ⚠️ Observações:
   - A senha do Postgres deve estar **URL-encodada** (`@` → `%40`, etc)
   - Pode deixar `+psycopg2` no URL — o app troca automaticamente para `+psycopg` (psycopg3)

4. Clique em **Deploy**.
5. Depois que as tabelas forem criadas, altere `INIT_DB` para `"false"` nos secrets para evitar recriações.

---

## 💡 Dicas
- Use a aba **ℹ️ Status** para testar a conexão do banco e do storage
- Se quiser personalizar o PDF, envie sua logo na barra lateral do app
- CSVs de exemplo podem ser gerados na aba de exportação

---

🛠 Desenvolvido para inspeções de qualidade integradas com Supabase + Streamlit.