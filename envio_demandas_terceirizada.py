import requests
import json
import time
import signal
import sys
from collections import defaultdict
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from pandas import json_normalize
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

mes_passado = datetime.now() - timedelta(days=30)
mes_passado_inicio = mes_passado.strftime('%Y-%m-01 00:00:00')
mes_passado_fim = mes_passado.strftime('%Y-%m-31 23:59:59')

""" data_inicial = '2025-06-01 00:00:00'
data_final = '2025-06-30 23:59:59' """

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

# UTILIZANDO PARA ENCAMINHAR CHAMADOS REFERENTE A TERCEIRIZADA, ID: 492. // FILTRANDO E CONFIRMANDO CHAMADO COM STATUS ABERTO ANTES DE ENCAMINHAR
def distribuir_chamados():

    # TOKEN para o WhatsTicket
    whatsapp_token = autenticar_whats_ticket()

    # CONFIGURAÇÃO DE HEADERS
    headers_listar = {
        'Authorization': token,
        'Content-Type': 'application/json',
        'ixcsoft': 'listar'
    }
    headers_put = {
        'Authorization': token,
        'Content-Type': 'application/json'
    }

    # 1. Buscar chamados abertos (sua lógica)
    url_oss = 'https://assinante.nmultifibra.com.br/webservice/v1/su_oss_chamado'
    body_oss = {
        "qtype": "status",
        "query": "A",
        "oper": "=",
        "page": "1",
        "rp": "1000"
    }
    response_oss = requests.post(url_oss, headers=headers_listar, json=body_oss)
    registros_oss = response_oss.json().get('registros', [])

    # 2. Mapear id -> nome de assuntos (sua lógica)
    url_assuntos = 'https://assinante.nmultifibra.com.br/webservice/v1/su_oss_assunto'
    response_assuntos = requests.post(url_assuntos, headers=headers_listar, json={"page":"1","rp":"1000"})
    registros_assuntos = response_assuntos.json().get('registros', [])
    assuntos_map = {str(a['id']): a['assunto'] for a in registros_assuntos}

    id_assunto_desejado = '492'
    filtrados = [
        os for os in registros_oss
        if os.get('id_assunto') == id_assunto_desejado and os.get('status') == 'A'
    ]
    # print(f'Total chamados abertos com assunto {id_assunto_desejado}: {len(filtrados)}')

    ids_tecnicos = [355, 345, 359, 354, 337, 313, 367, 377]

    # Dicionário que vai acumular os assuntos por técnico
    chamados_por_tecnico = defaultdict(list)

    # CONFIGURAÇÃO DE HEADERS
    headers_listar = {
        'Authorization': token,
        'Content-Type': 'application/json',
        'ixcsoft': 'listar'
    }
    headers_put = {
        'Authorization': token,
        'Content-Type': 'application/json'
    }

    # 2.1) Chamados Abertos
    url_oss = 'https://assinante.nmultifibra.com.br/webservice/v1/su_oss_chamado'
    body_oss = {"qtype":"status","query":"A","oper":"=","page":"1","rp":"1000"}
    response_oss = requests.post(url_oss, headers=headers_listar, json=body_oss)
    registros_oss = response_oss.json().get('registros', [])

    # 2.2) Mapa de Assuntos
    url_assuntos = 'https://assinante.nmultifibra.com.br/webservice/v1/su_oss_assunto'
    resp_asc = requests.post(url_assuntos, headers=headers_listar, json={"page":"1","rp":"1000"})
    assuntos_map = {str(a['id']): a['assunto'] for a in resp_asc.json().get('registros', [])}

    # 2.3) Filtrar só o assunto 492
    id_assunto_desejado = '492'
    filtrados = [
        os for os in registros_oss
        if os.get('id_assunto') == id_assunto_desejado and os.get('status') == 'A'
    ]

    print(f'Total chamados abertos com assunto {id_assunto_desejado}: {len(filtrados)}')  # << só uma vez

    # 2.4) Mapa de técnicos para rodízio e para nomes
    ids_tecnicos = [355,345,359,354,337,313,367,377]

    # Busca nomes uma única vez
    url_func = 'https://assinante.nmultifibra.com.br/webservice/v1/funcionarios'
    body_func = {'qtype':'id','query':'0','oper':'>','page':'1','rp':'1000'}
    resp_func = requests.post(url_func, headers=headers_listar, json=body_func)
    funcionarios_map = {int(f['id']): f['funcionario'] for f in resp_func.json().get('registros', [])}

    # Dicionário acumulador (fora do loop)
    chamados_por_tecnico = defaultdict(list)

    # 3) LOOP ÚNICO DE ENCAMINHAMENTO
    for i, chamado in enumerate(filtrados):
        id_chamado = chamado['id']
        
        # 3.1) Busca detalhada
        busca = {"qtype":"id","query":str(id_chamado),"oper":"=","page":"1","rp":"1"}
        resp_busca = requests.post(url_oss, headers=headers_listar, json=busca)
        regs = resp_busca.json().get('registros', [])
        if not regs:
            print(f"Chamado {id_chamado} não encontrado.")
            continue
        detalhado = regs[0]
        
        # 3.2) Atualiza campos
        tecnico_id = ids_tecnicos[i % len(ids_tecnicos)]
        detalhado['id_tecnico'] = tecnico_id
        detalhado['status'] = 'EN'
        detalhado['setor'] = '5'
        
        # 3.3) PUT de atualização
        resp_put = requests.put(f"{url_oss}/{id_chamado}", headers=headers_put, json=detalhado)
        if resp_put.status_code != 200:
            print(f"Erro ao atualizar {id_chamado}: {resp_put.status_code}")
            continue
        
        print(f"Chamado {id_chamado} encaminhado para técnico {tecnico_id}")  # << só um print
        
        if whatsapp_token:
                # --- AQUI COMEÇA A BUSCA DO CLIENTE ---
                id_cliente = detalhado.get('id_cliente')
                url_cliente = 'https://assinante.nmultifibra.com.br/webservice/v1/cliente'
                payload_cliente = {
                    "qtype": "id",
                    "query": str(id_cliente),
                    "oper": "=",
                    "page": "1",
                    "rp": "1"
                }
                resp_cliente = requests.post(url_cliente, headers=headers_listar, json=payload_cliente)
                if resp_cliente.status_code == 200 and resp_cliente.json().get('registros'):
                    nome_cliente = resp_cliente.json()['registros'][0].get('razao', f"Cliente {id_cliente}")
                else:
                    nome_cliente = f"Cliente {id_cliente}"
                # --- FIM DA BUSCA DO CLIENTE ---

                # acumula e conta os assuntos
                chamados_por_tecnico[tecnico_id].append(chamado['id_assunto'])
                contagem = Counter(chamados_por_tecnico[tecnico_id])
                total = sum(contagem.values())
                nome_tec = funcionarios_map.get(tecnico_id, f"Técnico {tecnico_id}")

                # monta a mensagem, agora incluindo o cliente
                mensagem = "⚠️ Envio de Demandas ⚠️\n\n"
                mensagem += f"Responsável: *{nome_tec}*\n\n"
                mensagem += f"- Cliente: *{nome_cliente}*\n"
                # mensagem += f"Total: *{total}* chamados\n"
                for a_id, qtd in contagem.items():
                    nome_a = assuntos_map.get(str(a_id), f"Assunto {a_id}")
                    mensagem += f"- *{nome_a}* : {qtd} chamado{'s' if qtd>1 else ''}\n"

                enviar_whatsapp(id_fila=23, mensagem=mensagem.strip(), token=whatsapp_token)
    
    print("⏱️ Executando rotina de encaminhar chamados…")

def main():
    scheduler = BlockingScheduler(timezone="America/Sao_Paulo")

    # Cron de 10 em 10 minutos entre 7h e 21h
    trigger = CronTrigger(minute="*/10", hour="7-21", second="0")
    scheduler.add_job(distribuir_chamados, trigger=trigger)

    distribuir_chamados()  # Executa imediatamente

    print("🚀 Agendado para rodar a cada 10 minutos.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n⛔ Encerrando scheduler...")

if __name__ == "__main__":
    main()