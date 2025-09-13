# RNC App v08 (v6.4) — Supabase + Streamlit

Este pacote contém:
- `app.py` (app completo)
- `requirements.txt`
- `exemplos/peps_exemplo.csv`
- `README.md`

## 1) Subir para o Streamlit Cloud (ou rodar local)
- Faça login no Streamlit Cloud e crie um app apontando para este repositório (ou faça upload direto destes arquivos).
- Versão do Python: 3.11+ recomendado.

## 2) Configurar *Secrets* do app
Em **Settings → Secrets**, cole exatamente:

```
SUPABASE_URL="https://umppgtxwipnsnwogwacv.supabase.co"
SUPABASE_KEY="SUA_ANON_KEY"
SUPABASE_DB_URL="postgresql+psycopg2://postgres:SUA_SENHA_URLENCODE@db.umppgtxwipnsnwogwacv.supabase.co:6543/postgres?sslmode=require"
SUPABASE_BUCKET="RNC-FOTOS"
QUALITY_PASS="qualidade123"
INIT_DB="true"
```

> Troque **SUA_ANON_KEY** pela anon key do seu projeto (Supabase → Project Settings → API → `anon key`).  
> Troque **SUA_SENHA_URLENCODE** por sua senha do Postgres **codificada** (ex.: `Vitor@Maia25` vira `Vitor%40Maia25`).

Após o primeiro run (tabelas criadas), pode alterar `INIT_DB` para `"false"`.

## 3) Como usar (resumo)
1. Abra o app e, no menu lateral, entre em **🔐 Acesso Qualidade** usando a senha do secrets (`QUALITY_PASS`).  
2. Em **➕ Nova RNC**, preencha e salve. O número (ex.: `2025-001`) é gerado automaticamente.
3. Em **🔎 Consultar/Editar**, visualize RNCs, encerre, reabra, cancele ou exclua.
4. Em **🏷️ PEPs**, importe via CSV (`exemplos/peps_exemplo.csv`) ou cadastre manualmente.
5. Em **⬇️⬆️ CSV**, exporte/importar RNCs.  
6. Em **ℹ️ Status**, veja se o banco conectou e se os secrets foram lidos.

## 4) Fotos no Storage
- O app cria (se não existir) o bucket `RNC-FOTOS` (público) e salva as imagens por pasta: `RNC/abertura|encerramento|reabertura/uuid.jpg`.

## 5) Dúvidas rápidas
- **Erro de conexão**: confira `SUPABASE_DB_URL` (host `db.<id>.supabase.co:6543`, senha URL-encoded e `sslmode=require`).  
- **Numeração duplicada**: o app usa índice `UNIQUE` e tenta novamente automaticamente.  
- **Logo no PDF**: envie/remova na barra lateral (seção Logo).

Pronto. Qualquer ajuste, basta substituir o `app.py`.
