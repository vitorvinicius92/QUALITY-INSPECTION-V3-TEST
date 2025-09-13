# RNC App v08 — Supabase + Streamlit

## Como rodar local
1. Python 3.11+
2. `pip install -r requirements.txt`
3. Crie um arquivo `.streamlit/secrets.toml` com:
   ```toml
   SUPABASE_URL = "https://SEU_ID.supabase.co"
   SUPABASE_KEY = "SUA_ANON_KEY"
   SUPABASE_DB_URL = "postgresql+psycopg2://postgres:SUA_SENHA_URLENCODE@db.SEU_ID.supabase.co:6543/postgres?sslmode=require"
   SUPABASE_BUCKET = "RNC-FOTOS"
   QUALITY_PASS = "qualidade123"
   INIT_DB = "true"
   ```
4. `streamlit run app.py`

## Streamlit Cloud
- Envie `app.py`, `requirements.txt`.
- Em *Settings → Secrets*, cole as chaves acima. Após criar o banco uma vez, mude `INIT_DB` para `"false"`.