from flask import Flask, jsonify
from flask_cors import CORS
from datetime import datetime
import os
import json

app = Flask(__name__)
CORS(app)  # Habilita CORS para requisições do front-end

# Rota principal para teste
@app.route('/')
def home():
    return jsonify({'message': '🚀 API de sinais fora do padrão está no ar!'})

# Rota para fornecer o JSON com os dados
@app.route('/api/sinais', methods=['GET'])
def get_sinais():
    filename = 'sinal_fora_padrao.json'

    if not os.path.exists(filename):
        return jsonify({'error': 'Arquivo de sinais não encontrado'}), 404

    try:
        with open(filename, 'r', encoding='utf-8') as file:
            data = json.load(file)
    except Exception as e:
        return jsonify({'error': f'Erro ao ler o arquivo: {str(e)}'}), 500

    return jsonify({
        'timestamp': datetime.fromtimestamp(os.path.getmtime(filename)).strftime("%Y-%m-%d %H:%M:%S"),  # Unix timestamp da última modificação
        'count': len(data),
        'data': data
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)