# RNC App v09.1 — Storage-only com Teste Automático

- Não usa banco SQL. Tudo em Supabase Storage (ou local, se USE_LOCAL_STORAGE=1).
- Inclui botão **"Rodar autoteste"** na aba **ℹ️ Status** que:
  1) Cria RNC de teste
  2) Salva JSON
  3) Relê JSON
  4) Gera PDF
  5) Limpa o registro de teste

## Secrets necessários (Streamlit)
```
SUPABASE_URL="https://<seu>.supabase.co"
SUPABASE_KEY="SUA_ANON_KEY"
SUPABASE_BUCKET="RNC-FOTOS"
QUALITY_PASS="qualidade123"
```

## Teste local sem Supabase
Defina no deploy ou no ambiente:
```
USE_LOCAL_STORAGE="1"
```
Assim o app salva tudo na pasta `.rnc_data` local (somente para testes).
