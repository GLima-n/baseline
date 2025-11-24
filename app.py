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
except Exception:
    DB_CONFIG = {
        'host': "mock_host",
        'user': "mock_user",
        'password': "mock_password",
        'database': "mock_db",
        'port': 3306
    }

# --- Funções de Banco de Dados ---

def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        return None

def create_baselines_table():
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            create_table_query = """
            CREATE TABLE IF NOT EXISTS baselines (
                id INT AUTO_INCREMENT PRIMARY KEY,
                empreendimento VARCHAR(255) NOT NULL,
                version_name VARCHAR(255) NOT NULL,
                baseline_data JSON NOT NULL,
                created_date VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_baseline (empreendimento, version_name)
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
    else:
        if 'mock_baselines' not in st.session_state:
            st.session_state.mock_baselines = {}

def load_baselines():
    conn = get_db_connection()
    if conn:
        baselines = {}
        try:
            cursor = conn.cursor(dictionary=True)
            query = "SELECT empreendimento, version_name, baseline_data, created_date FROM baselines ORDER BY created_at DESC"
            cursor.execute(query)
            results = cursor.fetchall()
            for row in results:
                empreendimento = row['empreendimento']
                version_name = row['version_name']
                if empreendimento not in baselines:
                    baselines[empreendimento] = {}
                baseline_data = json.loads(row['baseline_data'])
                baselines[empreendimento][version_name] = {
                    "date": row['created_date'],
                    "data": baseline_data
                }
            return baselines
        except Error as e:
            st.error(f"Erro ao carregar linhas de base: {e}")
            return {}
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        return st.session_state.mock_baselines

def save_baseline(empreendimento, version_name, baseline_data, created_date):
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            baseline_json = json.dumps(baseline_data)
            insert_query = """
            INSERT INTO baselines (empreendimento, version_name, baseline_data, created_date)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE baseline_data = VALUES(baseline_data), created_date = VALUES(created_date)
            """
            cursor.execute(insert_query, (empreendimento, version_name, baseline_json, created_date))
            conn.commit()
            return True
        except Error as e:
            st.error(f"Erro ao salvar linha de base: {e}")
            return False
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        if empreendimento not in st.session_state.mock_baselines:
            st.session_state.mock_baselines[empreendimento] = {}
        st.session_state.mock_baselines[empreendimento][version_name] = {
            "date": created_date,
            "data": baseline_data
        }
        return True

def delete_baseline(empreendimento, version_name):
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            delete_query = "DELETE FROM baselines WHERE empreendimento = %s AND version_name = %s"
            cursor.execute(delete_query, (empreendimento, version_name))
            conn.commit()
            return cursor.rowcount > 0
        except Error as e:
            st.error(f"Erro ao deletar linha de base: {e}")
            return False
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        if empreendimento in st.session_state.mock_baselines and version_name in st.session_state.mock_baselines[empreendimento]:
            del st.session_state.mock_baselines[empreendimento][version_name]
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

# --- Lógica de Linha de Base ---

def take_baseline(df, empreendimento):
    df_empreendimento = df[df['Empreendimento'] == empreendimento].copy()
    
    existing_baselines = load_baselines()
    empreendimento_baselines = existing_baselines.get(empreendimento, {})
    existing_versions = [k for k in empreendimento_baselines.keys() if k.startswith('P') and k.split('-')[0][1:].isdigit()]
    
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
    
    df_baseline = df_empreendimento[['ID_Tarefa', 'Real_Inicio', 'Real_Fim']].copy()
    df_baseline['Real_Inicio'] = df_baseline['Real_Inicio'].dt.strftime('%Y-%m-%d')
    df_baseline['Real_Fim'] = df_baseline['Real_Fim'].dt.strftime('%Y-%m-%d')
    
    baseline_data = df_baseline.rename(
        columns={'Real_Inicio': f'{version_prefix}_Previsto_Inicio', 'Real_Fim': f'{version_prefix}_Previsto_Fim'}
    ).to_dict('records')

    success = save_baseline(empreendimento, version_name, baseline_data, current_date_str)
    
    if success:
        # Marcar linha de base como não enviada para AWS
        if 'unsent_baselines' not in st.session_state:
            st.session_state.unsent_baselines = {}
        
        if empreendimento not in st.session_state.unsent_baselines:
            st.session_state.unsent_baselines[empreendimento] = []
        
        if version_name not in st.session_state.unsent_baselines[empreendimento]:
            st.session_state.unsent_baselines[empreendimento].append(version_name)
        
        return version_name
    else:
        raise Exception("Falha ao salvar linha de base no banco de dados")

# --- Função para enviar dados para AWS ---

def send_to_aws(empreendimento, version_name):
    """Simula o envio de dados para AWS"""
    try:
        # Simular processamento
        import time
        time.sleep(1)  # Simular delay de rede
        
        # Remover da lista de não enviados
        if ('unsent_baselines' in st.session_state and 
            empreendimento in st.session_state.unsent_baselines and 
            version_name in st.session_state.unsent_baselines[empreendimento]):
            
            st.session_state.unsent_baselines[empreendimento].remove(version_name)
            
            # Se não há mais linhas de base não enviadas para este empreendimento, remover a entrada
            if not st.session_state.unsent_baselines[empreendimento]:
                del st.session_state.unsent_baselines[empreendimento]
        
        return True
    except Exception as e:
        st.error(f"Erro ao enviar para AWS: {e}")
        return False

# --- Processar ações do menu de contexto ---

def process_context_menu_actions():
    """Processa ações do menu de contexto via query parameters"""
    query_params = st.query_params
    
    if 'context_action' in query_params and 'empreendimento' in query_params:
        action = query_params['context_action']
        empreendimento = query_params['empreendimento']
        
        # Limpar os parâmetros para evitar execução múltipla
        st.query_params.clear()
        
        if action == 'take_baseline':
            try:
                version_name = take_baseline(st.session_state.df, empreendimento)
                # Usar session_state para mostrar mensagem sem recarregar a página
                st.session_state.context_menu_success = f"✅ {version_name} criado via menu de contexto!"
                st.session_state.show_context_success = True
                st.session_state.context_menu_trigger = True
            except Exception as e:
                st.session_state.context_menu_error = f"❌ Erro ao criar linha de base: {e}"
                st.session_state.show_context_error = True

# --- Menu de Contexto SEM RECARREGAMENTO VISÍVEL ---

def create_context_menu_component(selected_empreendimento):
    """Cria o componente do menu de contexto sem recarregamento visível"""
    
    # Mostrar mensagens de sucesso/erro do menu de contexto
    if st.session_state.get('show_context_success'):
        # Usar um container vazio para a mensagem (não recarrega a página inteira)
        success_container = st.empty()
        success_container.success(st.session_state.context_menu_success)
        st.session_state.show_context_success = False
        
        # Remover a mensagem após 3 segundos
        import time
        time.sleep(3)
        success_container.empty()
    
    if st.session_state.get('show_context_error'):
        error_container = st.empty()
        error_container.error(st.session_state.context_menu_error)
        st.session_state.show_context_error = False
        
        import time
        time.sleep(3)
        error_container.empty()
    
    # HTML completo com CSS e JavaScript para o menu visual
    context_menu_html = f"""
    <style>
    #context-menu {{
        position: fixed;
        background: white;
        border: 1px solid #ccc;
        border-radius: 5px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.2);
        z-index: 10000;
        display: none;
        font-family: Arial, sans-serif;
    }}
    .context-menu-item {{
        padding: 12px 20px;
        cursor: pointer;
        border-bottom: 1px solid #eee;
        font-size: 14px;
        transition: background-color 0.2s;
    }}
    .context-menu-item:hover {{
        background: #f0f0f0;
    }}
    .context-menu-item:last-child {{
        border-bottom: none;
    }}
    #gantt-area {{
        height: 300px;
        border: 2px dashed #ccc;
        display: flex;
        align-items: center;
        justify-content: center;
        background-color: #f9f9f9;
        cursor: pointer;
        margin: 20px 0;
        user-select: none;
    }}
    #baseline-status {{
        margin-top: 10px;
        padding: 10px;
        border-radius: 5px;
        text-align: center;
        font-weight: bold;
        display: none;
    }}
    .status-creating {{
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        color: #856404;
    }}
    .status-success {{
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        color: #0c5460;
    }}
    .status-error {{
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
    }}
    #hidden-iframe {{
        position: absolute;
        width: 1px;
        height: 1px;
        border: none;
        opacity: 0;
        pointer-events: none;
    }}
    .loading-overlay {{
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(255, 255, 255, 0.8);
        display: none;
        justify-content: center;
        align-items: center;
        z-index: 10001;
        font-family: Arial, sans-serif;
    }}
    .loading-spinner {{
        background: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        text-align: center;
    }}
    </style>

    <div id="gantt-area">
        <div style="text-align: center;">
            <h3>Área do Gráfico de Gantt</h3>
            <p>Clique com o botão direito para abrir o menu de linha de base</p>
        </div>
    </div>

    <div id="baseline-status"></div>

    <!-- Overlay de loading -->
    <div id="loading-overlay" class="loading-overlay">
        <div class="loading-spinner">
            <h3>🔄 Criando Linha de Base</h3>
            <p>Por favor, aguarde...</p>
        </div>
    </div>

    <!-- Iframe invisível para carregamentos -->
    <iframe id="hidden-iframe" name="hidden-iframe"></iframe>

    <div id="context-menu">
        <div class="context-menu-item" id="take-baseline">📸 Criar Linha de Base</div>
        <div class="context-menu-item" id="restore-baseline">🔄 Restaurar Linha de Base</div>
        <div class="context-menu-item" id="delete-baseline">🗑️ Deletar Linha de Base</div>
    </div>

    <script>
    // Elementos
    const ganttArea = document.getElementById('gantt-area');
    const contextMenu = document.getElementById('context-menu');
    const statusDiv = document.getElementById('baseline-status');
    const takeBaselineBtn = document.getElementById('take-baseline');
    const loadingOverlay = document.getElementById('loading-overlay');
    const hiddenIframe = document.getElementById('hidden-iframe');
    
    // Função para mostrar o menu
    function showContextMenu(x, y) {{
        contextMenu.style.left = x + 'px';
        contextMenu.style.top = y + 'px';
        contextMenu.style.display = 'block';
    }}
    
    // Função para esconder o menu
    function hideContextMenu() {{
        contextMenu.style.display = 'none';
    }}
    
    // Função para mostrar/ocultar loading
    function showLoading() {{
        loadingOverlay.style.display = 'flex';
    }}
    
    function hideLoading() {{
        loadingOverlay.style.display = 'none';
    }}
    
    // Função para mostrar status
    function showStatus(message, type) {{
        statusDiv.textContent = message;
        statusDiv.className = '';
        statusDiv.classList.add(type);
        statusDiv.style.display = 'block';
        
        // Auto-esconder após 3 segundos
        setTimeout(() => {{
            statusDiv.style.display = 'none';
        }}, 3000);
    }}
    
    // Função para criar linha de base via iframe invisível
    function executeTakeBaseline() {{
        showStatus('🔄 Criando linha de base...', 'status-creating');
        showLoading();
        
        // Criar URL com parâmetros para o Streamlit processar
        const timestamp = new Date().getTime();
        const url = `?context_action=take_baseline&empreendimento={selected_empreendimento}&t=${{timestamp}}`;
        
        // Usar iframe invisível para carregar a URL
        hiddenIframe.src = url;
        
        // Quando o iframe terminar de carregar
        hiddenIframe.onload = function() {{
            hideLoading();
            showStatus('✅ Linha de base criada! Verifique a barra lateral para enviar para AWS.', 'status-success');
            
            // Forçar uma atualização suave da sidebar após 1 segundo
            setTimeout(() => {{
                // Disparar um evento customizado para atualizar a interface
                const event = new Event('baselineCreated');
                document.dispatchEvent(event);
            }}, 1000);
        }};
        
        hideContextMenu();
    }}
    
    // Event Listeners
    if (ganttArea) {{
        ganttArea.addEventListener('contextmenu', function(e) {{
            e.preventDefault();
            e.stopPropagation();
            showContextMenu(e.pageX, e.pageY);
        }});
    }}
    
    // Event listener para o botão de criar linha de base
    if (takeBaselineBtn) {{
        takeBaselineBtn.addEventListener('click', function() {{
            executeTakeBaseline();
        }});
    }}
    
    // Event listeners para outros botões (placeholder)
    const restoreBaselineBtn = document.getElementById('restore-baseline');
    const deleteBaselineBtn = document.getElementById('delete-baseline');
    
    if (restoreBaselineBtn) {{
        restoreBaselineBtn.addEventListener('click', function() {{
            showStatus('🔄 Funcionalidade em desenvolvimento...', 'status-creating');
            hideContextMenu();
        }});
    }}
    
    if (deleteBaselineBtn) {{
        deleteBaselineBtn.addEventListener('click', function() {{
            showStatus('🗑️ Funcionalidade em desenvolvimento...', 'status-creating');
            hideContextMenu();
        }});
    }}
    
    // Fechar menu ao clicar fora
    document.addEventListener('click', function(e) {{
        if (contextMenu && !contextMenu.contains(e.target) && e.target !== ganttArea) {{
            hideContextMenu();
        }}
    }});
    
    // Fechar menu com ESC
    document.addEventListener('keydown', function(e) {{
        if (e.key === 'Escape') {{
            hideContextMenu();
        }}
    }});
    
    // Prevenir menu de contexto padrão na área do Gantt
    document.addEventListener('contextmenu', function(e) {{
        if (e.target.id === 'gantt-area' || e.target.closest('#gantt-area')) {{
            e.preventDefault();
        }}
    }}, true);
    
    // Atualizar interface quando linha de base for criada
    document.addEventListener('baselineCreated', function() {{
        console.log('Linha de base criada - interface pode ser atualizada');
        // Aqui você pode adicionar lógica para atualizar elementos específicos
    }});
    </script>
    """
    
    # Usar html() para injetar o componente completo
    html(context_menu_html, height=400)

# --- Visualização de Comparação de Período ---

def display_period_comparison(df_filtered, empreendimento_baselines):
    st.subheader(f"⏳ Comparação de Período - {df_filtered['Empreendimento'].iloc[0]}")
    
    version_options = ["P0 (Planejamento Original)"]
    version_options.extend(sorted(empreendimento_baselines.keys()))
    
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
            version_data_list = empreendimento_baselines[version_name]['data']
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
    
    # Inicialização do session_state
    if 'df' not in st.session_state:
        st.session_state.df = create_mock_dataframe()
    if 'unsent_baselines' not in st.session_state:
        st.session_state.unsent_baselines = {}
    if 'show_comparison' not in st.session_state:
        st.session_state.show_comparison = False
    if 'show_context_success' not in st.session_state:
        st.session_state.show_context_success = False
    if 'show_context_error' not in st.session_state:
        st.session_state.show_context_error = False
    if 'context_menu_trigger' not in st.session_state:
        st.session_state.context_menu_trigger = False
    
    # Inicialização do banco
    create_baselines_table()
    
    # Processar ações do menu de contexto PRIMEIRO
    process_context_menu_actions()
    
    # Dados
    df = st.session_state.df
    baselines = load_baselines()
    
    # Sidebar
    with st.sidebar:
        empreendimentos = df['Empreendimento'].unique().tolist()
        selected_empreendimento = st.selectbox("🏢 Empreendimento", empreendimentos)
        
        df_filtered = df[df['Empreendimento'] == selected_empreendimento].copy()
        
        # Botões de ação na sidebar
        st.markdown("---")
        st.markdown("### 📸 Ações Rápidas")
        
        if st.button("📸 Criar Linha de Base", use_container_width=True, key="sidebar_baseline"):
            try:
                version_name = take_baseline(df, selected_empreendimento)
                st.success(f"✅ {version_name} criado!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro: {e}")
        
        if st.button("⏳ Comparar Períodos", use_container_width=True, key="sidebar_compare"):
            st.session_state.show_comparison = not st.session_state.show_comparison
            st.rerun()
        
        # Seção de envio para AWS
        st.markdown("---")
        st.markdown("### ☁️ Linhas de Base para Enviar")
        
        empreendimento_baselines = baselines.get(selected_empreendimento, {})
        unsent_baselines = st.session_state.unsent_baselines.get(selected_empreendimento, [])
        
        if unsent_baselines:
            st.info(f"📋 {len(unsent_baselines)} linha(s) de base aguardando envio para AWS")
            
            for version_name in unsent_baselines:
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.write(f"`{version_name}`")
                with col2:
                    if st.button("☁️", key=f"aws_{version_name}"):
                        if send_to_aws(selected_empreendimento, version_name):
                            st.success(f"✅ {version_name} enviado para AWS!")
                            st.rerun()
                with col3:
                    if st.button("🗑️", key=f"del_{version_name}"):
                        if delete_baseline(selected_empreendimento, version_name):
                            # Remover da lista de não enviados também
                            if version_name in st.session_state.unsent_baselines.get(selected_empreendimento, []):
                                st.session_state.unsent_baselines[selected_empreendimento].remove(version_name)
                            st.success(f"✅ {version_name} deletado!")
                            st.rerun()
        else:
            st.info("📭 Nenhuma linha de base aguardando envio")
        
        # Gerenciamento de todas as linhas de base
        st.markdown("---")
        st.markdown("### 💾 Todas as Linhas de Base")
        
        if empreendimento_baselines:
            for version_name in sorted(empreendimento_baselines.keys()):
                is_unsent = version_name in unsent_baselines
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    if is_unsent:
                        st.write(f"`{version_name}` ⏳")
                    else:
                        st.write(f"`{version_name}` ✅")
                with col2:
                    if st.button("🗑️", key=f"del_all_{version_name}"):
                        if delete_baseline(selected_empreendimento, version_name):
                            # Remover da lista de não enviados também
                            if version_name in st.session_state.unsent_baselines.get(selected_empreendimento, []):
                                st.session_state.unsent_baselines[selected_empreendimento].remove(version_name)
                            st.success(f"✅ {version_name} deletado!")
                            st.rerun()
        else:
            st.info("Nenhuma linha de base criada")
    
    # Visualização principal
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Dados do Projeto")
        st.dataframe(df_filtered, use_container_width=True)
    
    with col2:
        st.subheader("Linhas de Base")
        empreendimento_baselines = baselines.get(selected_empreendimento, {})
        unsent_baselines = st.session_state.unsent_baselines.get(selected_empreendimento, [])
        
        if empreendimento_baselines:
            for version in sorted(empreendimento_baselines.keys()):
                if version in unsent_baselines:
                    st.write(f"• {version} ⏳")
                else:
                    st.write(f"• {version} ✅")
        else:
            st.info("Nenhuma linha de base")
    
    # Menu de contexto
    st.markdown("---")
    st.subheader("Menu de Contexto (Clique com Botão Direito)")
    
    # Criar o componente do menu de contexto
    create_context_menu_component(selected_empreendimento)
    
    # Comparação de períodos
    if st.session_state.show_comparison:
        st.markdown("---")
        display_period_comparison(df_filtered, empreendimento_baselines)
    
    # Status de linhas de base não enviadas
    total_unsent = sum(len(baselines) for baselines in st.session_state.unsent_baselines.values())
    if total_unsent > 0:
        st.warning(f"⚠️ Você tem {total_unsent} linha(s) de base não enviadas para AWS. Envie-as pela barra lateral.")

if __name__ == "__main__":
    main()
