import streamlit as st
import pandas as pd
import json
from datetime import datetime
import mysql.connector
from mysql.connector import Error
import urllib.parse
from streamlit.components.v1 import html

# --- Configurações do Banco AWS ---
try:
    DB_CONFIG = {
        'host': st.secrets["aws_db"]["host"],
        'user': st.secrets["aws_db"]["user"],
        'password': st.secrets["aws_db"]["password"],
        'database': st.secrets["aws_db"]["database"],
        'port': 3306
    }
    DB_AVAILABLE = True
except Exception as e:
    st.warning("⚠️ Banco de dados AWS não disponível. Usando modo local.")
    DB_CONFIG = {}
    DB_AVAILABLE = False

# --- Estado da Sessão ---
if 'unsaved_changes' not in st.session_state:
    st.session_state.unsaved_changes = False

if 'local_data' not in st.session_state:
    st.session_state.local_data = {}

if 'mock_snapshots' not in st.session_state:
    st.session_state.mock_snapshots = {}

# --- Funções de Banco de Dados ---

def get_db_connection():
    if not DB_AVAILABLE:
        return None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        st.error(f"Erro de conexão: {e}")
        return None

def create_snapshots_table():
    if not DB_AVAILABLE:
        return  # Não tenta criar tabela se DB não está disponível
    
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            create_table_query = """
            CREATE TABLE IF NOT EXISTS snapshots (
                id INT AUTO_INCREMENT PRIMARY KEY,
                empreendimento VARCHAR(255) NOT NULL,
                version_name VARCHAR(255) NOT NULL,
                snapshot_data JSON NOT NULL,
                created_date VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_snapshot (empreendimento, version_name)
            )
            """
            cursor.execute(create_table_query)
            conn.commit()
        except Error as e:
            st.error(f"Erro ao criar tabela: {e}")
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()

def load_snapshots():
    if not DB_AVAILABLE:
        return st.session_state.mock_snapshots
    
    conn = get_db_connection()
    if conn:
        snapshots = {}
        try:
            cursor = conn.cursor(dictionary=True)
            query = "SELECT empreendimento, version_name, snapshot_data, created_date FROM snapshots ORDER BY created_at DESC"
            cursor.execute(query)
            results = cursor.fetchall()
            for row in results:
                empreendimento = row['empreendimento']
                version_name = row['version_name']
                if empreendimento not in snapshots:
                    snapshots[empreendimento] = {}
                snapshot_data = json.loads(row['snapshot_data'])
                snapshots[empreendimento][version_name] = {
                    "date": row['created_date'],
                    "data": snapshot_data
                }
            return snapshots
        except Error as e:
            st.error(f"Erro ao carregar snapshots: {e}")
            return st.session_state.mock_snapshots
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        return st.session_state.mock_snapshots

def save_snapshot(empreendimento, version_name, snapshot_data, created_date):
    if not DB_AVAILABLE:
        # Modo local - salva no session_state
        if empreendimento not in st.session_state.mock_snapshots:
            st.session_state.mock_snapshots[empreendimento] = {}
        st.session_state.mock_snapshots[empreendimento][version_name] = {
            "date": created_date,
            "data": snapshot_data
        }
        return True
    
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            snapshot_json = json.dumps(snapshot_data)
            insert_query = """
            INSERT INTO snapshots (empreendimento, version_name, snapshot_data, created_date)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE snapshot_data = VALUES(snapshot_data), created_date = VALUES(created_date)
            """
            cursor.execute(insert_query, (empreendimento, version_name, snapshot_json, created_date))
            conn.commit()
            return True
        except Error as e:
            st.error(f"Erro ao salvar snapshot: {e}")
            return False
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        # Fallback para modo local
        if empreendimento not in st.session_state.mock_snapshots:
            st.session_state.mock_snapshots[empreendimento] = {}
        st.session_state.mock_snapshots[empreendimento][version_name] = {
            "date": created_date,
            "data": snapshot_data
        }
        return True

def delete_snapshot(empreendimento, version_name):
    if not DB_AVAILABLE:
        # Modo local - remove do session_state
        if empreendimento in st.session_state.mock_snapshots and version_name in st.session_state.mock_snapshots[empreendimento]:
            del st.session_state.mock_snapshots[empreendimento][version_name]
            return True
        return False
    
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            delete_query = "DELETE FROM snapshots WHERE empreendimento = %s AND version_name = %s"
            cursor.execute(delete_query, (empreendimento, version_name))
            conn.commit()
            return cursor.rowcount > 0
        except Error as e:
            st.error(f"Erro ao deletar snapshot: {e}")
            return False
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        # Fallback para modo local
        if empreendimento in st.session_state.mock_snapshots and version_name in st.session_state.mock_snapshots[empreendimento]:
            del st.session_state.mock_snapshots[empreendimento][version_name]
            return True
        return False

# --- Funções para Gerenciar Dados Locais ---

def save_local_data(empreendimento, version_name, snapshot_data):
    """Salva dados no localStorage via JavaScript"""
    key = f"snapshot_{empreendimento}_{version_name}"
    data_to_save = {
        'empreendimento': empreendimento,
        'version_name': version_name,
        'snapshot_data': snapshot_data,
        'created_date': datetime.now().strftime("%d/%m/%Y"),
        'saved_to_aws': False
    }
    
    js_code = f"""
    <script>
        const data = {json.dumps(data_to_save)};
        localStorage.setItem('{key}', JSON.stringify(data));
        console.log('Dados salvos localmente:', '{key}');
        
        // Marcar que há mudanças não salvas
        localStorage.setItem('has_unsaved_changes', 'true');
        
        // Atualizar o estado do Streamlit
        window.parent.postMessage({{
            type: 'streamlit:setComponentValue',
            value: {{
                action: 'local_data_saved',
                key: '{key}',
                has_unsaved_changes: true
            }}
        }}, '*');
    </script>
    """
    html(js_code, height=0)
    st.session_state.unsaved_changes = True

def get_local_data():
    """Recupera todos os dados do localStorage"""
    js_code = """
    <script>
        function getAllLocalStorageData() {
            const data = {};
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                if (key.startsWith('snapshot_')) {
                    try {
                        data[key] = JSON.parse(localStorage.getItem(key));
                    } catch (e) {
                        console.error('Erro ao parsear:', key, e);
                    }
                }
            }
            const has_unsaved_changes = localStorage.getItem('has_unsaved_changes') === 'true';
            return { data, has_unsaved_changes };
        }
        
        const localData = getAllLocalStorageData();
        window.parent.postMessage({
            type: 'streamlit:setComponentValue',
            value: {
                action: 'local_data_loaded',
                data: localData.data,
                has_unsaved_changes: localData.has_unsaved_changes
            }
        }, '*');
    </script>
    """
    html(js_code, height=0)

def clear_local_data():
    """Limpa todos os dados locais"""
    js_code = """
    <script>
        // Remove apenas os dados da aplicação, mantendo outras chaves
        const keysToRemove = [];
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key.startsWith('snapshot_') || key === 'has_unsaved_changes') {
                keysToRemove.push(key);
            }
        }
        keysToRemove.forEach(key => localStorage.removeItem(key));
        console.log('Dados locais limpos');
        
        window.parent.postMessage({
            type: 'streamlit:setComponentValue',
            value: {
                action: 'local_data_cleared',
                has_unsaved_changes: false
            }
        }, '*');
    </script>
    """
    html(js_code, height=0)

def setup_before_unload():
    """Configura o aviso antes de fechar/recarregar a página"""
    js_code = """
    <script>
        function setupBeforeUnload() {
            window.addEventListener('beforeunload', function (e) {
                const hasUnsavedChanges = localStorage.getItem('has_unsaved_changes') === 'true';
                if (hasUnsavedChanges) {
                    e.preventDefault();
                    e.returnValue = 'Você tem alterações não salvas. Tem certeza que deseja sair?';
                    return 'Você tem alterações não salvas. Tem certeza que deseja sair?';
                }
            });
        }
        
        // Executar quando a página carregar
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', setupBeforeUnload);
        } else {
            setupBeforeUnload();
        }
        
        console.log('Beforeunload handler configurado');
    </script>
    """
    html(js_code, height=0)

# --- Função para criar DataFrame de exemplo ---

def create_mock_dataframe():
    data = {
        'ID_Tarefa': [1, 2, 3, 4, 5, 6],
        'Empreendimento': ['Projeto A', 'Projeto A', 'Projeto B', 'Projeto B', 'Projeto A', 'Projeto B'],
        'Tarefa': ['Fase 1', 'Fase 2', 'Design', 'Implementação', 'Teste', 'Deploy'],
        'Real_Inicio': [pd.to_datetime('2025-10-01'), pd.to_datetime('2025-10-15'), pd.to_datetime('2025-11-01'), pd.to_datetime('2025-11-10'), pd.to_datetime('2025-10-26'), pd.to_datetime('2025-11-21')],
        'Real_Fim': [pd.to_datetime('2025-10-10'), pd.to_datetime('2025-10-25'), pd.to_datetime('2025-11-05'), pd.to_datetime('2025-11-20'), pd.to_datetime('2025-11-05'), pd.to_datetime('2025-11-25')],
        'P0_Previsto_Inicio': [pd.to_datetime('2025-09-25'), pd.to_datetime('2025-10-12'), pd.to_datetime('2025-10-28'), pd.to_datetime('2025-11-08'), pd.to_datetime('2025-10-20'), pd.to_datetime('2025-11-18')],
        'P0_Previsto_Fim': [pd.to_datetime('2025-10-05'), pd.to_datetime('2025-10-20'), pd.to_datetime('2025-11-03'), pd.to_datetime('2025-11-15'), pd.to_datetime('2025-10-30'), pd.to_datetime('2025-11-22')],
    }
    df = pd.DataFrame(data)
    df['Previsto_Inicio'] = df['P0_Previsto_Inicio']
    df['Previsto_Fim'] = df['P0_Previsto_Fim']
    return df

# --- Lógica de Snapshot ---

def take_snapshot(df, empreendimento, save_locally=True):
    df_empreendimento = df[df['Empreendimento'] == empreendimento].copy()
    
    existing_snapshots = load_snapshots()
    empreendimento_snapshots = existing_snapshots.get(empreendimento, {})
    existing_versions = [k for k in empreendimento_snapshots.keys() if k.startswith('P') and k.split('-')[0][1:].isdigit()]
    
    next_n = 1
    if existing_versions:
        max_n = 0
        for version_name in existing_versions:
            try:
                n_str = version_name.split('-')[0][1:]
                n = int(n_str)
                if n > max_n:
                    max_n = n
            except ValueError:
                continue
        next_n = max_n + 1
    
    version_prefix = f"P{next_n}"
    current_date_str = datetime.now().strftime("%d/%m/%Y")
    version_name = f"{version_prefix}-({current_date_str})"
    
    df_snapshot = df_empreendimento[['ID_Tarefa', 'Real_Inicio', 'Real_Fim']].copy()
    df_snapshot['Real_Inicio'] = df_snapshot['Real_Inicio'].dt.strftime('%Y-%m-%d')
    df_snapshot['Real_Fim'] = df_snapshot['Real_Fim'].dt.strftime('%Y-%m-%d')
    
    snapshot_data = df_snapshot.rename(
        columns={'Real_Inicio': f'{version_prefix}_Previsto_Inicio', 'Real_Fim': f'{version_prefix}_Previsto_Fim'}
    ).to_dict('records')

    if save_locally:
        # Salva localmente primeiro
        save_local_data(empreendimento, version_name, snapshot_data)
        return version_name, True  # True indica que foi salvo localmente
    else:
        # Salva diretamente na AWS (ou modo local)
        success = save_snapshot(empreendimento, version_name, snapshot_data, current_date_str)
        return version_name, success

def save_local_to_aws():
    """Salva todos os dados locais na AWS"""
    local_data = st.session_state.get('local_data', {})
    saved_count = 0
    error_count = 0
    
    for key, data in local_data.items():
        if not data.get('saved_to_aws', False):
            success = save_snapshot(
                data['empreendimento'],
                data['version_name'],
                data['snapshot_data'],
                data['created_date']
            )
            if success:
                data['saved_to_aws'] = True
                saved_count += 1
                
                # Remove do localStorage após salvar na AWS
                js_code = f"""
                <script>
                    localStorage.removeItem('{key}');
                    console.log('Dados movidos para AWS e removidos do localStorage:', '{key}');
                </script>
                """
                html(js_code, height=0)
            else:
                error_count += 1
    
    # Atualiza flag de mudanças não salvas
    if saved_count > 0 and error_count == 0:
        js_code = """
        <script>
            localStorage.setItem('has_unsaved_changes', 'false');
        </script>
        """
        html(js_code, height=0)
        st.session_state.unsaved_changes = False
    
    return saved_count, error_count

# --- Menu de Contexto Simplificado e Funcional ---

def create_context_menu(selected_empreendimento, snapshots, local_snapshots):
    """Cria um menu de contexto funcional e robusto"""
    
    # Prepara dados para o JavaScript
    snapshots_data = {}
    for version, data in snapshots.items():
        snapshots_data[version] = {'type': 'aws', 'date': data['date']}
    
    for version, data in local_snapshots.items():
        snapshots_data[version] = {'type': 'local', 'date': data['created_date']}
    
    html_code = f"""
<div id="gantt-area" style="height: 300px; border: 2px dashed #ccc; display: flex; align-items: center; justify-content: center; background-color: #f9f9f9; cursor: pointer; margin: 20px 0; position: relative;">
    <div style="text-align: center;">
        <h3>Área do Gráfico de Gantt</h3>
        <p>Clique com o botão direito para abrir o menu de snapshot</p>
        <p style="font-size: 12px; color: #666;">Snapshots são salvos localmente primeiro</p>
    </div>
</div>

<style>
.context-menu {{
    position: fixed;
    background: white;
    border: 1px solid #ccc;
    border-radius: 5px;
    box-shadow: 2px 2px 10px rgba(0,0,0,0.2);
    z-index: 1000;
    display: none;
    min-width: 250px;
    max-height: 400px;
    overflow-y: auto;
}}
.context-menu-item {{
    padding: 10px 15px;
    cursor: pointer;
    border-bottom: 1px solid #eee;
    display: flex;
    align-items: center;
    gap: 8px;
}}
.context-menu-item:hover {{
    background: #f0f0f0;
}}
.context-menu-item:last-child {{
    border-bottom: none;
}}
.context-menu-divider {{
    height: 1px;
    background: #eee;
    margin: 5px 0;
}}
.context-menu-section {{
    padding: 8px 15px;
    background: #f8f9fa;
    font-weight: bold;
    font-size: 0.9em;
    color: #666;
}}
.context-menu-version {{
    padding: 8px 15px;
    font-size: 0.85em;
    color: #666;
    border-left: 3px solid #ddd;
}}
.context-menu-version.aws {{
    border-left-color: #28a745;
}}
.context-menu-version.local {{
    border-left-color: #ffc107;
}}
</style>

<script>
// Dados dos snapshots
const snapshots = {json.dumps(snapshots_data)};

// Cria o menu de contexto
const menu = document.createElement('div');
menu.className = 'context-menu';
menu.innerHTML = `
    <div class="context-menu-item" onclick="takeSnapshot()">
        <span>📸</span>
        <span>Tirar Snapshot (Local)</span>
    </div>
    <div class="context-menu-divider"></div>
    <div class="context-menu-section">Restaurar Snapshot:</div>
    <div id="restore-section"></div>
    <div class="context-menu-divider"></div>
    <div class="context-menu-section">Deletar Snapshot:</div>
    <div id="delete-section"></div>
`;
document.body.appendChild(menu);

// Preenche as seções de restore e delete
function populateSnapshotSections() {{
    const restoreSection = document.getElementById('restore-section');
    const deleteSection = document.getElementById('delete-section');
    
    restoreSection.innerHTML = '';
    deleteSection.innerHTML = '';
    
    if (Object.keys(snapshots).length === 0) {{
        restoreSection.innerHTML = '<div class="context-menu-version">Nenhum snapshot disponível</div>';
        deleteSection.innerHTML = '<div class="context-menu-version">Nenhum snapshot disponível</div>';
        return;
    }}
    
    for (const [version, data] of Object.entries(snapshots)) {{
        const typeIcon = data.type === 'aws' ? '☁️' : '💾';
        const typeClass = data.type === 'aws' ? 'aws' : 'local';
        
        // Item para restaurar
        const restoreItem = document.createElement('div');
        restoreItem.className = `context-menu-item context-menu-version ${{typeClass}}`;
        restoreItem.innerHTML = `
            <span>${{typeIcon}}</span>
            <span style="flex: 1;">${{version}}</span>
        `;
        restoreItem.onclick = (e) => {{
            e.stopPropagation();
            restoreSnapshot(version);
        }};
        restoreSection.appendChild(restoreItem);
        
        // Item para deletar
        const deleteItem = document.createElement('div');
        deleteItem.className = `context-menu-item context-menu-version ${{typeClass}}`;
        deleteItem.innerHTML = `
            <span>🗑️</span>
            <span style="flex: 1;">${{version}}</span>
        `;
        deleteItem.onclick = (e) => {{
            e.stopPropagation();
            deleteSnapshot(version);
        }};
        deleteSection.appendChild(deleteItem);
    }}
}}

// Funções do menu
function takeSnapshot() {{
    hideMenu();
    const link = document.createElement('a');
    link.href = `?snapshot_action=take_snapshot&empreendimento={selected_empreendimento}&timestamp=${{Date.now()}}`;
    link.click();
}}

function restoreSnapshot(versionName) {{
    hideMenu();
    const link = document.createElement('a');
    link.href = `?snapshot_action=restore_snapshot&empreendimento={selected_empreendimento}&version=${{encodeURIComponent(versionName)}}&timestamp=${{Date.now()}}`;
    link.click();
}}

function deleteSnapshot(versionName) {{
    hideMenu();
    const link = document.createElement('a');
    link.href = `?snapshot_action=delete_snapshot&empreendimento={selected_empreendimento}&version=${{encodeURIComponent(versionName)}}&timestamp=${{Date.now()}}`;
    link.click();
}}

function showMenu(x, y) {{
    populateSnapshotSections();
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';
    menu.style.display = 'block';
}}

function hideMenu() {{
    menu.style.display = 'none';
}}

// Event listeners
document.getElementById('gantt-area').addEventListener('contextmenu', function(e) {{
    e.preventDefault();
    showMenu(e.pageX, e.pageY);
}});

document.addEventListener('click', function(e) {{
    if (!menu.contains(e.target)) {{
        hideMenu();
    }}
}});

// Fecha o menu com ESC
document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') {{
        hideMenu();
    }}
}});

// Inicializa as seções quando o menu é carregado
populateSnapshotSections();
</script>
"""
    return html_code

# --- Função para processar ações do menu ---

def process_snapshot_actions():
    """Processa ações do menu de contexto via query parameters"""
    query_params = st.query_params
    
    action = query_params.get('snapshot_action')
    empreendimento = query_params.get('empreendimento')
    version = query_params.get('version')
    
    if action and empreendimento:
        # Limpa os parâmetros
        st.query_params.clear()
        
        df = create_mock_dataframe()
        
        if action == 'take_snapshot':
            try:
                version_name, saved_locally = take_snapshot(df, empreendimento, save_locally=True)
                if saved_locally:
                    st.success(f"✅ Snapshot '{version_name}' salvo localmente!")
                    st.info("💡 Use o botão 'Enviar para AWS' na barra lateral para salvar permanentemente.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao criar snapshot: {e}")
        
        elif action == 'restore_snapshot' and version:
            st.warning(f"🔄 Funcionalidade de restaurar snapshot '{version}' não implementada")
        
        elif action == 'delete_snapshot' and version:
            if delete_snapshot(empreendimento, version):
                st.success(f"✅ Snapshot '{version}' deletado com sucesso!")
            else:
                st.error(f"❌ Erro ao deletar snapshot '{version}'")
            st.rerun()

# --- Visualização de Comparação de Período ---

def display_period_comparison(df_filtered, empreendimento_snapshots):
    st.subheader(f"⏳ Comparação de Período - {df_filtered['Empreendimento'].iloc[0]}")
    
    version_options = ["P0 (Planejamento Original)"]
    version_options.extend(sorted(empreendimento_snapshots.keys()))
    
    if not version_options or len(version_options) < 2:
        st.warning("É necessário ter pelo menos duas versões para comparação")
        return
    
    col1, col2 = st.columns(2)
    with col1:
        version_a = st.selectbox("Linha de Base A", version_options, index=0, key="version_a")
    with col2:
        default_index_b = 1 if len(version_options) > 1 else 0
        version_b = st.selectbox("Linha de Base B", version_options, index=default_index_b, key="version_b")
        
    if version_a == version_b:
        st.warning("Selecione duas linhas de base diferentes")
        return

    def load_version_data(version_name):
        if version_name == "P0 (Planejamento Original)":
            df_version = df_filtered[['ID_Tarefa', 'P0_Previsto_Inicio', 'P0_Previsto_Fim']].copy()
            df_version = df_version.rename(columns={'P0_Previsto_Inicio': 'Inicio', 'P0_Previsto_Fim': 'Fim'})
        else:
            version_data_list = empreendimento_snapshots[version_name]['data']
            df_version = pd.DataFrame(version_data_list)
            version_prefix = version_name.split('-')[0]
            col_inicio = f'{version_prefix}_Previsto_Inicio'
            col_fim = f'{version_prefix}_Previsto_Fim'
            df_version = df_version.rename(columns={col_inicio: 'Inicio', col_fim: 'Fim'})
            
        df_version['Inicio'] = pd.to_datetime(df_version['Inicio'])
        df_version['Fim'] = pd.to_datetime(df_version['Fim'])
        return df_version[['ID_Tarefa', 'Inicio', 'Fim']]

    df_a = load_version_data(version_a)
    df_b = load_version_data(version_b)
    df_merged = df_a.merge(df_b, on='ID_Tarefa', suffixes=('_A', '_B'))
    
    df_merged['Duracao_A'] = (df_merged['Fim_A'] - df_merged['Inicio_A']).dt.days
    df_merged['Duracao_B'] = (df_merged['Fim_B'] - df_merged['Inicio_B']).dt.days
    df_merged['Diferenca_Duracao'] = df_merged['Duracao_B'] - df_merged['Duracao_A']
    df_merged['Desvio_Inicio'] = (df_merged['Inicio_B'] - df_merged['Inicio_A']).dt.days
    df_merged['Desvio_Fim'] = (df_merged['Fim_B'] - df_merged['Fim_A']).dt.days
    
    df_context = df_filtered[['ID_Tarefa', 'Tarefa']].drop_duplicates()
    df_final = df_context.merge(df_merged, on='ID_Tarefa')
    
    st.dataframe(df_final, use_container_width=True)

# --- Aplicação Principal ---

def main():
    st.set_page_config(layout="wide", page_title="Gantt Chart Baseline")
    st.title("📊 Gráfico de Gantt com Versionamento")
    
    # Configura aviso antes de fechar
    setup_before_unload()
    
    # Inicialização
    create_snapshots_table()
    
    # Carrega dados locais ao iniciar
    if 'local_data_loaded' not in st.session_state:
        get_local_data()
        st.session_state.local_data_loaded = True
    
    # Processa ações do menu primeiro
    process_snapshot_actions()
    
    # Dados
    if 'df' not in st.session_state:
        st.session_state.df = create_mock_dataframe()
    
    df = st.session_state.df
    snapshots = load_snapshots()
    
    # Sidebar
    empreendimentos = df['Empreendimento'].unique().tolist()
    selected_empreendimento = st.sidebar.selectbox("🏢 Empreendimento", empreendimentos)
    df_filtered = df[df['Empreendimento'] == selected_empreendimento].copy()
    
    # Informação do modo de operação
    if not DB_AVAILABLE:
        st.sidebar.info("🔶 Modo Local Ativo")
    
    # Botões de ação na sidebar - DADOS LOCAIS
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 💾 Dados Locais")
    
    # Indicador de mudanças não salvas
    if st.session_state.unsaved_changes:
        st.sidebar.warning("⚠️ Você tem dados não salvos!")
    
    col1, col2 = st.sidebar.columns(2)
    
    with col1:
        if st.button("📥 Carregar Locais", use_container_width=True, help="Carrega dados salvos localmente"):
            get_local_data()
            st.rerun()
    
    with col2:
        if st.button("🗑️ Limpar Locais", use_container_width=True, help="Remove todos os dados locais"):
            clear_local_data()
            st.session_state.unsaved_changes = False
            st.session_state.local_data = {}
            st.success("Dados locais limpos!")
            st.rerun()
    
    # Botão para enviar para AWS (só mostra se DB estiver disponível)
    if DB_AVAILABLE:
        if st.sidebar.button("🚀 Enviar para AWS", type="primary", use_container_width=True, 
                            disabled=not st.session_state.unsaved_changes):
            with st.spinner("Enviando dados para AWS..."):
                saved_count, error_count = save_local_to_aws()
                
                if error_count == 0:
                    if saved_count > 0:
                        st.success(f"✅ {saved_count} snapshot(s) salvos na AWS!")
                    else:
                        st.info("ℹ️ Nenhum dado novo para salvar na AWS.")
                else:
                    st.error(f"❌ Erro ao salvar {error_count} snapshot(s) na AWS.")
            
            st.rerun()
    else:
        st.sidebar.info("🌐 AWS não disponível")
    
    # Botões de ação rápidos
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📸 Ações Rápidas")
    
    if st.sidebar.button("📸 Criar Snapshot Local", use_container_width=True):
        try:
            version_name, saved_locally = take_snapshot(df, selected_empreendimento, save_locally=True)
            if saved_locally:
                st.success(f"✅ {version_name} salvo localmente!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Erro: {e}")
    
    if st.sidebar.button("📸 Criar Snapshot Direto", use_container_width=True):
        try:
            version_name, success = take_snapshot(df, selected_empreendimento, save_locally=False)
            if success:
                st.success(f"✅ {version_name} salvo com sucesso!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Erro: {e}")
    
    if st.sidebar.button("⏳ Comparar Períodos", use_container_width=True):
        st.session_state.show_comparison = not st.session_state.get('show_comparison', False)
        st.rerun()
    
    # Visualização principal
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Dados do Projeto")
        st.dataframe(df_filtered, use_container_width=True)
    
    with col2:
        # Snapshots salvos
        st.subheader("📁 Snapshots Salvos")
        empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
        
        if empreendimento_snapshots:
            st.write("**☁️ Na AWS:**" if DB_AVAILABLE else "**💾 Locais:**")
            for version in sorted(empreendimento_snapshots.keys()):
                st.write(f"• {version}")
        else:
            st.info("Nenhum snapshot salvo")
        
        # Snapshots locais
        st.subheader("💾 Snapshots Locais")
        local_snapshots = {}
        for key, data in st.session_state.get('local_data', {}).items():
            if data.get('empreendimento') == selected_empreendimento:
                local_snapshots[data['version_name']] = data
        
        if local_snapshots:
            for version in sorted(local_snapshots.keys()):
                status = "✅" if local_snapshots[version].get('saved_to_aws') else "⏳"
                st.write(f"• {version} {status}")
        else:
            st.info("Nenhum snapshot local")
    
    # Menu de contexto
    st.markdown("---")
    st.subheader("🎯 Menu de Contexto (Clique com Botão Direito)")
    
    # Prepara dados para o menu de contexto
    empreendimento_snapshots_menu = snapshots.get(selected_empreendimento, {})
    local_snapshots_menu = {}
    for key, data in st.session_state.get('local_data', {}).items():
        if data.get('empreendimento') == selected_empreendimento:
            local_snapshots_menu[data['version_name']] = data
    
    context_menu_html = create_context_menu(selected_empreendimento, empreendimento_snapshots_menu, local_snapshots_menu)
    html(context_menu_html, height=350)
    
    # Comparação de períodos
    if st.session_state.get('show_comparison', False):
        st.markdown("---")
        empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
        if empreendimento_snapshots:
            display_period_comparison(df_filtered, empreendimento_snapshots)
        else:
            st.warning("Não há snapshots salvos para comparação")
    
    # Gerenciamento de snapshots na sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔧 Gerenciar Snapshots")
    
    empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
    if empreendimento_snapshots:
        for version_name in sorted(empreendimento_snapshots.keys()):
            col1, col2 = st.sidebar.columns([3, 1])
            with col1:
                st.write(f"`{version_name}`")
            with col2:
                if st.button("🗑️", key=f"del_{version_name}"):
                    if delete_snapshot(selected_empreendimento, version_name):
                        st.success(f"✅ {version_name} deletado!")
                        st.rerun()

if __name__ == "__main__":
    main()
