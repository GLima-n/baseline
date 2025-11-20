'''
import streamlit as st
import pandas as pd
import json
from datetime import datetime
import mysql.connector
from mysql.connector import Error
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

# --- Funções de Banco de Dados (Mock para simulação) ---

def get_db_connection():
    """Tenta conectar ao banco de dados, usando mock se as credenciais não existirem."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        return None

def create_snapshots_table():
    """Cria a tabela de snapshots se não existir (ou simula a criação)."""
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
    """Carrega todos os snapshots do banco AWS (ou mock)."""
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
    """Salva um novo snapshot no banco AWS (ou mock)."""
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
    """Deleta um snapshot específico (ou mock)."""
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
    """Cria um DataFrame de exemplo para simular os dados do Gantt."""
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

# --- Lógica de Snapshot (Backend) ---

def take_snapshot(df, empreendimento):
    """Cria um novo snapshot (linha de base) para o empreendimento."""
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

# --- Geração do Gráfico de Gantt (Mock) ---

def create_gantt_chart(df):
    """Função mock para simular a criação do gráfico de Gantt."""
    st.subheader("Gráfico de Gantt (Visualização Mock)")
    df_display = df[['Empreendimento', 'Tarefa', 'Real_Inicio', 'Real_Fim', 'Previsto_Inicio', 'Previsto_Fim']].copy()
    
    for col in ['Real_Inicio', 'Real_Fim', 'Previsto_Inicio', 'Previsto_Fim']:
        if pd.api.types.is_datetime64_any_dtype(df_display[col]):
            df_display[col] = df_display[col].dt.strftime('%Y-%m-%d')
            
    st.dataframe(df_display, use_container_width=True, hide_index=True)
    
    # Retorna o HTML da área que o JS vai usar como alvo
    return '<div id="gantt-chart-area" style="border: 2px dashed #ccc; padding: 20px; text-align: center; margin-top: 20px; min-height: 200px;">Clique com o botão direito nesta área para o menu de Snapshot.</div>'

# --- Funções de Injeção de Componentes (JS/CSS) ---

def inject_js_context_menu(gantt_area_html, empreendimento):
    """Injeta o HTML da área do gráfico, o CSS e o JavaScript do menu de contexto."""
    # 1. Carrega o CSS
    try:
        with open("circular_menu(1).css", "r") as f:
            css_content = f.read()
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.error("Arquivo 'circular_menu.css' não encontrado.")

    # 2. Carrega o JavaScript
    try:
        with open("circular_menu(1).js", "r") as f:
            js_content = f.read()
    except FileNotFoundError:
        st.error("Arquivo 'circular_menu.js' não encontrado.")
        js_content = ""

    # 3. O HTML da área do gráfico é injetado primeiro.
    st.markdown(gantt_area_html, unsafe_allow_html=True)

    # 4. O script de inicialização é injetado em seguida.
    init_script = f"""
    <script>
        {js_content}
        // Garante que o script rode após o DOM estar pronto
        if (document.readyState === 'complete') {{
            injectCircularMenu('{empreendimento}');
        }} else {{
            window.addEventListener('load', () => injectCircularMenu('{empreendimento}'));
        }}
    </script>
    """
    html(init_script, height=0, width=0)

# --- Função Principal do App ---

def main():
    st.set_page_config(page_title="Gantt Chart Baseline/Snapshot - AWS", layout="wide")
    st.title("📊 Gráfico de Gantt com Versionamento de Planejamento - AWS MySQL")

    create_snapshots_table()

    if 'df' not in st.session_state:
        st.session_state.df = create_mock_dataframe()
    df = st.session_state.df

    snapshots = load_snapshots()

    st.sidebar.header("⚙️ Controles")
    st.sidebar.markdown("### 1. Selecione o Empreendimento")
    empreendimentos = df['Empreendimento'].unique()
    selected_empreendimento = st.sidebar.selectbox(
        "Selecione o Empreendimento",
        options=empreendimentos,
        index=0,
        key='empreendimento_selector'
    )

    df_filtered = df[df['Empreendimento'] == selected_empreendimento].copy()
    empreendimento_snapshots = snapshots.get(selected_empreendimento, {})

    # --- Tratamento dos Parâmetros de URL (Correção) ---
    query_params = st.query_params.to_dict()
    
    if query_params.get('take_snapshot') == 'true' and query_params.get('empreendimento') == selected_empreendimento:
        try:
            new_version = take_snapshot(df, selected_empreendimento)
            st.success(f"✅ Snapshot **{new_version}** criado com sucesso!")
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"❌ Erro ao criar snapshot: {e}")
    
    if query_params.get('view_period') == 'true' and query_params.get('empreendimento') == selected_empreendimento:
        st.info("⏳ Funcionalidade 'Visualizar Período' acionada. Implementação pendente.")
        st.query_params.clear()

    st.sidebar.markdown("### 2. Gerenciar Snapshots")
    if st.sidebar.button("📸 Fotografar Cenário Real como Previsto", use_container_width=True):
        try:
            new_version = take_snapshot(df, selected_empreendimento)
            st.success(f"✅ Snapshot **{new_version}** criado com sucesso!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Erro ao criar snapshot: {e}")

    if st.sidebar.button("⏳ Visualizar Período entre Linhas de Base", use_container_width=True):
        st.info("Funcionalidade de visualização de período ainda não implementada.")

    st.sidebar.markdown("### 3. Selecione a Versão de Planejamento (Baseline) para Comparação")
    version_options = ['Real Atual (Comparar com P0)'] + list(empreendimento_snapshots.keys())
    selected_version = st.sidebar.selectbox(
        "Real Atual (Comparar com...)",
        options=version_options,
        index=0
    )
    
    if selected_version == "Real Atual (Comparar com P0)":
        df_filtered['Previsto_Inicio'] = df_filtered['P0_Previsto_Inicio']
        df_filtered['Previsto_Fim'] = df_filtered['P0_Previsto_Fim']
        st.info("📊 Comparando Real Atual com a Linha de Base **P0 (Padrão)**.")
    elif selected_version in empreendimento_snapshots:
        version_data_list = empreendimento_snapshots[selected_version]['data']
        version_data = pd.DataFrame(version_data_list)
        version_prefix = selected_version.split('-')[0]
        col_inicio = f'{version_prefix}_Previsto_Inicio'
        col_fim = f'{version_prefix}_Previsto_Fim'
        version_data = version_data.rename(columns={col_inicio: 'Previsto_Inicio', col_fim: 'Previsto_Fim'})
        version_data['Previsto_Inicio'] = pd.to_datetime(version_data['Previsto_Inicio'])
        version_data['Previsto_Fim'] = pd.to_datetime(version_data['Previsto_Fim'])
        df_filtered = df_filtered.merge(
            version_data[['ID_Tarefa', 'Previsto_Inicio', 'Previsto_Fim']],
            on='ID_Tarefa',
            how='left',
            suffixes=('_atual', '_novo')
        )
        df_filtered['Previsto_Inicio'] = df_filtered['Previsto_Inicio_novo']
        df_filtered['Previsto_Fim'] = df_filtered['Previsto_Fim_novo']
        df_filtered = df_filtered.drop(columns=['Previsto_Inicio_atual', 'Previsto_Fim_atual', 'Previsto_Inicio_novo', 'Previsto_Fim_novo'], errors='ignore')
        st.info(f"📊 Comparando Real Atual com a Linha de Base: **{selected_version}**.")
    
    gantt_area_html = create_gantt_chart(df_filtered)
    inject_js_context_menu(gantt_area_html, selected_empreendimento)
    
    st.sidebar.markdown("---
### 💾 Snapshots Salvos")
    if empreendimento_snapshots:
        for version_name in sorted(empreendimento_snapshots.keys()):
            col1, col2 = st.sidebar.columns([3, 1])
            with col1:
                st.write(f"`{version_name}`")
            with col2:
                if st.button("🗑️", key=f"del_{version_name}"):
                    if delete_snapshot(selected_empreendimento, version_name):
                        st.success(f"✅ Snapshot {version_name} deletado!")
                        st.rerun()
    else:
        st.sidebar.info("ℹ️ Nenhum snapshot salvo para este empreendimento")
        
    st.sidebar.markdown("---
### 📥 Exportar Dados")
    txt_content = "Relatório de Snapshots de Linha de Base - AWS MySQL\n\n"
    txt_content += f"Data de exportação: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
    txt_content += f"Empreendimento atual: {selected_empreendimento}\n\n"
    if not snapshots:
        txt_content += "Nenhum snapshot salvo ainda."
    else:
        for empreendimento, versions in snapshots.items():
            txt_content += f"==================================================\n"
            txt_content += f"Empreendimento: {empreendimento}\n"
            txt_content += f"==================================================\n"
            for version, data in versions.items():
                txt_content += f"--- Versão: {version} (Data: {data['date']}) ---\n"
                df_version = pd.DataFrame(data['data'])
                txt_content += df_version.to_string(index=False) + "\n\n"
    
    st.sidebar.download_button(
        label="💾 Baixar Relatório de Snapshots (TXT)",
        data=txt_content,
        file_name=f"relatorio_snapshots_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        mime="text/plain",
        use_container_width=True
    )
    
    with st.sidebar.expander("🔧 Informações de Debug"):
        st.json(snapshots)
        st.metric("Total de Snapshots", sum(len(versions) for versions in snapshots.values()))
        st.metric("Snapshots deste Empreendimento", len(empreendimento_snapshots))

if __name__ == "__main__":
    main()
'''
