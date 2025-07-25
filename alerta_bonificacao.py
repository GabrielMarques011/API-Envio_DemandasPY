import requests
import json
import time
import signal
import sys
from collections import defaultdict
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from pandas import json_normalize
import pandas as pd
import calendar


mes_passado = datetime.now() - timedelta(days=30)
mes_passado_inicio = mes_passado.strftime('%Y-%m-01 00:00:00')
mes_passado_fim = mes_passado.strftime('%Y-%m-31 23:59:59')

data_inicial = '2025-06-01 00:00:00'
data_final = '2025-06-30 23:59:59'

from dotenv import load_dotenv
import os

# Carregar variáveis do .env
load_dotenv()

token = os.getenv('TOKEN_API')

BASE_URL = 'http://10.0.100.128:5009'

def autenticar_whats_ticket():
    try:
        response = requests.post(
            f'{BASE_URL}/auth/login',
            json={
                'email': os.getenv('EMAIL_WHATICKET'),
                'password': os.getenv('SENHA_WHATICKET')
            }
        )
        response.raise_for_status()
        token = response.json().get('token')
        print("✅ Token WhatsTicket obtido com sucesso!")
        return token
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao autenticar no WhatsTicket: {e}")
        return None

def enviar_whatsapp(id_fila, mensagem, token):
    if not token:
        print("❌ Token WhatsTicket não disponível.")
        return

    try:
        response = requests.post(
            f'{BASE_URL}/messages/{id_fila}',
            json={'body': mensagem, 'fromMe': True, 'read': 1},
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        )
        response.raise_for_status()
        print(f"✅ Mensagem enviada no WhatsApp (fila {id_fila})")
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao enviar WhatsApp: {e}")

# Consulta os chamados e gera relatório
def consultando_retencao():
    hoje = datetime.now()
    primeiro_dia_mes = hoje.replace(day=1, hour=0, minute=0, second=0).strftime('%Y-%m-%d 00:00:00')
    ultimo_dia_mes = hoje.replace(day=calendar.monthrange(hoje.year, hoje.month)[1], hour=23, minute=59, second=59).strftime('%Y-%m-%d 23:59:59')

    print(f"🔍 Filtrando de {primeiro_dia_mes} até {ultimo_dia_mes}")

    ids_tecnicos = [355, 345, 359, 354, 337, 313, 367, 377]
    funcionarios_map = {
        355: "Rubens Leite",
        345: "João Miyake",
        359: "Pedro Henrique",
        354: "Eduardo Tomaz",
        337: "Alison da Silva",
        313: "João Gomes",
        367: "Rodrigo Akira",
        377: "Diego Sousa"
    }

    url = 'https://assinante.nmultifibra.com.br/webservice/v1/su_ticket'
    headers = {
        'Authorization': token,
        'Content-Type': 'application/json',
        'ixcsoft': 'listar'
    }

    body = {
        "qtype": "id_assunto",
        "query": "358",
        "oper": "=",
        "page": "1",
        "rp": "1000",
        "grid_param": f"""[
            {{"TB":"data_criacao","OP":">=","P":"{primeiro_dia_mes}","C":"AND","G":"data_criacao"}},
            {{"TB":"data_criacao","OP":"<=","P":"{ultimo_dia_mes}","C":"AND","G":"data_criacao"}}
        ]"""
    }

    response = requests.post(url, headers=headers, json=body)

    if response.status_code == 200:
        registros = response.json().get('registros', [])
        registros_filtrados = [r for r in registros if primeiro_dia_mes <= r['data_criacao'] <= ultimo_dia_mes]

        contagem_358 = Counter()
        for r in registros_filtrados:
            tec_id = int(r.get('id_responsavel_tecnico', 0))
            if tec_id in ids_tecnicos:
                contagem_358[tec_id] += 1

        # Salvar JSON
        json_saida = {
            "data_execucao": datetime.now().isoformat(),
            "resultado": [
                {
                    "id_tecnico": tec,
                    "nome": funcionarios_map.get(tec, f"Técnico {tec}"),
                    "quantidade": qtd
                }
                for tec, qtd in contagem_358.items()
            ]
        }

        with open("relatorio_retencao.json", "w", encoding="utf-8") as f:
            json.dump(json_saida, f, ensure_ascii=False, indent=2)

        print("✅ Arquivo relatorio_retencao.json atualizado.")

        # Enviar mensagem por WhatsApp
        token_whats = autenticar_whats_ticket()
        mensagem = "🚨 *Retenções - Mês Atual* 🚨\n\n"
        ordenado = sorted(contagem_358.items(), key=lambda x: x[1], reverse=True)
        for i, (tec, qtd) in enumerate(ordenado, start=1):
            nome = funcionarios_map.get(tec, f"Téc {tec}")
            mensagem += f"{i}° - {nome}: *{qtd}* *retenções*\n"

        enviar_whatsapp(id_fila=29, mensagem=mensagem.strip(), token=token_whats)
    else:
        print(f"❌ Erro na requisição: {response.status_code} - {response.text}")
        
def consultando_upgrade():
    # Calculando intervalo do mês atual (do dia 1 até o último dia do mês)
    hoje = datetime.now()
    primeiro_dia_mes = hoje.replace(day=1, hour=0, minute=0, second=0).strftime('%Y-%m-%d 00:00:00')
    ultimo_dia_mes = hoje.replace(day=calendar.monthrange(hoje.year, hoje.month)[1], hour=23, minute=59, second=59).strftime('%Y-%m-%d 23:59:59')

    print(f"Filtrando de {primeiro_dia_mes} até {ultimo_dia_mes}")

    # Lista dos técnicos que quer contar
    ids_tecnicos = [355, 345, 359, 354, 337, 313, 367, 377]

    # Mapeamento exemplo de id técnico para nome (substitua pelo seu)
    funcionarios_map = {
        355: "Rubens Leite",
        345: "João Miyake",
        359: "Pedro Henrique",
        354: "Eduardo Tomaz",
        337: "Alison da Silva",
        313: "João Gomes",
        367: "Rodrigo Akira",
        377: "Diego Sousa"
    }

    url= 'https://assinante.nmultifibra.com.br/webservice/v1/su_ticket'

    headers = {
        'Authorization': token,
        'Content-Type': 'application/json',
        'ixcsoft': 'listar'
    }

    # Monta o filtro grid_param incluindo filtro por data e id_assunto=358
    body = {
        "qtype": "id_assunto",
        "query": "82",
        "oper": "=",
        "page": "1",
        "rp": "1000",
        "grid_param": f"""[
            {{"TB":"data_criacao","OP":">=","P":"{primeiro_dia_mes}","C":"AND","G":"data_criacao"}},
            {{"TB":"data_criacao","OP":"<=","P":"{ultimo_dia_mes}","C":"AND","G":"data_criacao"}}
        ]"""
    }

    response = requests.post(url, headers=headers, json=body)

    if response.status_code == 200:
        resposta_json = response.json()

        registros = resposta_json.get('registros', [])

        # Garante que só entram registros no intervalo (por segurança)
        registros_filtrados = [r for r in registros if primeiro_dia_mes <= r['data_criacao'] <= ultimo_dia_mes]

        # Inicializa contador por técnico
        contagem_358 = {tec: 0 for tec in ids_tecnicos}

        # Contabiliza chamados de cada técnico dentro do filtro
        for r in registros_filtrados:
            tec_id = int(r.get('id_responsavel_tecnico', 0))
            if tec_id in contagem_358:
                contagem_358[tec_id] += 1

        # Enviar mensagem por WhatsApp
        token_whats = autenticar_whats_ticket()
        mensagem = "🚨 *Troca de Plano - Mês Atual:* 🚨\n\n"
        ordenado = sorted(contagem_358.items(), key=lambda x: x[1], reverse=True)
        for i, (tec, qtd) in enumerate(ordenado, start=1):
            nome = funcionarios_map.get(tec, f"Téc {tec}")
            mensagem += f"{i}° - {nome}: *{qtd}* *upgrades*\n"

        enviar_whatsapp(id_fila=29, mensagem=mensagem.strip(), token=token_whats)

    else:
        print(f"Erro na requisição: {response.status_code} - {response.text}")        

def main():
    scheduler = BlockingScheduler(timezone="America/Sao_Paulo")

    trigger = CronTrigger(minute=0, hour="12,16", second=0)
    scheduler.add_job(consultando_retencao, trigger=trigger)
    scheduler.add_job(consultando_upgrade, trigger=trigger)

    consultando_retencao()  # Executa imediatamente
    consultando_upgrade()  # Executa imediatamente

    print("🚀 Agendado para rodar às 12h e 16h todos os dias.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n⛔ Encerrando scheduler...")

if __name__ == "__main__":
    main()