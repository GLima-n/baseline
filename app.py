import streamlit as st
import pandas as pd
import json
from datetime import datetime
import mysql.connector
from mysql.connector import Error

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
            st.error(f"Erro ao criar tabela: {e}")
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
            st.error(f"Erro ao carregar snapshots: {e}")
            return {}
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        return st.session_state.mock_snapshots

def save_snapshot(empreendimento, version_name, snapshot_data, created_date):
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
            st.error(f"Erro ao deletar snapshot: {e}")
            return False
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        if empreendimento in st.session_state.mock_snapshots and version_name in st.session_state.mock_snapshots[empreendimento]:
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

# --- Menu de Contexto Simples com Streamlit ---

def create_simple_context_menu(selected_empreendimento):
    """Cria um menu de contexto simples usando apenas Streamlit"""
    
    st.markdown("---")
    st.subheader("📋 Menu de Contexto")
    
    # Área clicável simulada
    with st.container():
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown(
                f"""
                <div style='
                    height: 200px; 
                    border: 2px dashed #ccc; 
                    display: flex; 
                    align-items: center; 
                    justify-content: center; 
                    background-color: #f9f9f9; 
                    cursor: pointer;
                    border-radius: 10px;
                    margin: 20px 0;
                    text-align: center;
                '>
                    <div>
                        <h3>📊 Área do Gráfico de Gantt</h3>
                        <p>Use os botões abaixo para ações de snapshot</p>
                    </div>
                </div>
                """, 
                unsafe_allow_html=True
            )
    
    # Botões de ação
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📸 Tirar Snapshot", use_container_width=True):
            try:
                version_name = take_snapshot(st.session_state.df, selected_empreendimento)
                st.success(f"✅ Snapshot '{version_name}' criado com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao criar snapshot: {e}")
    
    with col2:
        if st.button("🔄 Restaurar Snapshot", use_container_width=True):
            st.info("🔧 Funcionalidade em desenvolvimento")
            # Aqui você pode adicionar a lógica para restaurar snapshots
    
    with col3:
        if st.button("🗑️ Gerenciar Snapshots", use_container_width=True):
            st.session_state.show_snapshot_management = not st.session_state.get('show_snapshot_management', False)
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

# --- Gerenciamento de Snapshots ---

def display_snapshot_management(selected_empreendimento, snapshots):
    st.subheader("💾 Gerenciamento de Snapshots")
    
    empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
    
    if not empreendimento_snapshots:
        st.info("Nenhum snapshot disponível para este empreendimento.")
        return
    
    for version_name in sorted(empreendimento_snapshots.keys()):
        with st.expander(f"📁 {version_name}"):
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col1:
                st.write(f"**Data de criação:** {empreendimento_snapshots[version_name]['date']}")
                st.write(f"**Total de tarefas:** {len(empreendimento_snapshots[version_name]['data'])}")
            
            with col2:
                if st.button("🔍 Visualizar", key=f"view_{version_name}"):
                    st.session_state[f"view_snapshot_{version_name}"] = True
            
            with col3:
                if st.button("🗑️ Deletar", key=f"del_{version_name}"):
                    if delete_snapshot(selected_empreendimento, version_name):
                        st.success(f"✅ {version_name} deletado!")
                        st.rerun()
                    else:
                        st.error(f"❌ Erro ao deletar {version_name}")
            
            # Visualização do snapshot
            if st.session_state.get(f"view_snapshot_{version_name}", False):
                snapshot_data = empreendimento_snapshots[version_name]['data']
                df_snapshot = pd.DataFrame(snapshot_data)
                st.dataframe(df_snapshot, use_container_width=True)
                
                if st.button("Fechar Visualização", key=f"close_{version_name}"):
                    st.session_state[f"view_snapshot_{version_name}"] = False
                    st.rerun()

# --- Aplicação Principal ---

def main():
    st.set_page_config(layout="wide", page_title="Gantt Chart Baseline")
    st.title("📊 Gráfico de Gantt com Versionamento")
    
    # Inicialização
    if 'df' not in st.session_state:
        st.session_state.df = create_mock_dataframe()
    
    create_snapshots_table()
    
    df = st.session_state.df
    snapshots = load_snapshots()
    
    # Sidebar
    st.sidebar.header("🔧 Configurações")
    empreendimentos = df['Empreendimento'].unique().tolist()
    selected_empreendimento = st.sidebar.selectbox("🏢 Empreendimento", empreendimentos)
    df_filtered = df[df['Empreendimento'] == selected_empreendimento].copy()
    
    # Ações rápidas na sidebar
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚡ Ações Rápidas")
    
    if st.sidebar.button("📸 Criar Snapshot", use_container_width=True, type="primary"):
        try:
            version_name = take_snapshot(df, selected_empreendimento)
            st.sidebar.success(f"✅ {version_name} criado!")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"❌ Erro: {e}")
    
    if st.sidebar.button("⏳ Comparar Períodos", use_container_width=True):
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
    
    # Menu de contexto simplificado
    create_simple_context_menu(selected_empreendimento)
    
    # Gerenciamento de snapshots
    if st.session_state.get('show_snapshot_management', False):
        st.markdown("---")
        display_snapshot_management(selected_empreendimento, snapshots)
    
    # Comparação de períodos
    if st.session_state.get('show_comparison', False):
        st.markdown("---")
        empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
        display_period_comparison(df_filtered, empreendimento_snapshots)

if __name__ == "__main__":
    main()
