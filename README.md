# RNC App v10-fastdeploy (REST)
- Sem SQL, sem biblioteca supabase, sem reportlab (PDF desativado por enquanto)
- Usa apenas `requests` para chamar a API REST do Supabase Storage
- Bucket precisa estar **Public**
## Secrets
```
SUPABASE_URL="https://<seu>.supabase.co"
SUPABASE_KEY="SUA_ANON_KEY"
SUPABASE_BUCKET="RNC-FOTOS"
QUALITY_PASS="qualidade123"
```
