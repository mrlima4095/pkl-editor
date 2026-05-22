# app.py
from flask import Flask, render_template, request, jsonify, send_file, session
import os
import pickle
import joblib
import json
from pathlib import Path
import tempfile
import shutil

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui_mude_para_algo_seguro'

# Diretório base para os arquivos
BASE_DIR = Path(tempfile.mkdtemp())
CURRENT_DIR = BASE_DIR

# Extensões suportadas
SUPPORTED_EXTENSIONS = {'.pkl', '.pickle', '.joblib'}

def load_pickle_file(filepath):
    """Carrega arquivo pickle ou joblib"""
    ext = filepath.suffix.lower()
    try:
        if ext in ['.pkl', '.pickle']:
            with open(filepath, 'rb') as f:
                return pickle.load(f)
        elif ext == '.joblib':
            return joblib.load(filepath)
    except Exception as e:
        return None

def save_pickle_file(filepath, data, file_type='pickle'):
    """Salva arquivo pickle ou joblib"""
    try:
        if file_type == 'joblib':
            joblib.dump(data, filepath)
        else:
            with open(filepath, 'wb') as f:
                pickle.dump(data, f)
        return True
    except Exception as e:
        return False

@app.route('/')
def index():
    return render_template('explorer.html')

@app.route('/api/list_files')
def list_files():
    """Lista arquivos no diretório atual"""
    path = request.args.get('path', '')
    current_path = BASE_DIR / path if path else BASE_DIR
    
    try:
        items = []
        for item in current_path.iterdir():
            items.append({
                'name': item.name,
                'is_dir': item.is_dir(),
                'size': item.stat().st_size if item.is_file() else 0,
                'modified': item.stat().st_mtime,
                'is_supported': item.suffix.lower() in SUPPORTED_EXTENSIONS if item.is_file() else False
            })
        
        # Ordenar: diretórios primeiro, depois arquivos
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        
        return jsonify({
            'success': True,
            'current_path': str(current_path.relative_to(BASE_DIR)) if current_path != BASE_DIR else '',
            'items': items,
            'parent_path': str(current_path.parent.relative_to(BASE_DIR)) if current_path != BASE_DIR else None
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/load_file')
def load_file():
    """Carrega e retorna o conteúdo de um arquivo pickle/joblib"""
    filepath = request.args.get('path', '')
    full_path = BASE_DIR / filepath
    
    if not full_path.exists() or full_path.is_dir():
        return jsonify({'success': False, 'error': 'Arquivo não encontrado'})
    
    if full_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return jsonify({'success': False, 'error': 'Formato não suportado'})
    
    data = load_pickle_file(full_path)
    if data is None:
        return jsonify({'success': False, 'error': 'Erro ao carregar o arquivo'})
    
    # Converter dados para formato serializável em JSON
    try:
        # Salvar dados temporariamente para visualização
        session['current_data'] = json.dumps(data, default=str)
        session['current_file'] = filepath
        session['current_type'] = 'joblib' if full_path.suffix == '.joblib' else 'pickle'
        
        return jsonify({
            'success': True,
            'data': data,
            'data_str': str(data)[:1000]  # Preview
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao serializar: {str(e)}'})

@app.route('/api/save_file', methods=['POST'])
def save_file():
    """Salva dados editados no arquivo"""
    data = request.json
    filepath = data.get('path', '')
    new_data = data.get('data')
    file_type = data.get('type', 'pickle')
    
    full_path = BASE_DIR / filepath
    
    if not full_path.exists():
        return jsonify({'success': False, 'error': 'Arquivo não encontrado'})
    
    # Tentar converter o dado recebido
    try:
        # Se for string JSON, converter para objeto Python
        if isinstance(new_data, str):
            new_data = json.loads(new_data)
        
        if save_pickle_file(full_path, new_data, file_type):
            return jsonify({'success': True, 'message': 'Arquivo salvo com sucesso!'})
        else:
            return jsonify({'success': False, 'error': 'Erro ao salvar arquivo'})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro: {str(e)}'})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload de arquivo pickle/joblib"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'Nenhum arquivo enviado'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'Nome de arquivo vazio'})
    
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return jsonify({'success': False, 'error': f'Tipo não suportado. Use: {", ".join(SUPPORTED_EXTENSIONS)}'})
    
    # Salvar arquivo
    save_path = BASE_DIR / file.filename
    file.save(save_path)
    
    return jsonify({'success': True, 'message': 'Arquivo enviado com sucesso!'})

@app.route('/api/create_dir', methods=['POST'])
def create_directory():
    """Cria novo diretório"""
    data = request.json
    dirname = data.get('name', '')
    current_path = data.get('path', '')
    
    if not dirname:
        return jsonify({'success': False, 'error': 'Nome inválido'})
    
    full_path = BASE_DIR / current_path / dirname
    
    try:
        full_path.mkdir(exist_ok=False)
        return jsonify({'success': True, 'message': 'Diretório criado com sucesso!'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/download/<path:filepath>')
def download_file(filepath):
    """Download de arquivo"""
    full_path = BASE_DIR / filepath
    if full_path.exists() and full_path.is_file():
        return send_file(full_path, as_attachment=True)
    return jsonify({'success': False, 'error': 'Arquivo não encontrado'})

@app.route('/api/delete', methods=['POST'])
def delete_item():
    """Deleta arquivo ou diretório"""
    data = request.json
    item_path = data.get('path', '')
    
    full_path = BASE_DIR / item_path
    
    if not full_path.exists():
        return jsonify({'success': False, 'error': 'Item não encontrado'})
    
    try:
        if full_path.is_dir():
            shutil.rmtree(full_path)
        else:
            full_path.unlink()
        return jsonify({'success': True, 'message': 'Item deletado com sucesso!'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True, port=5000)