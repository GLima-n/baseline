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

@st.cache_resource
def get_db_connection():
    """Tenta estabelecer e cachear a conexão com o banco de dados."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        if conn.is_connected():
            return conn
        else:
            return None
    except Error as e:
        return None
    except Exception as e:
        return None

def create_snapshots_table():
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
            if conn:
                st.error(f"Erro ao criar tabela: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
    else:
        if 'mock_snapshots' not in st.session_state:
            st.session_state.mock_snapshots = {}

@st.cache_data(ttl=3600)
def load_snapshots():
    """Carrega todos os snapshots do banco de dados ou mock."""
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
            if conn:
                st.error(f"Erro ao carregar snapshots: {e}")
            return {}
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
    else:
        return st.session_state.get('mock_snapshots', {})

def validate_snapshot_data(snapshot_data):
    """Valida a estrutura dos dados do snapshot."""
    required_fields = ['ID_Tarefa', 'P0_Previsto_Inicio', 'P0_Previsto_Fim', 'Real_Inicio', 'Real_Fim']
    
    if not isinstance(snapshot_data, list):
        return False
    
    for item in snapshot_data:
        if not all(field in item for field in required_fields):
            return False
    
    return True

def save_snapshot(empreendimento, version_name, snapshot_data, created_date):
    """Salva um snapshot no banco de dados ou mock."""
    if not validate_snapshot_data(snapshot_data):
        st.error("Dados do snapshot inválidos")
        return False
        
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
            load_snapshots.clear()
            return True
        except Error as e:
            st.error(f"Erro ao salvar snapshot: {e}")
            return False
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
    else:
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
    """Deleta um snapshot do banco de dados ou mock."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            delete_query = "DELETE FROM snapshots WHERE empreendimento = %s AND version_name = %s"
            cursor.execute(delete_query, (empreendimento, version_name))
            conn.commit()
            load_snapshots.clear()
            return cursor.rowcount > 0
        except Error as e:
            st.error(f"Erro ao deletar snapshot: {e}")
            return False
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
    else:
        if empreendimento in st.session_state.get('mock_snapshots', {}) and version_name in st.session_state.mock_snapshots[empreendimento]:
            del st.session_state.mock_snapshots[empreendimento][version_name]
            return True
        return False

# --- Funções para Gerenciar Dados Locais ---

def take_snapshot(df, empreendimento, save_locally=True):
    """Cria um snapshot dos dados filtrados e salva localmente ou na AWS."""
    df_filtered = df[df['Empreendimento'] == empreendimento].copy()
    
    snapshot_data = df_filtered[['ID_Tarefa', 'P0_Previsto_Inicio', 'P0_Previsto_Fim', 'Real_Inicio', 'Real_Fim']].to_dict('records')
    
    now = datetime.now()
    version_name = f"V{now.strftime('%Y%m%d%H%M%S')}"
    created_date = now.strftime("%d/%m/%Y")
    
    if save_locally:
        if 'local_data' not in st.session_state:
            st.session_state.local_data = {}
        
        st.session_state.local_data[version_name] = {
            'empreendimento': empreendimento,
            'version_name': version_name,
            'snapshot_data': snapshot_data,
            'created_date': created_date,
            'saved_to_aws': False
        }
        st.session_state.unsaved_changes = True
        return version_name, True
    else:
        success = save_snapshot(empreendimento, version_name, snapshot_data, created_date)
        return version_name, success

def save_local_to_aws():
    """Salva todos os snapshots locais não salvos na AWS."""
    saved_count = 0
    error_count = 0
    
    if 'local_data' not in st.session_state:
        return 0, 0
        
    keys_to_update = []
    
    for version_name, data in st.session_state.local_data.items():
        if not data.get('saved_to_aws'):
            success = save_snapshot(
                data['empreendimento'],
                data['version_name'],
                data['snapshot_data'],
                data['created_date']
            )
            
            if success:
                keys_to_update.append(version_name)
                saved_count += 1
            else:
                error_count += 1
                
    for version_name in keys_to_update:
        st.session_state.local_data[version_name]['saved_to_aws'] = True
        
    st.session_state.unsaved_changes = any(not data.get('saved_to_aws') for data in st.session_state.local_data.values())
    
    return saved_count, error_count

def clear_local_data():
    """Limpa todos os dados locais e reseta o estado de mudanças não salvas."""
    st.session_state.local_data = {}
    st.session_state.unsaved_changes = False

# --- Função para criar DataFrame de exemplo ---

def create_mock_dataframe():
    """Cria um DataFrame de exemplo com dados de projeto."""
    data = {
        'ID_Tarefa': [1, 2, 3, 4, 5, 6],
        'Empreendimento': ['Projeto A', 'Projeto A', 'Projeto B', 'Projeto B', 'Projeto A', 'Projeto B'],
        'Tarefa': ['Fase 1', 'Fase 2', 'Design', 'Implementação', 'Teste', 'Deploy'],
        'Real_Inicio': [pd.to_datetime('2025-10-01'), pd.to_datetime('2025-10-15'), pd.to_datetime('2025-11-01'), pd.to_datetime('2025-11-10'), pd.to_datetime('2025-10-26'), pd.to_datetime('2025-11-21')],
        'Real_Fim': [pd.to_datetime('2025-10-10'), pd.to_datetime('2025-10-25'), pd.to_datetime('2025-11-05'), pd.to_datetime('2025-11-20'), pd.to_datetime('2025-11-05'), pd.to_datetime('2025-11-25')],
        'P0_Previsto_Inicio': [pd.to_datetime('2025-10-01'), pd.to_datetime('2025-10-15'), pd.to_datetime('2025-11-01'), pd.to_datetime('2025-11-10'), pd.to_datetime('2025-10-26'), pd.to_datetime('2025-11-21')],
        'P0_Previsto_Fim': [pd.to_datetime('2025-10-10'), pd.to_datetime('2025-10-25'), pd.to_datetime('2025-11-05'), pd.to_datetime('2025-11-20'), pd.to_datetime('2025-11-05'), pd.to_datetime('2025-11-25')],
    }
    df = pd.DataFrame(data)
    return df

# --- Funções de Visualização ---

def display_period_comparison(df_filtered, empreendimento_snapshots):
    """Exibe a comparação entre dois snapshots de período."""
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
            df_version = df_version.rename(columns={'P0_Previsto_Inicio': 'Inicio', 'P0_Previsto_Fim': 'Fim'})
            
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

# --- Componente Customizado para Menu de Contexto (Simplificado) ---

def context_menu_component(empreendimento, snapshots_aws, snapshots_local):
    """
    Componente customizado para o menu de contexto.
    Versão simplificada que funciona melhor com Streamlit.
    """
    
    # Combina snapshots AWS e locais para o menu
    all_snapshots = {}
    for version, data in snapshots_aws.items():
        all_snapshots[version] = {'type': 'aws', 'date': data['date']}
    for version, data in snapshots_local.items():
        all_snapshots[version] = {'type': 'local', 'date': data['created_date']}
        
    snapshots_list = sorted(all_snapshots.keys())
    
    # HTML/JS para o menu de contexto - VERSÃO SIMPLIFICADA
    js_code = f"""
    <script>
    // Função para criar e mostrar o menu de contexto
    function showContextMenu(event) {{
        event.preventDefault();
        
        // Remove menu anterior se existir
        const oldMenu = document.getElementById('custom-context-menu');
        if (oldMenu) {{
            oldMenu.remove();
        }}
        
        // Cria novo menu
        const menu = document.createElement('div');
        menu.id = 'custom-context-menu';
        menu.style.position = 'fixed';
        menu.style.left = event.pageX + 'px';
        menu.style.top = event.pageY + 'px';
        menu.style.backgroundColor = 'white';
        menu.style.border = '1px solid #ccc';
        menu.style.boxShadow = '2px 2px 5px rgba(0,0,0,0.2)';
        menu.style.zIndex = '10000';
        menu.style.padding = '5px 0';
        menu.style.fontFamily = 'Arial, sans-serif';
        menu.style.fontSize = '14px';
        menu.style.minWidth = '200px';
        
        // Cria lista de opções
        const list = document.createElement('ul');
        list.style.listStyle = 'none';
        list.style.margin = '0';
        list.style.padding = '0';
        
        // Opção 1: Criar Snapshot Local
        const item1 = document.createElement('li');
        item1.textContent = '📸 Criar Snapshot Local';
        item1.style.padding = '8px 15px';
        item1.style.cursor = 'pointer';
        item1.onmouseover = () => item1.style.backgroundColor = '#f0f0f0';
        item1.onmouseout = () => item1.style.backgroundColor = 'transparent';
        item1.onclick = () => {{
            window.location.href = `?context_action=take_snapshot_local&empreendimento={empreendimento}&timestamp=${{Date.now()}}`;
        }};
        list.appendChild(item1);
        
        // Opção 2: Criar Snapshot AWS
        const item2 = document.createElement('li');
        item2.textContent = '🚀 Criar Snapshot AWS';
        item2.style.padding = '8px 15px';
        item2.style.cursor = 'pointer';
        item2.onmouseover = () => item2.style.backgroundColor = '#f0f0f0';
        item2.onmouseout = () => item2.style.backgroundColor = 'transparent';
        item2.onclick = () => {{
            window.location.href = `?context_action=take_snapshot_aws&empreendimento={empreendimento}&timestamp=${{Date.now()}}`;
        }};
        list.appendChild(item2);
        
        // Separador
        const separator = document.createElement('hr');
        separator.style.margin = '5px 0';
        separator.style.border = 'none';
        separator.style.borderTop = '1px solid #eee';
        list.appendChild(separator);
        
        // Snapshots disponíveis
        const snapshots = {json.dumps(all_snapshots)};
        const snapshotList = {json.dumps(snapshots_list)};
        
        if (snapshotList.length > 0) {{
            // Cabeçalho Restaurar
            const restoreHeader = document.createElement('li');
            restoreHeader.textContent = '🔄 Restaurar:';
            restoreHeader.style.padding = '5px 15px';
            restoreHeader.style.fontWeight = 'bold';
            restoreHeader.style.color = '#555';
            restoreHeader.style.cursor = 'default';
            list.appendChild(restoreHeader);
            
            // Opções de Restauração
            snapshotList.forEach(version => {{
                const item = document.createElement('li');
                item.textContent = `  - ${{version}} (${{snapshots[version].type.toUpperCase()}})`;
                item.style.padding = '8px 15px';
                item.style.cursor = 'pointer';
                item.onmouseover = () => item.style.backgroundColor = '#f0f0f0';
                item.onmouseout = () => item.style.backgroundColor = 'transparent';
                item.onclick = () => {{
                    window.location.href = `?context_action=restore_snapshot&empreendimento={empreendimento}&version=${{version}}&timestamp=${{Date.now()}}`;
                }};
                list.appendChild(item);
            }});
            
            // Separador
            const separator2 = document.createElement('hr');
            separator2.style.margin = '5px 0';
            separator2.style.border = 'none';
            separator2.style.borderTop = '1px solid #eee';
            list.appendChild(separator2);
            
            // Cabeçalho Deletar
            const deleteHeader = document.createElement('li');
            deleteHeader.textContent = '🗑️ Deletar:';
            deleteHeader.style.padding = '5px 15px';
            deleteHeader.style.fontWeight = 'bold';
            deleteHeader.style.color = '#555';
            deleteHeader.style.cursor = 'default';
            list.appendChild(deleteHeader);
            
            // Opções de Deleção
            snapshotList.forEach(version => {{
                const item = document.createElement('li');
                item.textContent = `  - ${{version}} (${{snapshots[version].type.toUpperCase()}})`;
                item.style.padding = '8px 15px';
                item.style.cursor = 'pointer';
                item.onmouseover = () => item.style.backgroundColor = '#f0f0f0';
                item.onmouseout = () => item.style.backgroundColor = 'transparent';
                item.onclick = () => {{
                    window.location.href = `?context_action=delete_snapshot&empreendimento={empreendimento}&version=${{version}}&timestamp=${{Date.now()}}`;
                }};
                list.appendChild(item);
            }});
        }} else {{
            const noSnapshots = document.createElement('li');
            noSnapshots.textContent = 'Nenhum snapshot disponível';
            noSnapshots.style.padding = '8px 15px';
            noSnapshots.style.color = '#aaa';
            noSnapshots.style.cursor = 'default';
            list.appendChild(noSnapshots);
        }}
        
        menu.appendChild(list);
        document.body.appendChild(menu);
        
        // Fecha o menu quando clicar fora
        function closeMenu(e) {{
            if (!menu.contains(e.target)) {{
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }}
        }}
        
        // Aguarda um frame antes de adicionar o event listener para evitar fechamento imediato
        setTimeout(() => {{
            document.addEventListener('click', closeMenu);
        }}, 0);
    }}
    
    // Adiciona o event listener para clique direito em toda a página
    document.addEventListener('contextmenu', showContextMenu);
    </script>
    """
    
    html(js_code, height=0)

def process_context_actions(df, snapshots):
    """Processa ações do menu de contexto via query parameters."""
    try:
        query_params = st.query_params
        
        action = query_params.get('context_action')
        empreendimento = query_params.get('empreendimento')
        version = query_params.get('version')
        
        if action and empreendimento:
            # Validação básica
            if empreendimento not in df['Empreendimento'].unique():
                st.error(f"Empreendimento '{empreendimento}' não encontrado!")
                st.query_params.clear()
                return
                
            # Limpa os parâmetros
            st.query_params.clear()
            
            if action == 'take_snapshot_local':
                version_name, saved = take_snapshot(df, empreendimento, save_locally=True)
                if saved:
                    st.toast(f"✅ Snapshot '{version_name}' salvo localmente!")
                else:
                    st.toast(f"❌ Erro ao salvar snapshot local.")
                    
            elif action == 'take_snapshot_aws':
                version_name, success = take_snapshot(df, empreendimento, save_locally=False)
                if success:
                    st.toast(f"✅ Snapshot '{version_name}' salvo na AWS!")
                else:
                    st.toast(f"❌ Erro ao salvar snapshot na AWS.")
                    
            elif action == 'restore_snapshot':
                if version:
                    st.warning(f"🔄 Funcionalidade de restaurar snapshot '{version}' não implementada completamente.")
                else:
                    st.error("❌ Versão não especificada para restauração.")
                    
            elif action == 'delete_snapshot':
                if version:
                    # Verifica se existe na AWS
                    if version in snapshots.get(empreendimento, {}):
                        if delete_snapshot(empreendimento, version):
                            st.toast(f"🗑️ Snapshot AWS '{version}' deletado!")
                        else:
                            st.toast(f"❌ Erro ao deletar snapshot AWS.")
                    else:
                        # Verifica se existe localmente
                        local_data = st.session_state.get('local_data', {})
                        if version in local_data and local_data[version].get('empreendimento') == empreendimento:
                            del st.session_state.local_data[version]
                            st.session_state.unsaved_changes = any(
                                not data.get('saved_to_aws') 
                                for data in st.session_state.local_data.values()
                            )
                            st.toast(f"🗑️ Snapshot Local '{version}' deletado!")
                        else:
                            st.toast(f"❌ Snapshot '{version}' não encontrado.")
                else:
                    st.error("❌ Versão não especificada para deleção.")
            
            st.rerun()
            
    except Exception as e:
        st.error(f"❌ Erro ao processar ação do menu de contexto: {e}")
        st.query_params.clear()

# --- Função para gerenciar edição de dados ---

def handle_data_editor_changes(edited_df, original_df, selected_empreendimento):
    """Manipula as mudanças no data_editor e atualiza o DataFrame principal."""
    # Compara os DataFrames para detectar mudanças
    if not edited_df.equals(original_df[original_df['Empreendimento'] == selected_empreendimento]):
        # Atualiza o DataFrame principal
        df_updated = original_df.copy()
        mask = df_updated['Empreendimento'] == selected_empreendimento
        df_updated.loc[mask, edited_df.columns] = edited_df.values
        
        st.session_state.df = df_updated
        st.session_state.unsaved_changes = True
        st.toast("✅ Mudanças aplicadas com sucesso!")
        return True
    return False

# --- Aplicação Principal ---

def main():
    st.set_page_config(layout="wide", page_title="Gantt Chart Baseline")
    st.title("📊 Gráfico de Gantt com Versionamento")
    
    # --- Inicialização de Estado da Sessão ---
    if 'unsaved_changes' not in st.session_state:
        st.session_state.unsaved_changes = False
    if 'local_data' not in st.session_state:
        st.session_state.local_data = {}
    if 'df' not in st.session_state:
        st.session_state.df = create_mock_dataframe()
    if 'show_comparison' not in st.session_state:
        st.session_state.show_comparison = False
    if 'selected_empreendimento' not in st.session_state:
        st.session_state.selected_empreendimento = st.session_state.df['Empreendimento'].unique().tolist()[0]
        
    # --- Inicialização de Banco de Dados ---
    create_snapshots_table()
    
    # --- Carregamento de Dados ---
    df = st.session_state.df
    snapshots = load_snapshots()
    
    # --- Processamento de Ações do Menu de Contexto (DEVE ser antes da sidebar) ---
    process_context_actions(df, snapshots)
    
    # --- Sidebar ---
    
    with st.sidebar:
        st.header("Configurações")
        
        # Seleção de Empreendimento
        empreendimentos = df['Empreendimento'].unique().tolist()
        selected_empreendimento = st.selectbox(
            "🏢 Empreendimento", 
            empreendimentos, 
            key="selected_empreendimento"
        )
        
        df_filtered = df[df['Empreendimento'] == selected_empreendimento].copy()
        
        st.markdown("---")
        st.markdown("### 💾 Dados Locais")
        
        # Indicador de mudanças não salvas
        if st.session_state.unsaved_changes:
            st.warning("⚠️ Você tem dados não salvos na AWS!")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🗑️ Limpar Locais", use_container_width=True, help="Remove todos os dados locais"):
                clear_local_data()
                st.success("Dados locais limpos!")
                st.rerun()
        
        with col2:
            if st.button("🚀 Enviar para AWS", type="primary", use_container_width=True, 
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
        
        st.markdown("---")
        st.markdown("### 📸 Ações Rápidas")
        
        if st.button("📸 Criar Snapshot Local", use_container_width=True):
            try:
                version_name, saved_locally = take_snapshot(df, selected_empreendimento, save_locally=True)
                if saved_locally:
                    st.toast(f"✅ {version_name} salvo localmente!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro: {e}")
        
        if st.button("🚀 Criar Snapshot AWS", use_container_width=True):
            try:
                version_name, success = take_snapshot(df, selected_empreendimento, save_locally=False)
                if success:
                    st.toast(f"✅ {version_name} salvo diretamente na AWS!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro: {e}")
        
        if st.button("⏳ Comparar Períodos", use_container_width=True):
            st.session_state.show_comparison = not st.session_state.show_comparison
            st.rerun()
            
        st.markdown("---")
        st.markdown("### 🔧 Gerenciar Snapshots AWS")
        
        empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
        if empreendimento_snapshots:
            for version_name in sorted(empreendimento_snapshots.keys()):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"`{version_name}`")
                with col2:
                    if st.button("🗑️", key=f"del_aws_{version_name}"):
                        if delete_snapshot(selected_empreendimento, version_name):
                            st.success(f"✅ {version_name} deletado!")
                        st.rerun()
        else:
            st.info("Nenhum snapshot AWS")

    # --- Visualização Principal ---
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader(f"Dados do Projeto: {selected_empreendimento}")
        
        # Exibe informações sobre o estado da conexão
        conn = get_db_connection()
        if not conn:
            st.info("🔶 Modo offline: usando armazenamento local (sem conexão com AWS)")
        
        # Tabela editável - SEM key para evitar conflitos
        edited_df = st.data_editor(
            df_filtered,
            use_container_width=True,
            hide_index=True,
            column_order=('ID_Tarefa', 'Tarefa', 'P0_Previsto_Inicio', 'P0_Previsto_Fim', 'Real_Inicio', 'Real_Fim'),
            num_rows="fixed"
        )
        
        # Botão para aplicar mudanças
        if st.button("💾 Aplicar Mudanças", type="primary"):
            if handle_data_editor_changes(edited_df, df, selected_empreendimento):
                st.rerun()
            
        st.info("💡 **Instruções:** Edite os dados acima e clique em 'Aplicar Mudanças' para salvar. Use o **clique com botão direito** em qualquer lugar da página para acessar o menu de contexto.")
            
    with col2:
        st.subheader("Snapshots AWS")
        empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
        if empreendimento_snapshots:
            for version in sorted(empreendimento_snapshots.keys()):
                st.write(f"• {version} ({empreendimento_snapshots[version]['date']})")
        else:
            st.info("Nenhum snapshot na AWS")
        
        st.subheader("Snapshots Locais")
        local_snapshots = {}
        for version, data in st.session_state.get('local_data', {}).items():
            if data.get('empreendimento') == selected_empreendimento:
                local_snapshots[version] = data
        
        if local_snapshots:
            for version in sorted(local_snapshots.keys()):
                status = "✅" if local_snapshots[version].get('saved_to_aws') else "⏳"
                st.write(f"• {version} ({local_snapshots[version]['created_date']}) {status}")
        else:
            st.info("Nenhum snapshot local")
            
    # --- Menu de Contexto ---
    st.markdown("---")
    st.subheader("Menu de Contexto")
    st.markdown("**Clique com o botão direito do mouse em qualquer lugar da página** para abrir o menu de contexto com opções de snapshot.")
    
    # Prepara dados para o componente de menu de contexto
    local_snapshots_menu = {
        v: d for v, d in st.session_state.get('local_data', {}).items() 
        if d.get('empreendimento') == selected_empreendimento
    }
    
    # Renderiza o menu de contexto
    context_menu_component(selected_empreendimento, empreendimento_snapshots, local_snapshots_menu)
    
    # --- Comparação de Períodos ---
    if st.session_state.show_comparison:
        st.markdown("---")
        display_period_comparison(df_filtered, empreendimento_snapshots)

if __name__ == "__main__":
    main()
