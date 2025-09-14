# Hotfix v09 (Storage-only)

Substituto do `app.py` que remove SQL/SQLAlchemy/rnc_counters.
Tudo é salvo no **Supabase Storage**:
- `rnc_app/data.json` (RNCs)
- `rnc_app/peps.json` (PEPs)
- fotos: `rnc_app/fotos/<RNC>/<tipo>/...`

## Secrets (Streamlit)
```
SUPABASE_URL="https://<seu>.supabase.co"
SUPABASE_KEY="SUA_ANON_KEY"
SUPABASE_BUCKET="RNC-FOTOS"
QUALITY_PASS="qualidade123"
```
