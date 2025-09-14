# RNC App v08 — Supabase (GRÁTIS)

**O que muda nesta versão**
- **Banco de dados**: PostgreSQL do **Supabase** (plano free)
- **Fotos**: salvas no **Supabase Storage** (bucket `rnc-fotos`) e exibidas por link
- **PDF**: inclui textos e imagens direto da nuvem
- **Nunca perde os dados** quando o app "dorme" no Streamlit Cloud

## 1) Criar projeto no Supabase (grátis)
1. Acesse https://supabase.com/ e crie uma conta.
2. Crie um projeto → escolha **Region** e **Senha do banco**.
3. No Dashboard: **Project Settings → API**: copie **Project URL** e **anon key**.
4. Na **Home do projeto**: clique em **Connection string** e copie a **URI** (postgresql://...).
5. Em **Storage → Create new bucket** → nome: `rnc-fotos` → marque **Public**.

## 2) Publicar no Streamlit Cloud
Suba os arquivos deste pacote para um repositório no GitHub e faça deploy apontando para `app.py`.

### Secrets (App settings → Secrets)
Cole e ajuste:
```
QUALITY_PASS="sua_senha_forte"

# Supabase
SUPABASE_URL="https://SEU-PROJECT-REF.supabase.co"
SUPABASE_KEY="sua_anon_key_ou_service_key"
SUPABASE_DB_URL="postgresql://usuario:senha@host:5432/postgres"  # de Connection string (URI)
SUPABASE_BUCKET="rnc-fotos"

# (opcional) E-mail SMTP
SMTP_HOST="smtp.office365.com"
SMTP_PORT="587"
SMTP_USER="seu.email@empresa.com"
SMTP_PASS="sua_senha_ou_app_password"
EMAIL_FROM="seu.email@empresa.com"
EMAIL_TO="qualidade@empresa.com, gestor@empresa.com"
```

## 3) Pronto!
- Aberturas, encerramentos e reaberturas gravam no Postgres
- Fotos são enviadas ao bucket e o app guarda apenas o **link**
- PDF baixa as imagens direto do Storage

## Backup
Você ainda pode **Exportar CSV** pelo app quando quiser.
