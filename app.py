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
            st.success("✅ Tabela de snapshots verificada/criada com sucesso!")
        except Error as e:
            st.error(f"❌ Erro ao criar tabela: {e}")
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        if 'mock_snapshots' not in st.session_state:
            st.session_state.mock_snapshots = {}
        st.info("📝 Modo mock ativado - usando session state para armazenamento")

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
            st.success(f"✅ Snapshot '{version_name}' salvo com sucesso!")
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
        st.success(f"✅ Snapshot '{version_name}' salvo localmente!")
        return True

def delete_snapshot(empreendimento, version_name):
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            delete_query = "DELETE FROM snapshots WHERE empreendimento = %s AND version_name = %s"
            cursor.execute(delete_query, (empreendimento, version_name))
            conn.commit()
            success = cursor.rowcount > 0
            if success:
                st.success(f"✅ Snapshot '{version_name}' deletado com sucesso!")
            else:
                st.warning(f"⚠️ Snapshot '{version_name}' não encontrado")
            return success
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
            st.success(f"✅ Snapshot '{version_name}' deletado localmente!")
            return True
        st.warning(f"⚠️ Snapshot '{version_name}' não encontrado")
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
        
        st.success(f"✅ Snapshot '{version_name}' restaurado com sucesso!")
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

# --- Menu de Contexto Melhorado ---

def create_enhanced_context_menu(selected_empreendimento, snapshots):
    """Cria um menu de contexto melhorado com funcionalidades completas"""
    
    empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
    snapshot_options = list(empreendimento_snapshots.keys())
    
    html_code = f"""
<div id="gantt-area" style="height: 300px; border: 2px dashed #ccc; display: flex; align-items: center; justify-content: center; background-color: #f9f9f9; cursor: pointer; margin: 20px 0;">
    <div style="text-align: center;">
        <h3>Área do Gráfico de Gantt - {selected_empreendimento}</h3>
        <p>Clique com o botão direito para abrir o menu de snapshot</p>
        <p><small>Snapshots disponíveis: {len(snapshot_options)}</small></p>
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
    min-width: 200px;
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
.context-menu-disabled {{
    color: #999;
    cursor: not-allowed;
}}
.context-menu-disabled:hover {{
    background: white;
}}
</style>

<script>
// Variável global para armazenar a ação
let snapshotAction = null;

// Cria o menu de contexto
const menu = document.createElement('div');
menu.className = 'context-menu';
menu.innerHTML = `
    <div class="context-menu-item" onclick="takeSnapshot()">
        📸 Tirar Snapshot
    </div>
    <div class="context-menu-item {'' if snapshot_options else 'context-menu-disabled'}" 
         onclick="{'' if snapshot_options else 'return false'}" 
         {'takeSnapshotAction(\"restore_snapshot\")' if snapshot_options else ''}>
        🔄 Restaurar Snapshot
    </div>
    <div class="context-menu-item {'' if snapshot_options else 'context-menu-disabled'}" 
         onclick="{'' if snapshot_options else 'return false'}" 
         {'takeSnapshotAction(\"delete_snapshot\")' if snapshot_options else ''}>
        🗑️ Deletar Snapshot
    </div>
`;
document.body.appendChild(menu);

// Funções do menu
function takeSnapshot() {{
    snapshotAction = 'take_snapshot';
    hideMenu();
    const link = document.createElement('a');
    link.href = `?snapshot_action=take_snapshot&empreendimento={selected_empreendimento}`;
    link.click();
}}

function takeSnapshotAction(action) {{
    snapshotAction = action;
    hideMenu();
    // Abre modal para selecionar snapshot
    const link = document.createElement('a');
    link.href = `?snapshot_action=${{action}}&empreendimento={selected_empreendimento}&open_modal=true`;
    link.click();
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
</script>
"""
    return html_code

# --- Função para processar ações do menu ---

def process_snapshot_actions():
    """Processa ações do menu de contexto via query parameters"""
    query_params = st.query_params
    
    action = query_params.get('snapshot_action')
    empreendimento = query_params.get('empreendimento')
    open_modal = query_params.get('open_modal')
    
    if action and empreendimento:
        # Limpa os parâmetros
        st.query_params.clear()
        
        df = st.session_state.df
        snapshots = load_snapshots()
        
        if action == 'take_snapshot':
            try:
                version_name = take_snapshot(df, empreendimento)
                st.success(f"✅ Snapshot '{version_name}' criado com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao criar snapshot: {e}")
        
        elif action == 'restore_snapshot':
            if open_modal:
                st.session_state.show_restore_modal = True
                st.session_state.restore_empreendimento = empreendimento
            else:
                st.info("🔄 Selecione um snapshot para restaurar")
        
        elif action == 'delete_snapshot':
            if open_modal:
                st.session_state.show_delete_modal = True
                st.session_state.delete_empreendimento = empreendimento
            else:
                st.info("🗑️ Selecione um snapshot para deletar")

# --- Modais para Restauração e Deleção ---

def show_restore_modal(empreendimento, snapshots):
    """Modal para selecionar snapshot para restauração"""
    st.markdown("---")
    st.subheader("🔄 Restaurar Snapshot")
    
    empreendimento_snapshots = snapshots.get(empreendimento, {})
    if not empreendimento_snapshots:
        st.warning("Nenhum snapshot disponível para restauração")
        return
    
    version_options = list(empreendimento_snapshots.keys())
    selected_version = st.selectbox("Selecione o snapshot para restaurar:", version_options)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Restaurar", use_container_width=True):
            df_updated = restore_snapshot_to_dataframe(
                st.session_state.df, empreendimento, selected_version, snapshots
            )
            st.session_state.df = df_updated
            st.session_state.show_restore_modal = False
            st.rerun()
    
    with col2:
        if st.button("❌ Cancelar", use_container_width=True):
            st.session_state.show_restore_modal = False
            st.rerun()
    
    # Preview do snapshot
    st.markdown("**Preview dos dados:**")
    snapshot_data = empreendimento_snapshots[selected_version]['data']
    df_preview = pd.DataFrame(snapshot_data)
    st.dataframe(df_preview, use_container_width=True)

def show_delete_modal(empreendimento, snapshots):
    """Modal para confirmar deleção de snapshot"""
    st.markdown("---")
    st.subheader("🗑️ Deletar Snapshot")
    
    empreendimento_snapshots = snapshots.get(empreendimento, {})
    if not empreendimento_snapshots:
        st.warning("Nenhum snapshot disponível para deleção")
        return
    
    version_options = list(empreendimento_snapshots.keys())
    selected_version = st.selectbox("Selecione o snapshot para deletar:", version_options)
    
    st.warning(f"⚠️ Tem certeza que deseja deletar o snapshot '{selected_version}'? Esta ação não pode ser desfeita.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Confirmar Deleção", type="primary", use_container_width=True):
            if delete_snapshot(empreendimento, selected_version):
                st.session_state.show_delete_modal = False
                st.rerun()
    
    with col2:
        if st.button("❌ Cancelar", use_container_width=True):
            st.session_state.show_delete_modal = False
            st.rerun()

# --- Visualização de Comparação de Período Melhorada ---

def display_enhanced_period_comparison(df_filtered, empreendimento_snapshots):
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
    
    # Cálculos de métricas
    df_merged['Duracao_A'] = (df_merged['Fim_A'] - df_merged['Inicio_A']).dt.days
    df_merged['Duracao_B'] = (df_merged['Fim_B'] - df_merged['Inicio_B']).dt.days
    df_merged['Diferenca_Duracao'] = df_merged['Duracao_B'] - df_merged['Duracao_A']
    df_merged['Desvio_Inicio'] = (df_merged['Inicio_B'] - df_merged['Inicio_A']).dt.days
    df_merged['Desvio_Fim'] = (df_merged['Fim_B'] - df_merged['Fim_A']).dt.days
    
    # Adiciona contexto das tarefas
    df_context = df_filtered[['ID_Tarefa', 'Tarefa']].drop_duplicates()
    df_final = df_context.merge(df_merged, on='ID_Tarefa')
    
    # Exibe métricas resumidas
    st.metric("Total de Tarefas Comparadas", len(df_final))
    st.metric("Desvio Médio de Início (dias)", f"{df_final['Desvio_Inicio'].mean():.1f}")
    st.metric("Desvio Médio de Fim (dias)", f"{df_final['Desvio_Fim'].mean():.1f}")
    
    # Dataframe com formatação condicional
    def color_differences(val):
        if isinstance(val, (int, float)):
            if val > 0:
                return 'color: red; background-color: #ffebee'
            elif val < 0:
                return 'color: green; background-color: #e8f5e8'
        return ''
    
    styled_df = df_final.style.applymap(color_differences, 
                                      subset=['Diferenca_Duracao', 'Desvio_Inicio', 'Desvio_Fim'])
    
    st.dataframe(styled_df, use_container_width=True)
    
    # Download dos resultados
    csv = df_final.to_csv(index=False)
    st.download_button(
        label="📥 Download da Comparação (CSV)",
        data=csv,
        file_name=f"comparacao_{version_a}_vs_{version_b}.csv",
        mime="text/csv"
    )

# --- Aplicação Principal ---

def main():
    st.set_page_config(layout="wide", page_title="Gantt Chart Baseline", page_icon="📊")
    st.title("📊 Gráfico de Gantt com Versionamento")
    
    # Inicialização
    if 'initialized' not in st.session_state:
        create_snapshots_table()
        st.session_state.df = create_mock_dataframe()
        st.session_state.initialized = True
    
    # Processa ações do menu primeiro
    process_snapshot_actions()
    
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
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("📸 Criar Snapshot", use_container_width=True):
            try:
                version_name = take_snapshot(df, selected_empreendimento)
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro: {e}")
    
    with col2:
        if st.button("⏳ Comparar", use_container_width=True):
            st.session_state.show_comparison = not st.session_state.get('show_comparison', False)
            st.rerun()
    
    # Visualização principal
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📋 Dados do Projeto")
        st.dataframe(df_filtered, use_container_width=True)
        
        # Estatísticas rápidas
        st.metric("Total de Tarefas", len(df_filtered))
        st.metric("Período do Projeto", 
                 f"{df_filtered['Real_Inicio'].min().strftime('%d/%m/%Y')} a {df_filtered['Real_Fim'].max().strftime('%d/%m/%Y')}")
    
    with col2:
        st.subheader("💾 Snapshots")
        empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
        if empreendimento_snapshots:
            for version in sorted(empreendimento_snapshots.keys()):
                date = empreendimento_snapshots[version]['date']
                st.write(f"• **{version}**")
                st.caption(f"Criado em: {date}")
        else:
            st.info("ℹ️ Nenhum snapshot disponível")
            st.caption("Use o botão direito na área do Gantt para criar o primeiro snapshot")
    
    # Menu de contexto
    st.markdown("---")
    st.subheader("🎮 Menu de Contexto (Clique com Botão Direito)")
    context_menu_html = create_enhanced_context_menu(selected_empreendimento, snapshots)
    html(context_menu_html, height=350)
    
    # Modais
    if st.session_state.get('show_restore_modal', False):
        show_restore_modal(st.session_state.restore_empreendimento, snapshots)
    
    if st.session_state.get('show_delete_modal', False):
        show_delete_modal(st.session_state.delete_empreendimento, snapshots)
    
    # Comparação de períodos
    if st.session_state.get('show_comparison', False):
        st.markdown("---")
        empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
        display_enhanced_period_comparison(df_filtered, empreendimento_snapshots)
    
    # Gerenciamento de snapshots na sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔧 Gerenciamento Avançado")
    
    empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
    if empreendimento_snapshots:
        st.sidebar.write("**Snapshots disponíveis:**")
        for version_name in sorted(empreendimento_snapshots.keys()):
            with st.sidebar.expander(f"📁 {version_name}"):
                st.write(f"Data: {empreendimento_snapshots[version_name]['date']}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🔄 Restaurar", key=f"restore_{version_name}"):
                        df_updated = restore_snapshot_to_dataframe(
                            df, selected_empreendimento, version_name, snapshots
                        )
                        st.session_state.df = df_updated
                        st.rerun()
                with col2:
                    if st.button("🗑️", key=f"del_{version_name}"):
                        if delete_snapshot(selected_empreendimento, version_name):
                            st.rerun()

if __name__ == "__main__":
    main()
