# Como contribuir — Similaris (Back-end)

Obrigado pelo interesse em contribuir com o **Similaris**. Este projeto é de código aberto sob a [Licença MIT](LICENSE).

## Fluxo de contribuição

1. Faça um **fork** deste repositório e crie uma branch a partir da `main`:
   ```bash
   git checkout -b feat/sua-melhoria
   ```
2. Ative os hooks locais de validação de commit:
   ```bash
   git config core.hooksPath .githooks
   ```
3. Configure o ambiente local copiando `.env.example` para `.env` (nunca versione credenciais ou arquivos `.env`).
4. Execute a suíte de testes antes de abrir o Pull Request:
   ```bash
   pytest
   ```
5. Envie commits seguindo o padrão **Conventional Commits** (ex.: `feat: adiciona suporte a ocr`, `fix: normaliza email no login`).
6. Abra um **Pull Request** descrevendo claramente a motivação, o que foi alterado e como validar.
