# app.py
from flask import Flask, render_template, request, jsonify, send_file
import pickle
import joblib
import json
import os
import io
import base64
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['TEMP_FOLDER'] = 'temp'

# Criar pastas necessárias
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['TEMP_FOLDER'], exist_ok=True)

class DictionaryExplorer:
    def __init__(self):
        self.data = {}
        self.current_filename = None
        self.current_filetype = None
        
    def load_from_bytes(self, file_bytes, filetype):
        """Carregar dados a partir de bytes do arquivo"""
        if filetype == 'pickle':
            self.data = pickle.loads(file_bytes)
        else:  # joblib
            self.data = joblib.load(io.BytesIO(file_bytes))
        return self.data
    
    def save_as_pickle_bytes(self):
        """Salvar dados como bytes pickle"""
        return pickle.dumps(self.data)
    
    def save_as_joblib_bytes(self):
        """Salvar dados como bytes joblib"""
        buffer = io.BytesIO()
        joblib.dump(self.data, buffer)
        return buffer.getvalue()
    
    def get_value_by_path(self, path):
        current = self.data
        for key in path:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list):
                try:
                    key = int(key) if isinstance(key, str) and key.isdigit() else key
                    current = current[key]
                except (ValueError, IndexError, TypeError):
                    return None
            else:
                return None
        return current
    
    def set_value_by_path(self, path, value):
        if not path:
            self.data = self.parse_value(value)
            return True
            
        current = self.data
        for key in path[:-1]:
            if isinstance(current, dict):
                if key not in current:
                    current[key] = {}
                current = current[key]
            elif isinstance(current, list):
                try:
                    idx = int(key) if isinstance(key, str) and key.isdigit() else key
                    if idx >= len(current):
                        current.extend([None] * (idx - len(current) + 1))
                    current = current[idx]
                except (ValueError, IndexError):
                    return False
            else:
                return False
                
        last_key = path[-1]
        
        if isinstance(current, dict):
            current[last_key] = self.parse_value(value)
        elif isinstance(current, list):
            try:
                idx = int(last_key) if isinstance(last_key, str) and last_key.isdigit() else last_key
                if idx >= len(current):
                    current.extend([None] * (idx - len(current) + 1))
                current[idx] = self.parse_value(value)
            except (ValueError, IndexError):
                return False
        return True
    
    def parse_value(self, value_str):
        # Tenta converter para JSON
        try:
            return json.loads(value_str)
        except:
            pass
        
        # Tenta converter para número
        try:
            if '.' in value_str:
                return float(value_str)
            return int(value_str)
        except:
            pass
        
        # Tenta converter para boolean
        if value_str.lower() == 'true':
            return True
        if value_str.lower() == 'false':
            return False
        
        # Mantém como string
        return value_str

explorer = DictionaryExplorer()

@app.route('/')
def index():
    return render_template('explorer.html')

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload do arquivo pickle ou joblib"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'Nenhum arquivo enviado'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'Nenhum arquivo selecionado'})
    
    # Determinar o tipo do arquivo
    filename = secure_filename(file.filename)
    if filename.endswith('.pkl'):
        filetype = 'pickle'
    elif filename.endswith('.joblib'):
        filetype = 'joblib'
    else:
        return jsonify({'success': False, 'error': 'Formato não suportado. Use .pkl ou .joblib'})
    
    try:
        # Ler o arquivo
        file_bytes = file.read()
        
        # Carregar os dados
        data = explorer.load_from_bytes(file_bytes, filetype)
        explorer.current_filename = filename
        explorer.current_filetype = filetype
        
        return jsonify({
            'success': True,
            'data': convert_to_serializable(data),
            'filename': filename,
            'filetype': filetype,
            'message': f'Arquivo {filename} carregado com sucesso!'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao carregar arquivo: {str(e)}'})

@app.route('/api/browse', methods=['POST'])
def browse():
    path = request.json.get('path', [])
    data = explorer.get_value_by_path(path)
    
    if data is None:
        return jsonify({'success': False, 'error': 'Caminho não encontrado'})
    
    return jsonify({
        'success': True,
        'data': convert_to_serializable(data),
        'path': path,
        'type': get_type_name(data)
    })

@app.route('/api/edit', methods=['POST'])
def edit_value():
    path = request.json.get('path', [])
    value = request.json.get('value', '')
    
    if explorer.set_value_by_path(path, value):
        return jsonify({'success': True, 'message': 'Valor atualizado com sucesso!'})
    return jsonify({'success': False, 'error': 'Falha ao atualizar o valor'})

@app.route('/api/download', methods=['POST'])
def download_file():
    """Download do arquivo atual"""
    if explorer.data is None:
        return jsonify({'success': False, 'error': 'Nenhum dado carregado'})
    
    filetype = request.json.get('filetype', explorer.current_filetype or 'pickle')
    
    try:
        if filetype == 'pickle':
            file_bytes = explorer.save_as_pickle_bytes()
            extension = 'pkl'
            mimetype = 'application/octet-stream'
        else:
            file_bytes = explorer.save_as_joblib_bytes()
            extension = 'joblib'
            mimetype = 'application/octet-stream'
        
        # Nome do arquivo
        original_name = explorer.current_filename if explorer.current_filename else 'data'
        name_without_ext = os.path.splitext(original_name)[0]
        download_name = f'{name_without_ext}_edited.{extension}'
        
        return send_file(
            io.BytesIO(file_bytes),
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_name
        )
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao baixar: {str(e)}'})

@app.route('/api/save', methods=['POST'])
def save_to_server():
    """Salvar arquivo no servidor (opcional)"""
    if explorer.data is None:
        return jsonify({'success': False, 'error': 'Nenhum dado carregado'})
    
    filetype = request.json.get('filetype', explorer.current_filetype or 'pickle')
    custom_name = request.json.get('filename', '')
    
    if custom_name:
        filename = secure_filename(custom_name)
        if not filename.endswith(f'.{filetype}'):
            filename += f'.{filetype}'
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'data_{timestamp}.{filetype}'
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    try:
        if filetype == 'pickle':
            with open(filepath, 'wb') as f:
                f.write(explorer.save_as_pickle_bytes())
        else:
            with open(filepath, 'wb') as f:
                f.write(explorer.save_as_joblib_bytes())
        
        return jsonify({
            'success': True,
            'message': f'Arquivo salvo como {filename}',
            'filepath': filepath
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao salvar: {str(e)}'})

def convert_to_serializable(obj, max_depth=5, current_depth=0):
    """Converter objeto para formato serializável JSON"""
    if current_depth > max_depth:
        return f"... (max depth {max_depth})"
    
    if isinstance(obj, dict):
        return {str(k): convert_to_serializable(v, max_depth, current_depth + 1) 
                for k, v in list(obj.items())[:100]}  # Limitar a 100 itens
    elif isinstance(obj, list):
        return [convert_to_serializable(item, max_depth, current_depth + 1) 
                for item in obj[:100]]  # Limitar a 100 itens
    elif isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    elif isinstance(obj, bytes):
        return f"<bytes: {len(obj)} bytes>"
    elif hasattr(obj, '__dict__'):
        return str(obj)  # Para objetos customizados
    else:
        return str(obj)

def get_type_name(obj):
    if isinstance(obj, dict):
        count = len(obj)
        return f'dicionário ({count} item{"s" if count != 1 else ""})'
    elif isinstance(obj, list):
        count = len(obj)
        return f'lista ({count} item{"s" if count != 1 else ""})'
    elif isinstance(obj, str):
        return f'texto ({len(obj)} caracteres)'
    elif isinstance(obj, int):
        return 'número inteiro'
    elif isinstance(obj, float):
        return 'número decimal'
    elif isinstance(obj, bool):
        return 'booleano'
    elif obj is None:
        return 'vazio (None)'
    elif isinstance(obj, bytes):
        return f'dados binários ({len(obj)} bytes)'
    else:
        return type(obj).__name__

if __name__ == '__main__':
    app.run(debug=True, port=5000)