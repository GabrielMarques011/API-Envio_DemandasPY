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
from pytz import timezone

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

def distribuir_feed():
    # UTILIZANDO PARA ENCAMINHAR CHAMADOS REFERENTE A FEEDBACK, ID: 205.

    headers_listar = {
        'Authorization': token,
        'Content-Type': 'application/json',
        'ixcsoft': 'listar'
    }

    headers_put = {
        'Authorization': token,
        'Content-Type': 'application/json'
    }

    # 1. Buscar chamados abertos (mesmo código que já tem)
    url_oss = 'https://assinante.nmultifibra.com.br/webservice/v1/su_oss_chamado'

    body_oss = {
        "qtype": "status",
        "query": "A",
        "oper": "=",
        "page": "1",
        "rp": "1000"
    }

    response_oss = requests.post(url_oss, headers=headers_listar, json=body_oss)
    dados_oss = response_oss.json()
    registros_oss = dados_oss.get('registros', [])

    # 2. Buscar assuntos para mapear id -> nome
    url_assuntos = 'https://assinante.nmultifibra.com.br/webservice/v1/su_oss_assunto'
    response_assuntos = requests.post(url_assuntos, headers=headers_listar, json={"page":"1","rp":"1000"})
    dados_assuntos = response_assuntos.json()
    registros_assuntos = dados_assuntos.get('registros', [])
    assuntos_map = {str(a['id']): a['assunto'] for a in registros_assuntos}

    ids_assunto_desejados = ['205', '409']

    # Contar chamados por assunto
    contagem_por_assunto = {assunto_id: 0 for assunto_id in ids_assunto_desejados}

    # Filtrar chamados abertos com os assuntos desejados
    filtrados = []
    for os in registros_oss:
        if os.get('status') == 'A' and os.get('id_assunto') in ids_assunto_desejados:
            filtrados.append(os)
            contagem_por_assunto[os.get('id_assunto')] += 1

    # Mostrar no console a quantidade por assunto
    for assunto_id in ids_assunto_desejados:
        nome_assunto = assuntos_map.get(assunto_id, 'Desconhecido')
        print(f"Total chamados abertos com assunto {assunto_id} ({nome_assunto}): {contagem_por_assunto[assunto_id]}")

    ids_tecnicos = [355, 345, 359, 354, 337, 313, 367, 377] #307 REMOVENDO O ROSA DEVIDO FERIAS

    chamados_por_tecnico = defaultdict(int)

    for i, chamado in enumerate(filtrados):
        id_chamado = chamado.get('id')
        
        # Buscar dados completos do chamado por ID
        url_busca_chamado = url_oss
        payload_busca = json.dumps({
            "qtype": "id",
            "query": str(id_chamado),
            "oper": "=",
            "page": "1",
            "rp": "1"
        })
        
        response_busca = requests.post(url_busca_chamado, headers=headers_listar, data=payload_busca)
        
        if response_busca.status_code != 200:
            print(f"Erro ao buscar dados do chamado {id_chamado}: {response_busca.status_code}")
            continue
        
        dados_chamado = response_busca.json()
        registros = dados_chamado.get('registros', [])
        if not registros:
            print(f"Chamado {id_chamado} não encontrado na busca detalhada.")
            continue
        
        chamado_detalhado = registros[0]
        
        # Editar campos necessários
        tecnico_id = ids_tecnicos[i % len(ids_tecnicos)]
        chamado_detalhado['id_tecnico'] = tecnico_id
        chamado_detalhado['status'] = 'EN'
        chamado_detalhado['setor'] = '5'
        
        # Enviar PUT para atualizar
        url_put = f"{url_oss}/{id_chamado}"
        
        response_put = requests.put(url_put, headers=headers_put, data=json.dumps(chamado_detalhado))
        
        if response_put.status_code == 200:
            print(f"Chamado {id_chamado} encaminhado para técnico {tecnico_id}")
            chamados_por_tecnico[tecnico_id] += 1
        else:
            print(f"Erro ao atualizar chamado {id_chamado}: {response_put.status_code} - {response_put.text}")

    # FIM do for: agora envia a mensagem resumida

    if chamados_por_tecnico:
        whatsapp_token = autenticar_whats_ticket()

        # Buscar nomes dos técnicos
        url_func = 'https://assinante.nmultifibra.com.br/webservice/v1/funcionarios'
        body_func = {'qtype': 'id', 'query': '0', 'oper': '>', 'page': '1', 'rp': '1000'}
        resp_func = requests.post(url_func, headers=headers_listar, json=body_func)
        funcionarios_map = {int(f['id']): f['funcionario'] for f in resp_func.json().get('registros', [])}

        # Montar mensagem final
        mensagem_final = "📊 *Resumo de Feedbacks Encaminhados*\n\n"
        for tec_id, qtd in chamados_por_tecnico.items():
            nome_tec = funcionarios_map.get(tec_id, f"Técnico {tec_id}")
            mensagem_final += f"- {tec_id} *{nome_tec}*: {qtd} Feedback{'s' if qtd > 1 else ''} encaminhado{'s' if qtd > 1 else ''}\n"

        # Enviar via WhatsApp (ajuste o id_fila conforme necessário)
        if whatsapp_token:
            enviar_whatsapp(id_fila=26, mensagem=mensagem_final.strip(), token=whatsapp_token)

def main():
    scheduler = BlockingScheduler(timezone="America/Sao_Paulo")

    # Executar todos os dias às 18h em ponto
    trigger = CronTrigger(hour=18, minute=0, second=0)
    scheduler.add_job(distribuir_feed, trigger=trigger)
    
    distribuir_feed()  # Executa imediatamente

    print("✅ Agendado para rodar todo dia às 18h. CTRL+C para parar.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n⛔ Encerrando scheduler...")

if __name__ == "__main__":
    main()