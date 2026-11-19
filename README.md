# Certifica

Programa desktop (Windows e macOS) que envia **certificados em PDF por email**, cada um para a sua pessoa, a partir de uma planilha.

## Download

Baixe na página de [Releases](https://github.com/oCatito/Certifica/releases/latest). Não precisa instalar nada.

- **Windows:** `Certifica.exe`. É só abrir o arquivo.
- **macOS (chip Apple, M1 ou mais novo):** `Certifica-macOS.zip`. Descompacte e arraste o `Certifica.app` para a pasta Aplicativos.

## Atualizações

Ao abrir, o programa verifica se há uma versão nova nos Releases. Se houver, aparece um aviso no canto inferior direito: clique em **Atualizar agora** e ele baixa a nova versão, substitui a atual e abre de novo. Se não puder se atualizar sozinho (por exemplo, sem permissão na pasta ou aberto direto do `.zip`), o botão abre a página de download.

## Como usar

O menu inicial tem três opções independentes (use só a que precisar, em qualquer ordem). A engrenagem **⚙** abre as configurações.

1. **Planilhar:** baixe a planilha modelo, preencha, carregue e clique em **Confirmar**.
2. **Certificar:** em breve.
3. **Enviar:** assistente em 5 passos:
   1. Escolha a planilha, a pasta dos PDFs e as colunas (Nome, Email, Arquivo).
   2. Pré-verificação: só as linhas ✅ são enviadas (❌ arquivo ausente ou email inválido, ⚠ duplicado, ⏭ já enviado).
   3. Revise a prévia e use **Enviar teste para mim**.
   4. Acompanhe o envio (é possível pausar ou cancelar).
   5. Veja o relatório `.xlsx` (salvo ao lado da planilha) e use **Reenviar falhas**.

## Configuração (⚙)

- **Servidor:** escolha o provedor (Gmail, Outlook, Yahoo, SendGrid etc.) ou "Outro servidor" (SMTP), informe usuário e senha e clique em **Testar conexão**. A senha fica no cofre do sistema, nunca em arquivo.
- **Remetente:** nome exibido e endereço de resposta.
- **Mensagem:** assunto e corpo (texto ou HTML), com prévia.
- **Envio:** intervalo entre emails (padrão aleatório, entre 30 s e 1 min), limite diário e tentativas.

> **Gmail:** exige uma **senha de app**. Ative a verificação em duas etapas e crie a senha em Conta Google → Segurança → Senhas de app. No Workspace, o administrador precisa liberar essa opção.

### Variáveis na mensagem

`{nome}`, `{primeiro_nome}`, `{email}`, `{arquivo}` e qualquer coluna da planilha (`Data do Curso` vira `{data_do_curso}`).
Exemplo de assunto: `Seu certificado - {curso}`

## Planilha

Arquivo `.xlsx` ou `.csv`, com cabeçalho e uma pessoa por linha. Os nomes das colunas são livres, pois você os escolhe na tela.

| Nome | Email | Arquivo | Curso |
|---|---|---|---|
| Marina Silva | marina@email.com | marina_silva.pdf | Python Básico |

Todos os PDFs devem estar numa única pasta. A extensão `.pdf` é opcional na coluna Arquivo.

## Listas grandes

Provedores limitam envios por dia (Gmail: ~500 em contas comuns, 2.000 no Workspace). Ajuste o **limite diário**: o programa para sozinho ao atingi-lo. No dia seguinte, abra a mesma planilha e quem já recebeu será pulado.

## Primeira execução

O app não é assinado digitalmente:

- **macOS:** botão direito em `Certifica.app` → **Abrir** → **Abrir**. Se não aparecer a opção, tente abrir uma vez e vá em **Ajustes do Sistema → Privacidade e Segurança → Abrir Mesmo Assim**.
- **Windows:** SmartScreen → **Mais informações** → **Executar assim mesmo**.

## Desenvolvimento

Requer Python 3.10+.

**macOS / Linux:**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python main.py          # abrir o programa
.venv/bin/python tools/dev.py     # recarrega ao salvar
.venv/bin/python -m pytest        # testes
```

**Windows (Prompt de Comando):**

```bat
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python main.py
.venv\Scripts\python tools\dev.py
.venv\Scripts\python -m pytest
```

- **Gerar executável:** `./build_mac.sh` (macOS) ou `build_windows.bat` (Windows), cada um no próprio sistema.
- **Publicar uma versão:** atualize `__version__` em `app/__init__.py`, faça o commit e envie uma tag com o mesmo número (`git tag v1.1.0` e `git push origin v1.1.0`). O GitHub Actions roda os testes, gera o `Certifica.exe` e cria o release com ele. Se a tag não bater com `__version__`, o release não é criado.
- **Ícone:** `tools/make_icon.py` gera `assets/icon.png`, `icon.ico` e `icon.icns`.
- **Testar sem enviar emails reais:** `.venv/bin/python -m aiosmtpd -n -l localhost:1025` e, nas configurações, servidor `localhost`, porta `1025`, segurança "Nenhuma".
- **Dados locais:** `~/Library/Application Support/Certifica/` (macOS) ou `%LOCALAPPDATA%\Certifica\` (Windows). Senha no cofre do sistema.
- **Estrutura:** `main.py` (entrada), `app/ui/` (janelas), `app/core/` (lógica), `tests/`.

## Licença

[PolyForm Noncommercial 1.0.0](LICENSE): uso, modificação e estudo permitidos **sem fins comerciais**. Para uso comercial, contate pelo [GitHub](https://github.com/ocatito).