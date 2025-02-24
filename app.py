from flask import Flask, render_template, request, jsonify, send_file, session
import joblib
import pickle
import os
import json
import traceback
import logging
from werkzeug.utils import secure_filename
from datetime import datetime
import inspect
import types
import sys

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'lucy-brain-explorer-secret-key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Garantir que a pasta de uploads existe
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Armazenamento global
current_brain = None
current_filename = None
current_filepath = None

# ============================================
# FUNÇÕES DE CARREGAMENTO
# ============================================

def safe_load_pkl(filepath):
    """Carrega arquivo PKL com múltiplas tentativas"""
    erros = []
    
    # Tentativa 1: Joblib (mais provável para LucyBrain)
    try:
        logger.info(f"Tentando carregar com joblib: {filepath}")
        data = joblib.load(filepath)
        logger.info("✅ Sucesso com joblib")
        return {
            'success': True,
            'data': data,
            'method': 'joblib',
            'type': type(data).__name__
        }
    except Exception as e:
        erros.append(f"joblib: {str(e)}")
        logger.warning(f"Joblib falhou: {e}")
    
    # Tentativa 2: Pickle padrão
    try:
        logger.info("Tentando pickle padrão")
        with open(filepath, 'rb') as f:
            data = pickle.load(f)
        logger.info("✅ Sucesso com pickle")
        return {
            'success': True,
            'data': data,
            'method': 'pickle',
            'type': type(data).__name__
        }
    except Exception as e:
        erros.append(f"pickle: {str(e)}")
    
    # Tentativa 3: Pickle com encoding latin1 (Python 2)
    try:
        logger.info("Tentando pickle com latin1")
        with open(filepath, 'rb') as f:
            data = pickle.load(f, encoding='latin1')
        logger.info("✅ Sucesso com pickle+latin1")
        return {
            'success': True,
            'data': data,
            'method': 'pickle+latin1',
            'type': type(data).__name__
        }
    except Exception as e:
        erros.append(f"pickle+latin1: {str(e)}")
    
    # Todas falharam
    return {
        'success': False,
        'error': 'Não foi possível carregar o arquivo',
        'details': erros
    }

def save_pkl_file(filepath, data):
    """Salva dados em PKL"""
    try:
        # Detectar tipo e escolher método apropriado
        if hasattr(data, 'neural_model'):  # É LucyBrain
            joblib.dump(data, filepath)
            logger.info("✅ LucyBrain salvo com joblib")
        else:
            with open(filepath, 'wb') as f:
                pickle.dump(data, f)
            logger.info("✅ Dados salvos com pickle")
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar: {e}")
        return False

# ============================================
# CONVERSORES PARA JSON
# ============================================

def is_lucy_brain(obj):
    """Verifica se o objeto é uma instância de LucyBrain"""
    return hasattr(obj, '__class__') and obj.__class__.__name__ == 'LucyBrain'

def convert_to_serializable(obj, max_depth=3, current_depth=0):
    """Converte objetos complexos para formatos JSON serializáveis"""
    
    if current_depth > max_depth:
        return f"<max depth reached: {type(obj).__name__}>"
    
    # Tipos básicos
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    
    # Listas e tuplas
    elif isinstance(obj, (list, tuple)):
        return [convert_to_serializable(item, max_depth, current_depth + 1) for item in obj[:50]]  # Limitar a 50 itens
    
    # Dicionários
    elif isinstance(obj, dict):
        return {str(k): convert_to_serializable(v, max_depth, current_depth + 1) 
                for k, v in list(obj.items())[:50]}  # Limitar a 50 itens
    
    # Objetos datetime
    elif isinstance(obj, datetime):
        return obj.isoformat()
    
    # Funções e métodos
    elif isinstance(obj, (types.FunctionType, types.MethodType, types.BuiltinFunctionType)):
        return f"<function {obj.__name__ if hasattr(obj, '__name__') else 'anonymous'}>"
    
    # Módulos
    elif isinstance(obj, types.ModuleType):
        return f"<module {obj.__name__}>"
    
    # LucyBrain específico
    elif is_lucy_brain(obj):
        return convert_lucy_brain(obj, max_depth, current_depth)
    
    # Objetos com __dict__
    elif hasattr(obj, '__dict__'):
        return {
            '__type__': obj.__class__.__name__,
            '__module__': obj.__class__.__module__,
            **{k: convert_to_serializable(v, max_depth, current_depth + 1) 
               for k, v in obj.__dict__.items() 
               if not k.startswith('_') and not callable(v)}
        }
    
    # Objetos com slots
    elif hasattr(obj, '__slots__'):
        return {
            '__type__': obj.__class__.__name__,
            **{slot: convert_to_serializable(getattr(obj, slot, None), max_depth, current_depth + 1)
               for slot in obj.__slots__ if hasattr(obj, slot)}
        }
    
    # Fallback
    else:
        return f"<{type(obj).__name__} object>"

def convert_lucy_brain(brain, max_depth=3, current_depth=0):
    """Conversor específico para LucyBrain"""
    if current_depth > max_depth:
        return "<LucyBrain (max depth)>"
    
    try:
        # Atributos principais
        result = {
            '__type__': 'LucyBrain',
            '__class__': brain.__class__.__name__,
            'emotional_state': getattr(brain, 'emotional_state', {}),
            'conversation_count': getattr(brain, 'conversation_count', 0),
            'conversation_history': getattr(brain, 'conversation_history', [])[-10:],  # Últimas 10
            'interaction_history': len(getattr(brain, 'interaction_history', [])),
            'neural_initialized': getattr(brain, 'neural_initialized', False),
            'training_data': len(getattr(brain, 'training_data', [])),
            'min_training_samples': getattr(brain, 'min_training_samples', 0),
            'max_training_samples': getattr(brain, 'max_training_samples', 0),
            'retrain_interval': getattr(brain, 'retrain_interval', 0),
            'learning_rate': getattr(brain, 'learning_rate', 0),
            'conversation_patterns': len(getattr(brain, 'conversation_patterns', {})),
            'response_weights': len(getattr(brain, 'response_weights', {})),
        }
        
        # Knowledge
        if hasattr(brain, 'knowledge'):
            knowledge = brain.knowledge
            result['knowledge'] = {
                'facts': len(knowledge.get('facts', [])),
                'user_teachings': len(knowledge.get('user_teachings', [])),
                'wikipedia_data': len(knowledge.get('wikipedia_data', [])),
                'duckduckgo_searches': len(knowledge.get('duckduckgo_searches', [])),
            }
            
            # Últimos ensinamentos
            teachings = knowledge.get('user_teachings', [])[-5:]
            result['recent_teachings'] = teachings
        
        # Memories
        if hasattr(brain, 'memories'):
            memories = brain.memories
            result['memories'] = {
                'conversations': len(memories.get('conversations', [])),
                'important_facts': len(memories.get('important_facts', [])),
                'user_preferences': len(memories.get('user_preferences', [])),
            }
        
        # Patterns
        if hasattr(brain, 'patterns'):
            patterns = brain.patterns
            result['patterns'] = {k: len(v) if isinstance(v, list) else str(type(v)) 
                                  for k, v in patterns.items()}
        
        # Lore
        if hasattr(brain, 'lore'):
            lore = brain.lore
            result['lore'] = {
                'name': lore.get('name', ''),
                'version': lore.get('version', ''),
                'responses': list(lore.get('responses', {}).keys()) if lore.get('responses') else []
            }
        
        # News feeds
        if hasattr(brain, 'news_feeds'):
            result['news_feeds'] = list(getattr(brain, 'news_feeds', {}).keys())
        
        # Cards
        if hasattr(brain, 'cards'):
            cards = getattr(brain, 'cards', [])
            result['cards_count'] = len(cards)
            if cards and isinstance(cards, list) and len(cards) > 0:
                result['sample_card'] = cards[0] if len(cards) > 0 else None
        
        # Sistema neural
        if brain.neural_initialized:
            result['neural'] = {
                'model': str(type(brain.neural_model)) if brain.neural_model else None,
                'vectorizer': str(type(brain.vectorizer)) if brain.vectorizer else None,
                'label_encoder': str(type(brain.label_encoder)) if brain.label_encoder else None,
                'categories': list(brain.label_encoder.classes_) if brain.label_encoder else []
            }
        
        return result
        
    except Exception as e:
        logger.error(f"Erro ao converter LucyBrain: {e}")
        return {
            '__type__': 'LucyBrain',
            'error': str(e)
        }

# ============================================
# ROTAS PRINCIPAIS
# ============================================

@app.route('/')
def index():
    """Página principal"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Upload de arquivo PKL"""
    global current_brain, current_filename, current_filepath
    
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nome de arquivo vazio'}), 400
    
    if not file.filename.endswith('.pkl'):
        return jsonify({'error': 'Arquivo deve ser .pkl'}), 400
    
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    try:
        file.save(filepath)
        logger.info(f"Arquivo salvo: {filepath} ({os.path.getsize(filepath)} bytes)")
        
        # Carregar arquivo
        result = safe_load_pkl(filepath)
        
        if not result['success']:
            return jsonify({
                'error': 'Falha ao carregar',
                'details': result.get('details', [])
            }), 500
        
        current_brain = result['data']
        current_filename = filename
        current_filepath = filepath
        
        # Converter para serializável
        serializable = convert_to_serializable(current_brain)
        
        # Estatísticas rápidas
        stats = {}
        if is_lucy_brain(current_brain):
            try:
                stats = {
                    'emotional': current_brain.get_emotional_state() if hasattr(current_brain, 'get_emotional_state') else {},
                    'knowledge_total': current_brain.get_knowledge_count() if hasattr(current_brain, 'get_knowledge_count') else 0,
                    'memories_total': current_brain.get_memory_count() if hasattr(current_brain, 'get_memory_count') else 0,
                    'neural_stats': current_brain.get_neural_stats() if hasattr(current_brain, 'get_neural_stats') else {}
                }
            except Exception as e:
                logger.error(f"Erro ao obter estatísticas: {e}")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'method': result['method'],
            'type': result['type'],
            'data': serializable,
            'stats': stats,
            'is_lucy_brain': is_lucy_brain(current_brain)
        })
        
    except Exception as e:
        logger.error(f"Erro no upload: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/save', methods=['POST'])
def save_file():
    """Salva alterações"""
    global current_brain, current_filepath
    
    if current_brain is None or current_filepath is None:
        return jsonify({'error': 'Nenhum arquivo carregado'}), 400
    
    try:
        if save_pkl_file(current_filepath, current_brain):
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Erro ao salvar'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download')
def download_file():
    """Download do arquivo atual"""
    global current_filepath, current_filename
    
    if current_filepath is None or not os.path.exists(current_filepath):
        return jsonify({'error': 'Arquivo não encontrado'}), 404
    
    return send_file(current_filepath, as_attachment=True, download_name=current_filename)

@app.route('/data')
def get_data():
    """Retorna dados serializados"""
    global current_brain
    
    if current_brain is None:
        return jsonify({'error': 'Nenhum dado carregado'}), 404
    
    return jsonify({
        'data': convert_to_serializable(current_brain),
        'type': type(current_brain).__name__,
        'is_lucy_brain': is_lucy_brain(current_brain)
    })

@app.route('/brain_stats')
def brain_stats():
    """Estatísticas detalhadas do LucyBrain"""
    global current_brain
    
    if current_brain is None or not is_lucy_brain(current_brain):
        return jsonify({'error': 'Nenhum LucyBrain carregado'}), 404
    
    try:
        stats = {}
        
        # Coletar estatísticas de forma segura
        if hasattr(current_brain, 'get_emotional_state'):
            stats['emotional'] = current_brain.get_emotional_state()
        
        if hasattr(current_brain, 'get_neural_stats'):
            stats['neural'] = current_brain.get_neural_stats()
        
        if hasattr(current_brain, 'get_knowledge_count'):
            stats['knowledge_count'] = current_brain.get_knowledge_count()
        
        if hasattr(current_brain, 'get_memory_count'):
            stats['memory_count'] = current_brain.get_memory_count()
        
        if hasattr(current_brain, 'analyze_conversation_quality'):
            stats['conversation_quality'] = current_brain.analyze_conversation_quality()
        
        if hasattr(current_brain, 'get_neural_insights'):
            stats['neural_insights'] = current_brain.get_neural_insights()
        
        # Dados brutos importantes
        stats['conversation_count'] = getattr(current_brain, 'conversation_count', 0)
        stats['training_samples'] = len(getattr(current_brain, 'training_data', []))
        stats['patterns_count'] = len(getattr(current_brain, 'conversation_patterns', {}))
        stats['neural_initialized'] = getattr(current_brain, 'neural_initialized', False)
        
        # Informações de arquivos
        stats['knowledge_files'] = {
            'knowledge.json': os.path.exists(getattr(current_brain, 'knowledge_file', '')),
            'memories.json': os.path.exists(getattr(current_brain, 'memories_file', '')),
            'neural_model.pkl': os.path.exists(getattr(current_brain, 'neural_model_file', ''))
        }
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/update_attribute', methods=['POST'])
def update_attribute():
    """Atualiza um atributo específico"""
    global current_brain
    
    if current_brain is None:
        return jsonify({'error': 'Nenhum dado carregado'}), 400
    
    data = request.json
    path = data.get('path', [])
    value = data.get('value')
    
    try:
        # Navegar até o atributo
        obj = current_brain
        for key in path[:-1]:
            if hasattr(obj, key):
                obj = getattr(obj, key)
            elif isinstance(obj, dict) and key in obj:
                obj = obj[key]
            elif isinstance(obj, list) and key.isdigit() and 0 <= int(key) < len(obj):
                obj = obj[int(key)]
            else:
                return jsonify({'error': f'Caminho inválido: {key}'}), 400
        
        # Atualizar
        last_key = path[-1]
        if hasattr(obj, last_key):
            setattr(obj, last_key, value)
        elif isinstance(obj, dict):
            obj[last_key] = value
        elif isinstance(obj, list) and last_key.isdigit():
            idx = int(last_key)
            if 0 <= idx < len(obj):
                obj[idx] = value
            else:
                return jsonify({'error': 'Índice inválido'}), 400
        else:
            return jsonify({'error': 'Não foi possível atualizar'}), 400
        
        return jsonify({
            'success': True,
            'data': convert_to_serializable(current_brain)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/inspect')
def inspect_brain():
    """Inspeciona métodos e atributos do LucyBrain"""
    global current_brain
    
    if current_brain is None or not is_lucy_brain(current_brain):
        return jsonify({'error': 'Nenhum LucyBrain carregado'}), 404
    
    try:
        methods = []
        attributes = []
        
        for name in dir(current_brain):
            if name.startswith('_'):
                continue
            
            attr = getattr(current_brain, name)
            if callable(attr):
                # É um método
                sig = str(inspect.signature(attr)) if hasattr(inspect, 'signature') else '(...)'
                doc = inspect.getdoc(attr)
                methods.append({
                    'name': name,
                    'signature': f"{name}{sig}",
                    'doc': doc[:100] + '...' if doc and len(doc) > 100 else doc
                })
            else:
                # É um atributo
                try:
                    value_repr = str(attr)[:100]
                    if len(str(attr)) > 100:
                        value_repr += '...'
                except:
                    value_repr = '<unprintable>'
                
                attributes.append({
                    'name': name,
                    'type': type(attr).__name__,
                    'value': value_repr
                })
        
        return jsonify({
            'methods': methods[:50],  # Limitar a 50
            'attributes': attributes[:50]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 50)
    print("🧠 EXPLORADOR DE PKL - LUCYBRAIN EDITION")
    print("=" * 50)
    print("🚀 Servidor iniciado em: http://localhost:5000")
    print("📁 Pasta de uploads: ./uploads")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)

    