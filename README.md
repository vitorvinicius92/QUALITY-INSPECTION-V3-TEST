# RNC App v10 (Storage-only)

Sem SQL/SQLAlchemy. Toda a persistência é no **Supabase Storage**:
- `rnc_app/data.json` (RNCs)
- `rnc_app/peps.json` (PEPs)
- fotos: `rnc_app/fotos/<RNC>/<tipo>/...`
- logo do PDF: `rnc_app/logo.bin`

## Secrets (Streamlit → Settings → Secrets)
```
SUPABASE_URL="https://<seu>.supabase.co"
SUPABASE_KEY="SUA_ANON_KEY"
SUPABASE_BUCKET="RNC-FOTOS"
QUALITY_PASS="qualidade123"
```

## Policies do bucket
No Supabase, habilite (UI) estas ações para o bucket `RNC-FOTOS`:
- Read (select)
- Upload (insert)
- Update
- Delete
Pode marcar o bucket como **Public** para facilitar preview das imagens.
