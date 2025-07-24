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

def filtrar_por_intervalo(registros, inicio, fim):
    return [r for r in registros if inicio <= r['data_criacao'] <= fim]

# FILTRANDO E CONTABILIZANDO FEEDBACKS EM NOME DOS COLABORADORES (ENCAMINHADOS)
def consulta_feed():
    headers = {
        'Authorization': token,
        'Content-Type': 'application/json',
        'ixcsoft': 'listar'
    }

    # --- 1. Buscar colaboradores (técnicos) ---
    url_funcionarios = 'https://assinante.nmultifibra.com.br/webservice/v1/funcionarios'
    body_funcionarios = {
        'qtype': 'id',
        'query': '0',
        'oper': '>',
        'page': '1',
        'rp': '1000',
        'sortname': 'funcionarios.id',
        'sortorder': 'asc'
    }

    response_func = requests.post(url_funcionarios, json=body_funcionarios, headers=headers)
    tecnicos_info = {}

    if response_func.status_code == 200:
        data_func = response_func.json()
        for funcionario in data_func.get('registros', []):
            id_func = int(funcionario.get('id', 0))
            nome_func = funcionario.get('funcionario', 'Nome Desconhecido')
            tecnicos_info[id_func] = nome_func
    else:
        print(f"Erro ao buscar colaboradores: {response_func.status_code} - {response_func.text}")
        exit(1)

    print(f"Total técnicos carregados: {len(tecnicos_info)}")

    # --- 2. Buscar assuntos válidos ---
    url_assuntos = 'https://assinante.nmultifibra.com.br/webservice/v1/su_oss_assunto'
    body_assuntos = {
        "qtype": "id",
        "query": "0",
        "oper": ">",
        "page": "1",
        "rp": "1000"
    }

    nomes_assuntos = [
        "Feedback - Pós BD",
        "Feedback - Pós BD Lógico"
    ]


    response_assuntos = requests.post(url_assuntos, json=body_assuntos, headers=headers)
    ids_assuntos_validos = set()
    assuntos_dict = {}

    if response_assuntos.status_code == 200:
        data_assuntos = response_assuntos.json()
        registros_assuntos = data_assuntos.get('registros', [])
        nomes_assuntos_set = set(nomes_assuntos)

        for assunto in registros_assuntos:
            nome = assunto.get('assunto')
            id_assunto = int(assunto.get('id', 0))
            assuntos_dict[id_assunto] = nome
            if nome in nomes_assuntos_set:
                ids_assuntos_validos.add(id_assunto)
    else:
        print(f"Erro ao buscar assuntos: {response_assuntos.status_code} - {response_assuntos.text}")
        exit(1)

    # --- 3. Buscar chamados paginados e filtrar ---
    url_chamados = 'https://assinante.nmultifibra.com.br/webservice/v1/su_oss_chamado'

    ids_tecnicos = [307, 355, 345, 359, 354, 337, 313, 367, 377]

    all_chamados = []
    page = 1
    rp = 1000

    while True:
        body_chamados = {
            "qtype": "status",
            "query": "EN",
            "oper": "=",
            "page": str(page),
            "rp": str(rp)
        }

        response_chamados = requests.post(url_chamados, json=body_chamados, headers=headers)

        if response_chamados.status_code != 200:
            print(f"Erro na requisição da página {page}: {response_chamados.status_code} - {response_chamados.text}")
            break

        data_chamados = response_chamados.json()
        registros_chamados = data_chamados.get('registros', [])
        total = int(data_chamados.get('total', 0))

        if not registros_chamados:
            break

        all_chamados.extend(registros_chamados)

        if page * rp >= total:
            break

        page += 1

    # --- 4. Filtrar chamados por técnico e assunto válido ---
    chamados_filtrados = [
        chamado for chamado in all_chamados
        if int(chamado.get('id_tecnico', 0)) in ids_tecnicos
        and int(chamado.get('id_assunto', 0)) in ids_assuntos_validos
    ]

    # --- 5. Agrupar chamados por técnico e imprimir resumo ---
    from collections import defaultdict
    chamados_por_tecnico = defaultdict(list)

    for chamado in chamados_filtrados:
        id_tec = int(chamado.get('id_tecnico', 0))
        id_assunto = int(chamado.get('id_assunto', 0))
        chamados_por_tecnico[id_tec].append(id_assunto)

    for id_tec, assuntos_ids in chamados_por_tecnico.items():
        nome_tec = tecnicos_info.get(id_tec, f"Técnico {id_tec}")
        assuntos_unicos = set(assuntos_ids)
        print(f"ID {id_tec} - {nome_tec}")
        print(f" Tem {len(assuntos_ids)} chamados atribuídos:")
        for assunto_id in assuntos_unicos:
            print(f"- {assuntos_dict.get(assunto_id, f'Assunto {assunto_id}')}")
        print()

    whatsapp_token = autenticar_whats_ticket()

    mensagem_geral = "📊 *Contagem de Feedbacks Gerais Distribuidas* 📊\n\n"

    for id_tec, assuntos_ids in chamados_por_tecnico.items():
        nome_tec = tecnicos_info.get(id_tec, f"Técnico {id_tec}")
        total_chamados = len(assuntos_ids)

        # Pegando o nome do primeiro assunto (considerando que todos chamados filtrados são do mesmo tipo por técnico)
        assuntos_unicos = set(assuntos_ids)
        # assuntos_nomes = [assuntos_dict.get(assunto_id, f"Assunto {assunto_id}") for assunto_id in assuntos_unicos]
        # assunto_str = ', '.join(assuntos_nomes)

        mensagem_geral += f"Responsável: *{nome_tec}*\n"
        # mensagem_geral += f"Assunto: *{assunto_str}*\n"
        mensagem_geral += f"Total de Chamados: *{total_chamados}*\n\n"

    print("➡️ Enviando mensagem geral:", mensagem_geral)

    if whatsapp_token:
        enviar_whatsapp(id_fila=31, mensagem=mensagem_geral, token=whatsapp_token)

    # enviar_telegram(mensagem_geral)

def main():
    scheduler = BlockingScheduler(timezone="America/Sao_Paulo")

    trigger = CronTrigger(minute=0, hour="7-19", second=0)
    scheduler.add_job(consulta_feed, trigger=trigger)

    # consulta_feed()  # Executa imediatamente

    print("🚀 Agendado para rodar a cada 1 hora, das 7 até 19 horas.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n⛔ Encerrando scheduler...")

if __name__ == "__main__":
    main()