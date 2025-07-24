import requests
import json
import time
import signal
import sys
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from pytz import timezone
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
import os

# Carregar variáveis do .env
load_dotenv()

token = os.getenv('TOKEN_API')
BASE_URL = 'http://10.0.100.128:5009'

# Expediente dos colaboradores
expediente_colaboradores = {
    355: { 'inicio': '15:00', 'fim': '21:00' },  # RUBENS
    345: { 'inicio': '06:00', 'fim': '16:00' },  # JOÃO MIYAKE
    359: { 'inicio': '10:00', 'fim': '17:00' },  # PEDRO
    354: { 'inicio': '06:00', 'fim': '11:00' },  # EDUARDO
    337: { 'inicio': '11:00', 'fim': '21:00' },  # ALISON
    313: { 'inicio': '11:00', 'fim': '21:00' },  # JOÃO GOMES
    367: { 'inicio': '06:00', 'fim': '16:00' },  # RODRIGO
    377: { 'inicio': '10:00', 'fim': '16:00' },  # DIEGO
}

# Lista de assuntos permitidos
assuntos_permitidos = [
    "Configuração de Roteador",
    "Sinal fora do padrão",
    "Ter - OS Sinal fora do padrão",
    "Troca de equipamento",
    "Vistoria Técnica - NMULTIFIBRA",
    "Retenção",
    "Cabeamento fora do padrão",
    "Ter - OS de cabeamento fora do padrão",
    "Transferência de endereço",
    "Mudança de Ponto",
    "Mudança de Ponto - Empresa",
    "ONU Alarmada",
    "Problema de energia (Fonte/ONU)",
    "Quedas de Conexão",
    "Ter - OS de quedas",
    "Sem Conexão",
    "Ter - OS de sem conexão",
    "Lentidão",
    "Ter - OS de lentidão"
]

def dentro_do_expediente(tecnico_id):
    agora = datetime.now(timezone('America/Sao_Paulo')).time()
    horario = expediente_colaboradores.get(tecnico_id)
    if not horario:
        return False
    inicio = datetime.strptime(horario['inicio'], '%H:%M').time()
    fim = datetime.strptime(horario['fim'], '%H:%M').time()
    return inicio <= agora <= fim

def carregar_ultimo_indice():
    try:
        with open("rodizio_index.txt", "r") as f:
            return int(f.read())
    except:
        return 0

def salvar_indice_atual(indice):
    with open("rodizio_index.txt", "w") as f:
        f.write(str(indice))

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

def distribuir_reagendamento():
    hoje = datetime.now(timezone('America/Sao_Paulo')).weekday()
    if hoje == 6:
        print("📅 Hoje é domingo. Cancelando envio.")
        return

    whatsapp_token = autenticar_whats_ticket()

    headers_listar = {
        'Authorization': token,
        'Content-Type': 'application/json',
        'ixcsoft': 'listar'
    }
    headers_put = {
        'Authorization': token,
        'Content-Type': 'application/json'
    }

    url_oss = 'https://assinante.nmultifibra.com.br/webservice/v1/su_oss_chamado'
    body_oss = {
        "qtype": "status",
        "query": "RAG",
        "oper": "=",
        "page": "1",
        "rp": "1000"
    }
    response_oss = requests.post(url_oss, headers=headers_listar, json=body_oss)
    registros_oss = response_oss.json().get('registros', [])

    # Mapear id_assunto -> nome
    url_assuntos = 'https://assinante.nmultifibra.com.br/webservice/v1/su_oss_assunto'
    response_assuntos = requests.post(url_assuntos, headers=headers_listar, json={"page": "1", "rp": "1000"})
    registros_assuntos = response_assuntos.json().get('registros', [])
    assuntos_map = {str(a['id']): a['assunto'] for a in registros_assuntos}

    # Filtrar os chamados com status RAG e assunto permitido
    filtrados = [
        os for os in registros_oss
        if os.get('status') == 'RAG' and assuntos_map.get(str(os.get('id_assunto'))) in assuntos_permitidos
    ]

    print(f'Total chamados RAG com assuntos permitidos: {len(filtrados)}')

    ids_tecnicos = [355, 345, 359, 354, 337, 313, 367, 377]

    # Mapear id_técnico -> nome
    url_func = 'https://assinante.nmultifibra.com.br/webservice/v1/funcionarios'
    body_func = {'qtype': 'id', 'query': '0', 'oper': '>', 'page': '1', 'rp': '1000'}
    resp_func = requests.post(url_func, headers=headers_listar, json=body_func)
    funcionarios_map = {int(f['id']): f['funcionario'] for f in resp_func.json().get('registros', [])}

    chamados_por_tecnico = defaultdict(list)
    indice_tecnico = carregar_ultimo_indice()
    num_tecnicos = len(ids_tecnicos)

    for chamado in filtrados:
        tentativas = 0
        while tentativas < num_tecnicos:
            tecnico_id = ids_tecnicos[indice_tecnico]
            if dentro_do_expediente(tecnico_id):
                break
            else:
                print(f"⏳ Técnico {tecnico_id} está fora do expediente. Pulando.")
                indice_tecnico = (indice_tecnico + 1) % num_tecnicos
                tentativas += 1
        else:
            print("⚠️ Nenhum técnico disponível no expediente para encaminhar o chamado.")
            break

        id_chamado = chamado['id']
        busca = {"qtype": "id", "query": str(id_chamado), "oper": "=", "page": "1", "rp": "1"}
        resp_busca = requests.post(url_oss, headers=headers_listar, json=busca)
        regs = resp_busca.json().get('registros', [])
        if not regs:
            print(f"Chamado {id_chamado} não encontrado.")
            indice_tecnico = (indice_tecnico + 1) % num_tecnicos
            salvar_indice_atual(indice_tecnico)
            continue
        detalhado = regs[0]

        detalhado['id_tecnico'] = tecnico_id
        detalhado['status'] = 'EN'
        detalhado['setor'] = '5'

        resp_put = requests.put(f"{url_oss}/{id_chamado}", headers=headers_put, json=detalhado)
        if resp_put.status_code != 200:
            print(f"Erro ao atualizar {id_chamado}: {resp_put.status_code}")
            indice_tecnico = (indice_tecnico + 1) % num_tecnicos
            salvar_indice_atual(indice_tecnico)
            continue

        print(f"Chamado {id_chamado} encaminhado para técnico {tecnico_id}")

        if whatsapp_token:
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

            chamados_por_tecnico[tecnico_id].append(chamado['id_assunto'])
            contagem = Counter(chamados_por_tecnico[tecnico_id])
            nome_tec = funcionarios_map.get(tecnico_id, f"Técnico {tecnico_id}")
            nome_assunto = assuntos_map.get(str(chamado['id_assunto']), f"Assunto {chamado['id_assunto']}")

            mensagem = "⚠️ Envio de Demandas ⚠️\n\n"
            mensagem += f"Responsável: *{nome_tec}*\n\n"
            mensagem += f"- Cliente: *{nome_cliente}*\n"
            mensagem += f"- Assunto: *{nome_assunto}* (Reagendamento de OS)\n"


            enviar_whatsapp(id_fila=31, mensagem=mensagem.strip(), token=whatsapp_token)

        indice_tecnico = (indice_tecnico + 1) % num_tecnicos
        salvar_indice_atual(indice_tecnico)

    print("⏱️ Executando rotina de encaminhar chamados…")

def main():
    scheduler = BlockingScheduler(timezone="America/Sao_Paulo")
    trigger = CronTrigger(minute="*/25", hour="7-19", second="0")
    scheduler.add_job(distribuir_reagendamento, trigger=trigger)

    # distribuir_reagendamento()  # Executa imediatamente

    print("🚀 Agendado para rodar a cada 25 minutos.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n⛔ Encerrando scheduler...")

if __name__ == "__main__":
    main()
