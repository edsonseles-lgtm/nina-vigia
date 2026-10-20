# nina-vigia

Vigia de fora da Nina (assistente do Edson). A cada 10 minutos, o GitHub Actions chama um webhook que responde
só **ok (200)** ou **falha (500)**, sem dado nenhum. Se falhar 2 vezes seguidas ou o servidor não responder,
avisa no WhatsApp e o job fica vermelho (o GitHub manda e-mail e push). Avisa de novo quando volta;
enquanto estiver fora, lembra 1 vez por hora.

- **Segredos** (Settings → Secrets → Actions): `VIGIA_URL`, `VIGIA_TOKEN`, `ALERTA_URL`, `ALERTA_TOKEN`, `ALERTA_NUMERO`.
  Nada disso fica no código.
- **Teste controlado:** Actions → vigia → Run workflow → marque "teste_token_errado" (2 vezes = aviso de queda);
  depois rode com "teste" marcado (aviso de volta). Usa um estado separado: não mexe no estado real.
- **Limites:** o cron do GitHub pode atrasar alguns minutos ou pular rodadas em horário de pico. Repositório
  público sem atividade por 60 dias tem o cron desligado: por isso há um commit vazio automático no dia 1 de cada mês.
- O código de referência (com testes) fica no repositório privado da Nina, em `nina-vps/ops/vigia-actions.py`.
