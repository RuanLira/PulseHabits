# PulseHabits

PulseHabits e uma aplicacao full-stack simples para acompanhar habitos, metas e progresso semanal.

O projeto usa:

- Python puro no backend
- SQLite como banco de dados
- HTML, CSS e JavaScript no frontend
- API local para criar, editar, concluir e remover habitos
- Login com sessao local
- Historico e exportacao CSV

## Requisito

Instale o Python 3 antes de rodar o projeto.

No Windows, voce pode baixar em:

```text
https://www.python.org/downloads/
```

Durante a instalacao, marque a opcao para adicionar o Python ao PATH.

## Como rodar

```bash
python app.py
```

Depois abra:

```text
http://localhost:8000
```

## Funcionalidades

- Cadastro de habitos com categoria e meta semanal
- Login e criacao de conta
- Marcar habitos como concluidos em qualquer data recente
- Mini historico por habito
- Dashboard com progresso, sequencia e resumo semanal
- Grafico dos ultimos 30 dias
- Filtro por categoria
- Edicao de habitos
- Exportacao em CSV
- Lembretes pelo navegador
- Persistencia em banco SQLite
- Interface responsiva

## Ideias para evoluir

- Recuperacao de senha
- Graficos por categoria
- Pagina publica de progresso
- Deploy em Render, Railway ou Fly.io

## Conta de teste

```text
usuario: demo
senha: demo123
```

## Deploy

O projeto usa apenas a biblioteca padrao do Python, entao pode ser adaptado para plataformas como Render, Railway ou Fly.io. Para producao, troque o servidor `http.server` por um servidor WSGI/ASGI e configure variaveis de ambiente.
