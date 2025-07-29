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
from collections import defaultdict, Counter
from datetime import datetime
from pytz import timezone

from dotenv import load_dotenv
import os

# Carregar variáveis do .env
load_dotenv()

token = os.getenv('TOKEN_API')

BASE_URL = 'http://10.0.100.128:5009'

def consulta_sinalAlto():
    # URLs
    url_radpop = "https://assinante.nmultifibra.com.br/webservice/v1/radpop_radio_cliente_fibra"
    url_contrato = "https://assinante.nmultifibra.com.br/webservice/v1/cliente_contrato"
    url_cliente = "https://assinante.nmultifibra.com.br/webservice/v1/cliente"

    # Mapeamento de OLTs por ID
    olt_map = {
        1: "OLT_COTIA_01_ANTIGA",
        2: "OLT_ITPV_01",
        3: "OLT_EMBU_01",
        4: "OLT_COTIA_02_ANTIGA",
        7: "OLT_COTIA_03_ANTIGA",
        9: "OLT_TRMS_02",
        12: "OLT_VGPA_01",
        14: "OLT_COTIA_03",
        15: "OLT_TRMS_01",
        16: "OLT_CCDA_01",
        17: "OLT_GRVN_01",
        20: "OLT_CCDA_02",
        21: "OLT_COTIA_01",
        22: "OLT_COTIA_04",
        23: "OLT_COTIA_05",
        24: "OLT_COTIA_02",
        26: "OLT_CPTR_01"
    }

    # Cabeçalhos
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "ixcsoft": "listar"
    }

    # Consulta os clientes de fibra
    body_radpop = {
        "qtype": "sinal_tx",
        "query": "-30",
        "oper": "<=",
        "page": "1",
        "rp": "1000"
    }
    
    response_radpop = requests.post(url_radpop, headers=headers, json=body_radpop)
    clientes_fibra = response_radpop.json().get("registros", [])

    contratos_validos = []

    for cliente in clientes_fibra:
        id_contrato = cliente.get("id_contrato")
        if not id_contrato:
            continue

        # Consulta dados do contrato
        body_contrato = {
            "qtype": "id",
            "query": str(id_contrato),
            "oper": "=",
            "page": "1",
            "rp": "1"
        }
        response_contrato = requests.post(url_contrato, headers=headers, json=body_contrato)
        contrato_data = response_contrato.json().get("registros", [{}])[0]

        rua = contrato_data.get("endereco", "")
        numero = contrato_data.get("numero", "")
        bairro = contrato_data.get("bairro", "")
        id_cliente = contrato_data.get("id_cliente")

        # Se não encontrar endereço, consulta diretamente o cliente
        if not (rua and numero and bairro) and id_cliente:
            body_cliente = {
                "qtype": "id",
                "query": str(id_cliente),
                "oper": "=",
                "page": "1",
                "rp": "1"
            }
            response_cliente = requests.post(url_cliente, headers=headers, json=body_cliente)
            cliente_info = response_cliente.json().get("registros", [{}])[0]

            rua = cliente_info.get("endereco", "") or ""
            numero = cliente_info.get("numero", "") or ""
            bairro = cliente_info.get("bairro", "") or ""

            contatos = {
                "contato": cliente_info.get("contato", "") or "",
                "whatsapp": cliente_info.get("whatsapp", "") or "",
                "celular": cliente_info.get("telefone_celular", "") or "",
                "comercial": cliente_info.get("telefone_comercial", "") or ""
            }
        else:
            # Se já tinha endereço, busca só os contatos (cliente precisa ser conhecido)
            contatos = {}
            if id_cliente:
                body_cliente = {
                    "qtype": "id",
                    "query": str(id_cliente),
                    "oper": "=",
                    "page": "1",
                    "rp": "1"
                }
                response_cliente = requests.post(url_cliente, headers=headers, json=body_cliente)
                cliente_info = response_cliente.json().get("registros", [{}])[0]

                contatos = {
                    "contato": cliente_info.get("contato", "") or "",
                    "whatsapp": cliente_info.get("whatsapp", "") or "",
                    "celular": cliente_info.get("telefone_celular", "") or "",
                    "comercial": cliente_info.get("telefone_comercial", "") or ""
                }

        id_olt = int(cliente.get("id_transmissor", 0))

        contratos_validos.append({
            "id_cliente": str(id_cliente) if id_cliente else "",
            "id_contrato": str(id_contrato),
            "olt": olt_map.get(id_olt, "OLT Desconhecida"),
            "login": cliente.get("id_login", ""),
            "ponid": cliente.get("ponid", ""),
            "mac": cliente.get("mac", ""),
            "rx": cliente.get("sinal_rx"),
            "tx": cliente.get("sinal_tx"),
            "endereco": {
                "rua": rua,
                "numero": numero,
                "bairro": bairro
            },
            "contatos": contatos
        })

    # Salvar o JSON em um arquivo
    with open("sinal_fora_padrao.json", "w", encoding="utf-8") as f:
        json.dump(contratos_validos, f, indent=2, ensure_ascii=False)

    print("✅ Arquivo sinal_fora_padrao.json gerado com sucesso.")

def main():
    scheduler = BlockingScheduler(timezone="America/Sao_Paulo")

    # Cron 06h00 e 22h00 todos os dias
    trigger = CronTrigger(hour="6,22", minute="0", second="0", day_of_week="0-6")
    scheduler.add_job(consulta_sinalAlto, trigger=trigger)

    consulta_sinalAlto()  # Executa imediatamente

    print("🚀 Agendado para rodar às 06h00 e 22h00 todos os dias.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n⛔ Encerrando scheduler...")

if __name__ == "__main__":
    main()