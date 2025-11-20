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

# --- Menu de Contexto com Formulário ---

def create_context_menu_with_form(selected_empreendimento):
    """Cria menu de contexto usando formulário HTML"""
    
    html_code = f'''
<div id="gantt-area" style="height: 300px; border: 2px dashed #ccc; display: flex; align-items: center; justify-content: center; background-color: #f9f9f9; cursor: pointer; margin: 20px 0;">
    <div style="text-align: center;">
        <h3>Área do Gráfico de Gantt</h3>
        <p>Clique com o botão direito para abrir o menu de snapshot</p>
        <p><small>Empreendimento: {selected_empreendimento}</small></p>
    </div>
</div>

<!-- Formulário invisível para enviar ações -->
<form id="context-menu-form" method="get" style="display: none;">
    <input type="hidden" name="context_action" id="context_action_input">
    <input type="hidden" name="context_empreendimento" id="context_empreendimento_input" value="{selected_empreendimento}">
    <input type="submit" id="context_submit">
</form>

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
    <div class="context-menu-item" onclick="handleAction('take_snapshot')">📸 Tirar Snapshot</div>
    <div class="context-menu-item" onclick="handleAction('restore_snapshot')">🔄 Restaurar Snapshot</div>
    <div class="context-menu-item" onclick="handleAction('delete_snapshot')">🗑️ Deletar Snapshot</div>
`;
document.body.appendChild(menu);

function handleAction(action) {{
    // Preenche o formulário e submete
    document.getElementById('context_action_input').value = action;
    document.getElementById('context_submit').click();
    hideMenu();
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
'''
    return html_code

# --- Processamento de Ações do Menu ---

def process_context_menu_actions():
    """Processa ações do menu de contexto via query parameters"""
    query_params = st.query_params
    
    action = query_params.get('context_action')
    empreendimento = query_params.get('context_empreendimento')
    
    if action and empreendimento:
        # Limpa os parâmetros imediatamente para evitar loop
        st.query_params.clear()
        
        df = create_mock_dataframe()
        
        if action == 'take_snapshot':
            try:
                version_name = take_snapshot(df, empreendimento)
                st.success(f"✅ Snapshot '{version_name}' criado com sucesso!")
                # Força um rerun para atualizar a interface
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao criar snapshot: {e}")
        elif action == 'restore_snapshot':
            st.warning("🔄 Funcionalidade de restaurar snapshot não implementada")
        elif action == 'delete_snapshot':
            st.warning("🗑️ Use a sidebar para deletar snapshots específicos")

# --- Aplicação Principal ---

def main():
    st.set_page_config(layout="wide", page_title="Gantt Chart Baseline")
    st.title("📊 Gráfico de Gantt com Versionamento")
    
    # Inicialização
    create_snapshots_table()
    
    # Processa ações do menu de contexto PRIMEIRO
    process_context_menu_actions()
    
    # Inicializa dados se necessário
    if 'df' not in st.session_state:
        st.session_state.df = create_mock_dataframe()
    
    # Carrega dados
    df = st.session_state.df
    snapshots = load_snapshots()
    
    # Sidebar
    with st.sidebar:
        st.header("🎯 Controles")
        
        empreendimentos = df['Empreendimento'].unique().tolist()
        selected_empreendimento = st.selectbox("🏢 Empreendimento", empreendimentos)
        df_filtered = df[df['Empreendimento'] == selected_empreendimento].copy()
        
        st.markdown("---")
        st.subheader("📸 Ações Rápidas")
        
        # Botão para criar snapshot
        if st.button("📸 Criar Novo Snapshot", use_container_width=True, type="primary"):
            try:
                version_name = take_snapshot(df, selected_empreendimento)
                st.success(f"✅ {version_name} criado!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro: {e}")
        
        # Seletor de versão
        empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
        version_options = ["Real Atual (Comparar com P0)"]
        version_options.extend(sorted(empreendimento_snapshots.keys()))
        
        selected_version = st.selectbox(
            "🔄 Versão para Comparação",
            version_options,
            index=0
        )
        
        st.markdown("---")
        st.subheader("💾 Snapshots Salvos")
        
        # Lista de snapshots com opção de deletar
        if empreendimento_snapshots:
            for version_name in sorted(empreendimento_snapshots.keys()):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**{version_name}**")
                    st.caption(f"Criado em: {empreendimento_snapshots[version_name]['date']}")
                with col2:
                    if st.button("🗑️", key=f"del_{version_name}"):
                        if delete_snapshot(selected_empreendimento, version_name):
                            st.success(f"✅ {version_name} deletado!")
                            st.rerun()
        else:
            st.info("ℹ️ Nenhum snapshot salvo")
            
        st.markdown("---")
        st.subheader("📥 Exportar")
        
        # Botão de exportação
        txt_content = f"Relatório de Snapshots\nEmpreendimento: {selected_empreendimento}\nData: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        
        if empreendimento_snapshots:
            for version, data in empreendimento_snapshots.items():
                txt_content += f"--- {version} ---\n"
                df_version = pd.DataFrame(data['data'])
                txt_content += df_version.to_string(index=False) + "\n\n"
        else:
            txt_content += "Nenhum snapshot salvo."
        
        st.download_button(
            label="💾 Baixar Relatório",
            data=txt_content,
            file_name=f"snapshots_{selected_empreendimento}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
            mime="text/plain",
            use_container_width=True
        )

    # Layout principal
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Dados do projeto
        st.subheader("📊 Dados do Projeto")
        
        # Aplica a versão selecionada para visualização
        df_display = df_filtered.copy()
        
        if selected_version != "Real Atual (Comparar com P0)":
            # Aplica dados do snapshot selecionado
            version_data_list = empreendimento_snapshots[selected_version]['data']
            version_data = pd.DataFrame(version_data_list)
            
            version_prefix = selected_version.split('-')[0]
            col_inicio = f'{version_prefix}_Previsto_Inicio'
            col_fim = f'{version_prefix}_Previsto_Fim'
            
            # Merge com dados do snapshot
            df_display = df_display.merge(
                version_data[['ID_Tarefa', col_inicio, col_fim]],
                on='ID_Tarefa',
                how='left'
            )
            
            # Atualiza as colunas de previsão
            df_display['Previsto_Inicio'] = pd.to_datetime(df_display[col_inicio])
            df_display['Previsto_Fim'] = pd.to_datetime(df_display[col_fim])
        
        # Formata para exibição
        df_display_formatted = df_display[['Tarefa', 'Real_Inicio', 'Real_Fim', 'Previsto_Inicio', 'Previsto_Fim']].copy()
        for col in ['Real_Inicio', 'Real_Fim', 'Previsto_Inicio', 'Previsto_Fim']:
            if pd.api.types.is_datetime64_any_dtype(df_display_formatted[col]):
                df_display_formatted[col] = df_display_formatted[col].dt.strftime('%Y-%m-%d')
        
        st.dataframe(df_display_formatted, use_container_width=True)
        
        # Informação da versão
        if selected_version == "Real Atual (Comparar com P0)":
            st.info("📊 Comparando **Real Atual** com **P0 (Planejamento Original)**")
        else:
            st.info(f"📊 Comparando **Real Atual** com **{selected_version}**")
        
        # Menu de contexto
        st.markdown("---")
        st.subheader("🎯 Menu de Contexto")
        st.markdown("**Clique com o botão direito na área abaixo:**")
        
        # Componente do menu de contexto com formulário
        context_menu_html = create_context_menu_with_form(selected_empreendimento)
        html(context_menu_html, height=350)
    
    with col2:
        # Estatísticas e informações
        st.subheader("📈 Estatísticas")
        
        st.metric("Total de Tarefas", len(df_filtered))
        st.metric("Snapshots Salvos", len(empreendimento_snapshots))
        
        # Próximas ações sugeridas
        st.markdown("---")
        st.subheader("💡 Sugestões")
        
        if len(empreendimento_snapshots) == 0:
            st.info("Crie seu primeiro snapshot para começar a comparar versões!")
        else:
            st.success(f"Você tem {len(empreendimento_snapshots)} snapshot(s) para comparar")

if __name__ == "__main__":
    main()
