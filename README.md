# RNC App (SQL, pyformat fix)

## 1) Suba estes arquivos no seu repositório (raiz)
- app.py
- requirements.txt
- runtime.txt

## 2) Secrets no Streamlit
SUPABASE_DB_URL="postgresql+psycopg2://postgres:<SUA_SENHA>@aws-1-sa-east-1.pooler.supabase.com:6543/postgres?sslmode=require"
QUALITY_PASS="qualidade123"

## 3) No Streamlit Cloud
- New app → aponte para este repo
- Main file path: app.py
- Manage app → Advanced → Clear cache (se travar)
