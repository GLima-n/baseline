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
        st.error(f"❌ Erro de conexão com o banco: {e}")
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
            st.error(f"❌ Erro ao criar tabela: {e}")
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        if 'mock_snapshots' not in st.session_state:
            st.session_state.mock_snapshots = {}

def load_snapshots():
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
            st.error(f"❌ Erro ao carregar snapshots: {e}")
            return {}
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        return st.session_state.get('mock_snapshots', {})

def save_snapshot(empreendimento, version_name, snapshot_data, created_date):
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            snapshot_json = json.dumps(snapshot_data, ensure_ascii=False)
            insert_query = """
            INSERT INTO snapshots (empreendimento, version_name, snapshot_data, created_date)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE snapshot_data = VALUES(snapshot_data), created_date = VALUES(created_date)
            """
            cursor.execute(insert_query, (empreendimento, version_name, snapshot_json, created_date))
            conn.commit()
            return True
        except Error as e:
            st.error(f"❌ Erro ao salvar snapshot: {e}")
            return False
        finally:
            if conn.is_connected():
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
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            delete_query = "DELETE FROM snapshots WHERE empreendimento = %s AND version_name = %s"
            cursor.execute(delete_query, (empreendimento, version_name))
            conn.commit()
            return cursor.rowcount > 0
        except Error as e:
            st.error(f"❌ Erro ao deletar snapshot: {e}")
            return False
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        if (empreendimento in st.session_state.get('mock_snapshots', {}) and 
            version_name in st.session_state.mock_snapshots[empreendimento]):
            del st.session_state.mock_snapshots[empreendimento][version_name]
            return True
        return False

def restore_snapshot_to_dataframe(df, empreendimento, version_name, snapshots):
    """Restaura um snapshot para o DataFrame principal"""
    try:
        if empreendimento not in snapshots or version_name not in snapshots[empreendimento]:
            st.error(f"❌ Snapshot '{version_name}' não encontrado")
            return df
        
        snapshot_data = snapshots[empreendimento][version_name]['data']
        df_snapshot = pd.DataFrame(snapshot_data)
        
        # Determina o prefixo da versão
        version_prefix = version_name.split('-')[0]
        
        # Cria novas colunas no DataFrame principal
        for _, row in df_snapshot.iterrows():
            task_id = row['ID_Tarefa']
            mask = (df['ID_Tarefa'] == task_id) & (df['Empreendimento'] == empreendimento)
            
            if mask.any():
                df.loc[mask, f'{version_prefix}_Previsto_Inicio'] = pd.to_datetime(row[f'{version_prefix}_Previsto_Inicio'])
                df.loc[mask, f'{version_prefix}_Previsto_Fim'] = pd.to_datetime(row[f'{version_prefix}_Previsto_Fim'])
        
        return df
        
    except Exception as e:
        st.error(f"❌ Erro ao restaurar snapshot: {e}")
        return df

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
    
    if df_empreendimento.empty:
        raise Exception("Nenhum dado encontrado para o empreendimento selecionado")
    
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

    success = save_snapshot(empreendimento, version_name, snapshot_data, current_date_str)
    
    if success:
        return version_name
    else:
        raise Exception("Falha ao salvar snapshot no banco de dados")

# --- Menu de Contexto Corrigido ---

def create_context_menu_with_callbacks(selected_empreendimento, snapshots):
    """Cria menu de contexto usando callbacks do Streamlit para evitar reload da página"""
    
    empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
    snapshot_options = list(empreendimento_snapshots.keys())
    
    # Usando JavaScript com callbacks para evitar reload
    js_code = f"""
    <script>
    function setupContextMenu() {{
        const ganttArea = document.getElementById('gantt-area');
        const menu = document.createElement('div');
        
        menu.innerHTML = `
            <div class="context-menu" id="contextMenu" style="
                position: fixed;
                background: white;
                border: 1px solid #ccc;
                border-radius: 5px;
                box-shadow: 2px 2px 10px rgba(0,0,0,0.2);
                z-index: 1000;
                display: none;
                min-width: 200px;
            ">
                <div class="context-menu-item" onclick="handleTakeSnapshot()" style="
                    padding: 10px 15px;
                    cursor: pointer;
                    border-bottom: 1px solid #eee;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                ">
                    📸 Tirar Snapshot
                </div>
                <div class="context-menu-item" onclick="handleRestoreSnapshot()" style="
                    padding: 10px 15px;
                    cursor: pointer;
                    border-bottom: 1px solid #eee;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    {'' if snapshot_options else 'color: #999; cursor: not-allowed;'}
                " {'' if snapshot_options else 'onclick="return false"'}>
                    🔄 Restaurar Snapshot
                </div>
                <div class="context-menu-item" onclick="handleDeleteSnapshot()" style="
                    padding: 10px 15px;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    {'' if snapshot_options else 'color: #999; cursor: not-allowed;'}
                " {'' if snapshot_options else 'onclick="return false"'}>
                    🗑️ Deletar Snapshot
                </div>
            </div>
        `;
        
        document.body.appendChild(menu);
        const contextMenu = document.getElementById('contextMenu');
        
        // Funções de handler
        window.handleTakeSnapshot = function() {{
            // Usando parent para acessar o Streamlit
            if (window.parent && window.parent.streamlitApi) {{
                window.parent.streamlitApi.runCallback('take_snapshot');
            }}
            hideMenu();
        }};
        
        window.handleRestoreSnapshot = function() {{
            if ({'true' if snapshot_options else 'false'}) {{
                if (window.parent && window.parent.streamlitApi) {{
                    window.parent.streamlitApi.runCallback('restore_snapshot');
                }}
                hideMenu();
            }}
        }};
        
        window.handleDeleteSnapshot = function() {{
            if ({'true' if snapshot_options else 'false'}) {{
                if (window.parent && window.parent.streamlitApi) {{
                    window.parent.streamlitApi.runCallback('delete_snapshot');
                }}
                hideMenu();
            }}
        }};
        
        function showMenu(x, y) {{
            contextMenu.style.left = x + 'px';
            contextMenu.style.top = y + 'px';
            contextMenu.style.display = 'block';
        }}
        
        function hideMenu() {{
            contextMenu.style.display = 'none';
        }}
        
        // Event listeners
        ganttArea.addEventListener('contextmenu', function(e) {{
            e.preventDefault();
            showMenu(e.pageX, e.pageY);
        }});
        
        document.addEventListener('click', function(e) {{
            if (!contextMenu.contains(e.target)) {{
                hideMenu();
            }}
        }});
        
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') {{
                hideMenu();
            }}
        }});
    }}
    
    // Inicializa quando o documento estiver pronto
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', setupContextMenu);
    }} else {{
        setupContextMenu();
    }}
    </script>
    """
    
    # HTML da área do Gantt
    html_content = f"""
    <div id="gantt-area" style="
        height: 300px; 
        border: 2px dashed #ccc; 
        display: flex; 
        align-items: center; 
        justify-content: center; 
        background-color: #f9f9f9; 
        cursor: pointer; 
        margin: 20px 0;
        border-radius: 8px;
    ">
        <div style="text-align: center;">
            <h3 style="color: #666; margin-bottom: 10px;">Área do Gráfico de Gantt - {selected_empreendimento}</h3>
            <p style="color: #888; margin: 5px 0;">Clique com o botão direito para abrir o menu de snapshot</p>
            <p style="color: #999; font-size: 12px; margin: 5px 0;">
                Snapshots disponíveis: {len(snapshot_options)}
            </p>
        </div>
    </div>
    {js_code}
    """
    
    return html_content

# --- Callbacks para ações do menu ---

def setup_context_menu_callbacks(selected_empreendimento):
    """Configura callbacks para as ações do menu de contexto"""
    
    # Callback para tirar snapshot
    if st.button("📸 Tirar Snapshot", key="context_take_snapshot", use_container_width=True):
        try:
            version_name = take_snapshot(st.session_state.df, selected_empreendimento)
            st.success(f"✅ Snapshot '{version_name}' criado com sucesso!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Erro ao criar snapshot: {e}")
    
    # Callback para restaurar snapshot
    if st.button("🔄 Restaurar Snapshot", key="context_restore_snapshot", use_container_width=True):
        st.session_state.show_restore_modal = True
        st.session_state.restore_empreendimento = selected_empreendimento
        st.rerun()
    
    # Callback para deletar snapshot
    if st.button("🗑️ Deletar Snapshot", key="context_delete_snapshot", use_container_width=True):
        st.session_state.show_delete_modal = True
        st.session_state.delete_empreendimento = selected_empreendimento
        st.rerun()

# --- Modais para Restauração e Deleção ---

def show_restore_modal(empreendimento, snapshots):
    """Modal para selecionar snapshot para restauração"""
    with st.container():
        st.markdown("---")
        st.subheader("🔄 Restaurar Snapshot")
        
        empreendimento_snapshots = snapshots.get(empreendimento, {})
        if not empreendimento_snapshots:
            st.warning("Nenhum snapshot disponível para restauração")
            if st.button("Fechar", key="close_restore_empty"):
                st.session_state.show_restore_modal = False
                st.rerun()
            return
        
        version_options = list(empreendimento_snapshots.keys())
        selected_version = st.selectbox("Selecione o snapshot para restaurar:", version_options, key="restore_select")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Restaurar", use_container_width=True, key="confirm_restore"):
                df_updated = restore_snapshot_to_dataframe(
                    st.session_state.df, empreendimento, selected_version, snapshots
                )
                st.session_state.df = df_updated
                st.session_state.show_restore_modal = False
                st.success(f"✅ Snapshot '{selected_version}' restaurado com sucesso!")
                st.rerun()
        
        with col2:
            if st.button("❌ Cancelar", use_container_width=True, key="cancel_restore"):
                st.session_state.show_restore_modal = False
                st.rerun()
        
        # Preview do snapshot
        st.markdown("**Preview dos dados:**")
        snapshot_data = empreendimento_snapshots[selected_version]['data']
        df_preview = pd.DataFrame(snapshot_data)
        st.dataframe(df_preview, use_container_width=True)

def show_delete_modal(empreendimento, snapshots):
    """Modal para confirmar deleção de snapshot"""
    with st.container():
        st.markdown("---")
        st.subheader("🗑️ Deletar Snapshot")
        
        empreendimento_snapshots = snapshots.get(empreendimento, {})
        if not empreendimento_snapshots:
            st.warning("Nenhum snapshot disponível para deleção")
            if st.button("Fechar", key="close_delete_empty"):
                st.session_state.show_delete_modal = False
                st.rerun()
            return
        
        version_options = list(empreendimento_snapshots.keys())
        selected_version = st.selectbox("Selecione o snapshot para deletar:", version_options, key="delete_select")
        
        st.warning(f"⚠️ Tem certeza que deseja deletar o snapshot '{selected_version}'? Esta ação não pode ser desfeita.")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Confirmar Deleção", type="primary", use_container_width=True, key="confirm_delete"):
                if delete_snapshot(empreendimento, selected_version):
                    st.session_state.show_delete_modal = False
                    st.success(f"✅ Snapshot '{selected_version}' deletado com sucesso!")
                    st.rerun()
        
        with col2:
            if st.button("❌ Cancelar", use_container_width=True, key="cancel_delete"):
                st.session_state.show_delete_modal = False
                st.rerun()

# --- Visualização de Comparação de Período ---

def display_period_comparison(df_filtered, empreendimento_snapshots):
    st.subheader(f"⏳ Comparação de Período - {df_filtered['Empreendimento'].iloc[0]}")
    
    version_options = ["P0 (Planejamento Original)"]
    version_options.extend(sorted(empreendimento_snapshots.keys()))
    
    if len(version_options) < 2:
        st.warning("⚠️ São necessários pelo menos 2 snapshots para comparação")
        return
    
    col1, col2 = st.columns(2)
    with col1:
        version_a = st.selectbox("Linha de Base A", version_options, index=0, key="version_a")
    with col2:
        default_index_b = 1 if len(version_options) > 1 else 0
        version_b = st.selectbox("Linha de Base B", version_options, index=default_index_b, key="version_b")
        
    if version_a == version_b:
        st.warning("⚠️ Selecione duas linhas de base diferentes para comparação")
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
    st.set_page_config(layout="wide", page_title="Gantt Chart Baseline", page_icon="📊")
    st.title("📊 Gráfico de Gantt com Versionamento")
    
    # Inicialização
    if 'df' not in st.session_state:
        st.session_state.df = create_mock_dataframe()
    
    create_snapshots_table()
    
    # Dados
    df = st.session_state.df
    snapshots = load_snapshots()
    
    # Sidebar
    st.sidebar.title("🎯 Controle do Projeto")
    empreendimentos = df['Empreendimento'].unique().tolist()
    selected_empreendimento = st.sidebar.selectbox("🏢 Empreendimento", empreendimentos)
    df_filtered = df[df['Empreendimento'] == selected_empreendimento].copy()
    
    # Botões de ação na sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📸 Ações Rápidas")
    
    if st.sidebar.button("📸 Criar Snapshot", use_container_width=True, key="sidebar_take_snapshot"):
        try:
            version_name = take_snapshot(df, selected_empreendimento)
            st.success(f"✅ {version_name} criado!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Erro: {e}")
    
    if st.sidebar.button("⏳ Comparar Períodos", use_container_width=True, key="sidebar_compare"):
        st.session_state.show_comparison = not st.session_state.get('show_comparison', False)
        st.rerun()
    
    # Visualização principal
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📋 Dados do Projeto")
        st.dataframe(df_filtered, use_container_width=True)
    
    with col2:
        st.subheader("💾 Snapshots")
        empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
        if empreendimento_snapshots:
            for version in sorted(empreendimento_snapshots.keys()):
                st.write(f"• **{version}**")
                st.caption(f"Criado em: {empreendimento_snapshots[version]['date']}")
        else:
            st.info("ℹ️ Nenhum snapshot disponível")
    
    # Menu de contexto corrigido
    st.markdown("---")
    st.subheader("🎮 Menu de Contexto (Clique com Botão Direito)")
    
    # Área do menu de contexto
    context_menu_html = create_context_menu_with_callbacks(selected_empreendimento, snapshots)
    html(context_menu_html, height=350)
    
    # Callbacks (ocultos inicialmente)
    with st.container():
        st.markdown("---")
        st.subheader("Ações do Menu de Contexto")
        setup_context_menu_callbacks(selected_empreendimento)
    
    # Modais
    if st.session_state.get('show_restore_modal', False):
        show_restore_modal(st.session_state.restore_empreendimento, snapshots)
    
    if st.session_state.get('show_delete_modal', False):
        show_delete_modal(st.session_state.delete_empreendimento, snapshots)
    
    # Comparação de períodos
    if st.session_state.get('show_comparison', False):
        st.markdown("---")
        empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
        display_period_comparison(df_filtered, empreendimento_snapshots)
    
    # Gerenciamento de snapshots na sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔧 Gerenciamento Avançado")
    
    empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
    if empreendimento_snapshots:
        for version_name in sorted(empreendimento_snapshots.keys()):
            col1, col2, col3 = st.sidebar.columns([3, 1, 1])
            with col1:
                st.write(f"`{version_name}`")
            with col2:
                if st.button("🔄", key=f"restore_{version_name}"):
                    df_updated = restore_snapshot_to_dataframe(
                        df, selected_empreendimento, version_name, snapshots
                    )
                    st.session_state.df = df_updated
                    st.success(f"✅ {version_name} restaurado!")
                    st.rerun()
            with col3:
                if st.button("🗑️", key=f"del_{version_name}"):
                    if delete_snapshot(selected_empreendimento, version_name):
                        st.rerun()

if __name__ == "__main__":
    main()
