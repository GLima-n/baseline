import streamlit as st
import pandas as pd
import json
from datetime import datetime
import mysql.connector
from mysql.connector import Error
import urllib.parse
from streamlit.components.v1 import html
import time

# --- Configurações do Banco AWS ---
try:
    DB_CONFIG = {
        'host': st.secrets["aws_db"]["host"],
        'user': st.secrets["aws_db"]["user"],
        'password': st.secrets["aws_db"]["password"],
        'database': st.secrets["aws_db"]["database"],
        'port': 3306
    }
    st.success("✅ Configurações AWS carregadas com sucesso!")
except Exception as e:
    st.error(f"❌ Erro ao carregar configurações AWS: {e}")
    DB_CONFIG = {
        'host': "mock_host",
        'user': "mock_user", 
        'password': "mock_password",
        'database': "mock_db",
        'port': 3306
    }
    st.info("🔶 Modo offline ativado - usando armazenamento local")

# --- Funções de Banco de Dados ---

def get_db_connection():
    """Tenta estabelecer conexão com o banco de dados."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        if conn.is_connected():
            return conn
        else:
            return None
    except Error as e:
        st.error(f"❌ Erro de conexão com AWS: {e}")
        return None
    except Exception as e:
        st.error(f"❌ Erro inesperado: {e}")
        return None

def test_connection():
    """Testa a conexão e retorna status."""
    conn = get_db_connection()
    if conn:
        conn.close()
        return True
    return False

def create_snapshots_table():
    """Cria a tabela de snapshots se não existir."""
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
            st.success("✅ Tabela de snapshots verificada/criada!")
        except Error as e:
            st.error(f"❌ Erro ao criar tabela: {e}")
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        # Modo offline - usar session_state
        if 'mock_snapshots' not in st.session_state:
            st.session_state.mock_snapshots = {}
        st.info("🔶 Modo offline - usando armazenamento local")

def load_snapshots():
    """Carrega snapshots do banco ou do armazenamento local."""
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
                
                try:
                    snapshot_data = json.loads(row['snapshot_data'])
                    snapshots[empreendimento][version_name] = {
                        "date": row['created_date'],
                        "data": snapshot_data
                    }
                except json.JSONDecodeError:
                    st.error(f"❌ Erro ao decodificar JSON do snapshot {version_name}")
                    continue
                    
            return snapshots
            
        except Error as e:
            st.error(f"❌ Erro ao carregar snapshots: {e}")
            return {}
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        # Modo offline
        return st.session_state.get('mock_snapshots', {})

def save_snapshot(empreendimento, version_name, snapshot_data, created_date):
    """Salva snapshot no banco ou localmente."""
    conn = get_db_connection()
    
    if conn:
        try:
            cursor = conn.cursor()
            snapshot_json = json.dumps(snapshot_data, ensure_ascii=False)
            
            insert_query = """
            INSERT INTO snapshots (empreendimento, version_name, snapshot_data, created_date)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                snapshot_data = VALUES(snapshot_data), 
                created_date = VALUES(created_date)
            """
            
            cursor.execute(insert_query, (empreendimento, version_name, snapshot_json, created_date))
            conn.commit()
            
            if cursor.rowcount > 0:
                return True
            else:
                return False
                
        except Error as e:
            st.error(f"❌ Erro ao salvar snapshot na AWS: {e}")
            return False
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        # Modo offline - salvar localmente
        if 'mock_snapshots' not in st.session_state:
            st.session_state.mock_snapshots = {}
        
        if empreendimento not in st.session_state.mock_snapshots:
            st.session_state.mock_snapshots[empreendimento] = {}
            
        st.session_state.mock_snapshots[empreendimento][version_name] = {
            "date": created_date,
            "data": snapshot_data
        }
        
        return True

def delete_snapshot(empreendimento, version_name):
    """Deleta snapshot do banco ou localmente."""
    conn = get_db_connection()
    
    if conn:
        try:
            cursor = conn.cursor()
            delete_query = "DELETE FROM snapshots WHERE empreendimento = %s AND version_name = %s"
            cursor.execute(delete_query, (empreendimento, version_name))
            conn.commit()
            
            if cursor.rowcount > 0:
                return True
            else:
                return False
                
        except Error as e:
            st.error(f"❌ Erro ao deletar snapshot da AWS: {e}")
            return False
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        # Modo offline - deletar localmente
        if (empreendimento in st.session_state.get('mock_snapshots', {}) and 
            version_name in st.session_state.mock_snapshots[empreendimento]):
            
            del st.session_state.mock_snapshots[empreendimento][version_name]
            return True
            
        return False

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

def take_snapshot(df, empreendimento):
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
    
    # Prepara dados do snapshot
    df_snapshot = df_empreendimento[['ID_Tarefa', 'Real_Inicio', 'Real_Fim']].copy()
    df_snapshot['Real_Inicio'] = df_snapshot['Real_Inicio'].dt.strftime('%Y-%m-%d')
    df_snapshot['Real_Fim'] = df_snapshot['Real_Fim'].dt.strftime('%Y-%m-%d')
    
    snapshot_data = df_snapshot.rename(
        columns={'Real_Inicio': f'{version_prefix}_Previsto_Inicio', 'Real_Fim': f'{version_prefix}_Previsto_Fim'}
    ).to_dict('records')

    success = save_snapshot(empreendimento, version_name, snapshot_data, current_date_str)
    
    if success:
        return version_name
    else:
        raise Exception("Falha ao salvar snapshot")

# --- Solução Simplificada para Menu de Contexto ---

def create_simple_context_menu(selected_empreendimento):
    """Cria um menu de contexto simples usando apenas HTML/JS básico"""
    
    # Verifica se há uma ação pendente para mostrar feedback
    feedback_html = ""
    if st.session_state.get('snapshot_feedback'):
        feedback_type, feedback_message = st.session_state.snapshot_feedback
        color = "green" if feedback_type == "success" else "red"
        feedback_html = f"""
        <div style="padding: 10px; background-color: {color}20; border: 1px solid {color}; border-radius: 5px; margin: 10px 0;">
            <strong>{'✅' if feedback_type == 'success' else '❌'} {feedback_message}</strong>
        </div>
        """
        # Limpa o feedback após exibir
        del st.session_state.snapshot_feedback
    
    html_code = f"""
<div id="gantt-area" style="height: 300px; border: 2px dashed #ccc; display: flex; align-items: center; justify-content: center; background-color: #f9f9f9; cursor: pointer; margin: 20px 0;">
    <div style="text-align: center;">
        <h3>Área do Gráfico de Gantt</h3>
        <p>Clique com o botão direito para abrir o menu de snapshot</p>
    </div>
</div>

{feedback_html}

<style>
.context-menu {{
    position: fixed;
    background: white;
    border: 1px solid #ccc;
    border-radius: 5px;
    box-shadow: 2px 2px 10px rgba(0,0,0,0.2);
    z-index: 1000;
    display: none;
}}
.context-menu-item {{
    padding: 10px 15px;
    cursor: pointer;
    border-bottom: 1px solid #eee;
}}
.context-menu-item:hover {{
    background: #f0f0f0;
}}
.context-menu-item:last-child {{
    border-bottom: none;
}}
</style>

<script>
// Cria o menu de contexto
const menu = document.createElement('div');
menu.className = 'context-menu';
menu.innerHTML = `
    <div class="context-menu-item" onclick="takeSnapshot()">📸 Tirar Snapshot</div>
    <div class="context-menu-item" onclick="restoreSnapshot()">🔄 Restaurar Snapshot</div>
    <div class="context-menu-item" onclick="deleteSnapshot()">🗑️ Deletar Snapshot</div>
`;
document.body.appendChild(menu);

// Funções do menu
function takeSnapshot() {{
    hideMenu();
    // Usa uma abordagem diferente para evitar recarregar a página
    const timestamp = new Date().getTime();
    const event = new CustomEvent('snapshotAction', {{
        detail: {{
            action: 'take_snapshot',
            empreendimento: '{selected_empreendimento}',
            timestamp: timestamp
        }}
    }});
    window.dispatchEvent(event);
}}

function restoreSnapshot() {{
    hideMenu();
    const timestamp = new Date().getTime();
    const event = new CustomEvent('snapshotAction', {{
        detail: {{
            action: 'restore_snapshot', 
            empreendimento: '{selected_empreendimento}',
            timestamp: timestamp
        }}
    }});
    window.dispatchEvent(event);
}}

function deleteSnapshot() {{
    hideMenu();
    const timestamp = new Date().getTime();
    const event = new CustomEvent('snapshotAction', {{
        detail: {{
            action: 'delete_snapshot',
            empreendimento: '{selected_empreendimento}',
            timestamp: timestamp
        }}
    }});
    window.dispatchEvent(event);
}}

function showMenu(x, y) {{
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

// Listener para eventos customizados do snapshot
window.addEventListener('snapshotAction', function(e) {{
    const {{ action, empreendimento, timestamp }} = e.detail;
    
    // Envia a ação para o Streamlit via WebSocket
    if (window.StreamlitComponent) {{
        window.StreamlitComponent.setComponentValue({{
            action: action,
            empreendimento: empreendimento,
            timestamp: timestamp
        }});
    }}
}});
</script>
"""
    return html_code

# --- Função para processar ações do menu ---

def process_snapshot_actions():
    """Processa ações do menu de contexto via eventos customizados"""
    # Verifica se há uma ação pendente no session_state
    if 'pending_snapshot_action' in st.session_state:
        action_data = st.session_state.pending_snapshot_action
        action = action_data['action']
        empreendimento = action_data['empreendimento']
        
        # Limpa a ação pendente
        del st.session_state.pending_snapshot_action
        
        df = st.session_state.df
        
        if action == 'take_snapshot':
            try:
                version_name = take_snapshot(df, empreendimento)
                st.session_state.snapshot_feedback = ("success", f"Snapshot '{version_name}' criado com sucesso!")
                # Força atualização apenas do componente
                st.rerun()
            except Exception as e:
                st.session_state.snapshot_feedback = ("error", f"Erro ao criar snapshot: {e}")
                st.rerun()
        elif action == 'restore_snapshot':
            st.session_state.snapshot_feedback = ("error", "Funcionalidade de restaurar snapshot não implementada")
            st.rerun()
        elif action == 'delete_snapshot':
            st.session_state.snapshot_feedback = ("error", "Funcionalidade de deletar snapshot não implementada via menu")

# --- Componente para capturar eventos JavaScript ---

def create_snapshot_event_handler():
    """Cria um componente para capturar eventos do JavaScript"""
    
    # Componente vazio que será controlado via JavaScript
    def snapshot_component():
        # Este componente não renderiza nada visualmente
        # mas permite comunicação entre JS e Python
        return
    
    # HTML com JavaScript para comunicação
    event_handler_html = """
<script>
// Função para enviar eventos do JavaScript para o Streamlit
function sendSnapshotAction(actionData) {
    if (window.Streamlit) {
        // Usando o método setComponentValue para comunicação
        window.Streamlit.setComponentValue(actionData);
    }
}

// Listener para eventos customizados
window.addEventListener('snapshotAction', function(e) {
    const { action, empreendimento, timestamp } = e.detail;
    sendSnapshotAction({
        action: action,
        empreendimento: empreendimento, 
        timestamp: timestamp
    });
});

// Também expõe uma função global para ser chamada diretamente
window.takeSnapshot = function(empreendimento) {
    sendSnapshotAction({
        action: 'take_snapshot',
        empreendimento: empreendimento,
        timestamp: new Date().getTime()
    });
}
</script>
"""
    
    # Cria um container vazio com o script
    html(event_handler_html)
    
    # Verifica se há valores do componente
    if 'component_value' in st.session_state:
        action_data = st.session_state.component_value
        st.session_state.pending_snapshot_action = action_data
        del st.session_state.component_value
        st.rerun()

# --- Visualização de Comparação de Período ---

def display_period_comparison(df_filtered, empreendimento_snapshots):
    st.subheader(f"⏳ Comparação de Período - {df_filtered['Empreendimento'].iloc[0]}")
    
    version_options = ["P0 (Planejamento Original)"]
    version_options.extend(sorted(empreendimento_snapshots.keys()))
    
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
    
    # Inicialização do estado
    if 'df' not in st.session_state:
        st.session_state.df = create_mock_dataframe()
    
    # Status da conexão
    st.sidebar.markdown("### 🔗 Status da Conexão")
    if test_connection():
        st.sidebar.success("✅ Conectado à AWS")
    else:
        st.sidebar.warning("🔶 Modo Offline - Armazenamento Local")
    
    # Inicialização do banco (apenas uma vez)
    if 'db_initialized' not in st.session_state:
        create_snapshots_table()
        st.session_state.db_initialized = True
    
    # Componente para capturar eventos
    create_snapshot_event_handler()
    
    # Processa ações do menu
    process_snapshot_actions()
    
    # Dados
    df = st.session_state.df
    snapshots = load_snapshots()
    
    # Sidebar
    empreendimentos = df['Empreendimento'].unique().tolist()
    selected_empreendimento = st.sidebar.selectbox("🏢 Empreendimento", empreendimentos)
    df_filtered = df[df['Empreendimento'] == selected_empreendimento].copy()
    
    # Botões de ação na sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📸 Ações Rápidas")
    
    if st.sidebar.button("📸 Criar Snapshot", use_container_width=True):
        try:
            version_name = take_snapshot(df, selected_empreendimento)
            st.success(f"✅ {version_name} criado!")
            # Atualiza apenas os snapshots
            st.session_state.last_snapshot_update = datetime.now()
        except Exception as e:
            st.error(f"❌ Erro: {e}")
    
    if st.sidebar.button("⏳ Comparar Períodos", use_container_width=True):
        st.session_state.show_comparison = not st.session_state.get('show_comparison', False)
    
    # Visualização principal
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Dados do Projeto")
        st.dataframe(df_filtered, use_container_width=True)
    
    with col2:
        st.subheader("Snapshots")
        empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
        if empreendimento_snapshots:
            for version in sorted(empreendimento_snapshots.keys()):
                st.write(f"• {version}")
        else:
            st.info("Nenhum snapshot")
    
    # Menu de contexto - esta é a área que será atualizada
    st.markdown("---")
    st.subheader("Menu de Contexto (Clique com Botão Direito)")
    
    # Container específico para o menu de contexto
    context_container = st.container()
    with context_container:
        context_menu_html = create_simple_context_menu(selected_empreendimento)
        html(context_menu_html, height=400)
    
    # Comparação de períodos
    if st.session_state.get('show_comparison', False):
        st.markdown("---")
        empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
        display_period_comparison(df_filtered, empreendimento_snapshots)
    
    # Gerenciamento de snapshots na sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 💾 Gerenciar Snapshots")
    
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
                        # Marca para atualizar apenas os snapshots
                        st.session_state.last_snapshot_update = datetime.now()

if __name__ == "__main__":
    main()
