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
    """
    Cria um novo snapshot (linha de base) para o empreendimento.
    As datas 'Real' atuais se tornam as novas datas 'Previstas' para a nova versão.
    """
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
    """
    Função mock para simular a criação do gráfico de Gantt.
    Retorna o HTML para a área do gráfico.
    """
    
    st.subheader("Gráfico de Gantt (Visualização Mock)")
    
    df_display = df[['Empreendimento', 'Tarefa', 'Real_Inicio', 'Real_Fim', 'Previsto_Inicio', 'Previsto_Fim']].copy()
    
    for col in ['Real_Inicio', 'Real_Fim', 'Previsto_Inicio', 'Previsto_Fim']:
        if pd.api.types.is_datetime64_any_dtype(df_display[col]):
            df_display[col] = df_display[col].dt.strftime('%Y-%m-%d')
        
    st.dataframe(df_display, use_container_width=True)
    
    return '<div id="gantt-chart-area" style="height: 400px; border: 1px solid #ccc; margin-top: 10px; display: flex; align-items: center; justify-content: center; background-color: #f9f9f9;">Clique com o botão direito nesta área para o menu de Snapshot.</div>'

# --- Funções para comunicação JS-Python corrigidas ---

def inject_js_context_menu(gantt_area_html, selected_empreendimento):
    """
    Injeta o HTML da área do gráfico, o CSS e o JavaScript para o menu circular.
    
    CORREÇÃO: Usando uma abordagem diferente para comunicação JS-Python
    """
    
    css_code = """
.context-menu {
    position: absolute;
    z-index: 1000;
    background-color: #fff;
    border: 1px solid #ccc;
    box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.2);
    border-radius: 4px;
    padding: 5px 0;
    display: none;
}

.menu-item {
    padding: 8px 12px;
    cursor: pointer;
    font-size: 14px;
    color: #333;
}

.menu-item:hover {
    background-color: #f0f0f0;
}
"""
    
    js_code = f"""
function injectCircularMenu(empreendimento) {{
    // Cria o menu de contexto
    let menu = document.getElementById('snapshot-context-menu');
    if (!menu) {{
        menu = document.createElement('div');
        menu.className = 'context-menu';
        menu.id = 'snapshot-context-menu';
        document.body.appendChild(menu);
    }}
    
    // Conteúdo do menu
    menu.innerHTML = `
        <div class="menu-item" data-action="take_snapshot">📸 Tirar Snapshot (Linha de Base)</div>
        <div class="menu-item" data-action="restore_snapshot">🔄 Restaurar Snapshot</div>
        <div class="menu-item" data-action="delete_snapshot">🗑️ Deletar Snapshot</div>
    `;

    // Manipulador de clique com o botão direito
    const ganttArea = document.getElementById('gantt-chart-area');
    if (ganttArea) {{
        ganttArea.oncontextmenu = function(e) {{
            e.preventDefault();
            
            // Posiciona o menu
            menu.style.left = e.pageX + 'px';
            menu.style.top = e.pageY + 'px';
            menu.style.display = 'block';
        }};
    }}

    // Manipulador de clique nos itens do menu
    menu.onclick = function(e) {{
        if (e.target.classList.contains('menu-item')) {{
            const action = e.target.getAttribute('data-action');
            handleMenuClick(action, empreendimento);
        }}
    }};

    // Fecha o menu ao clicar em qualquer lugar
    document.onclick = function(e) {{
        if (menu.style.display === 'block' && !menu.contains(e.target)) {{
            menu.style.display = 'none';
        }}
    }};
}}

// FUNÇÃO CORRIGIDA: Usando window.parent.postMessage para comunicação
function handleMenuClick(action, empreendimento) {{
    // Esconde o menu
    document.getElementById('snapshot-context-menu').style.display = 'none';
    
    // Envia a mensagem para o Streamlit
    window.parent.postMessage({{
        type: 'streamlit:setComponentValue',
        value: JSON.stringify({{
            action: action,
            empreendimento: empreendimento
        }})
    }}, '*');
    
    console.log('Ação enviada:', action, 'Empreendimento:', empreendimento);
}}

// Inicializa o menu quando a página carrega
document.addEventListener('DOMContentLoaded', function() {{
    injectCircularMenu("{selected_empreendimento}");
}});

// Também inicializa se o DOM já estiver carregado
if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', function() {{
        injectCircularMenu("{selected_empreendimento}");
    }});
}} else {{
    injectCircularMenu("{selected_empreendimento}");
}}
"""
    
    full_html_code = f"""
    <style>
        {css_code}
    </style>
    
    {gantt_area_html}
    
    <script>
        {js_code}
    </script>
    """
    
    html(full_html_code, height=450)

def inject_global_js_listener():
    """Injeta um listener global para capturar mensagens do menu de contexto"""
    js_listener = """
    <script>
    // Listener para mensagens do menu de contexto
    window.addEventListener('message', function(event) {
        // Verifica se a mensagem é do tipo que queremos
        if (event.data.type === 'streamlit:setComponentValue') {
            try {
                const data = JSON.parse(event.data.value);
                
                // Atualiza a URL com os parâmetros (abordagem alternativa)
                const url = new URL(window.location);
                url.searchParams.set('snapshot_action', data.action);
                url.searchParams.set('snapshot_empreendimento', data.empreendimento);
                
                window.history.replaceState(null, '', url.toString());
                
                // Dispara um evento para o Streamlit saber que precisa atualizar
                window.parent.postMessage({
                    type: 'streamlit:triggerRerun',
                    data: data
                }, '*');
            } catch (e) {
                console.error('Erro ao processar mensagem:', e);
            }
        }
    });
    </script>
    """
    html(js_listener)

def handle_js_messages():
    """Processa mensagens do JavaScript via st.query_params"""
    query_params = st.query_params
    
    action = query_params.get('snapshot_action')
    empreendimento = query_params.get('snapshot_empreendimento')
    
    if action and empreendimento:
        st.query_params.clear()
        
        st.session_state.snapshot_action_data = {
            "action": action,
            "empreendimento": empreendimento
        }
        st.rerun()

def display_period_comparison(df_filtered, empreendimento_snapshots):
    """
    Exibe a comparação de período entre duas linhas de base selecionadas.
    """
    st.subheader(f"⏳ Visualização de Período entre Linhas de Base para {df_filtered['Empreendimento'].iloc[0]}")
    
    version_options = ["P0 (Planejamento Original)"]
    version_options.extend(sorted(empreendimento_snapshots.keys()))
    
    col1, col2 = st.columns(2)
    
    with col1:
        version_a = st.selectbox("Selecione a Linha de Base A", version_options, index=0, key="version_a")
    with col2:
        default_index_b = 1 if len(version_options) > 1 else 0
        version_b = st.selectbox("Selecione a Linha de Base B", version_options, index=default_index_b, key="version_b")
        
    if version_a == version_b:
        st.warning("Selecione duas linhas de base diferentes para comparação.")
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
    
    df_merged['Diferenca_Duracao (dias)'] = df_merged['Duracao_B'] - df_merged['Duracao_A']
    
    df_merged['Desvio_Inicio (dias)'] = (df_merged['Inicio_B'] - df_merged['Inicio_A']).dt.days
    df_merged['Desvio_Fim (dias)'] = (df_merged['Fim_B'] - df_merged['Fim_A']).dt.days
    
    df_context = df_filtered[['ID_Tarefa', 'Tarefa']].drop_duplicates()
    df_final = df_context.merge(df_merged, on='ID_Tarefa')
    
    df_display = df_final[[
        'Tarefa',
        'Inicio_A', 'Fim_A', 'Duracao_A',
        'Inicio_B', 'Fim_B', 'Duracao_B',
        'Diferenca_Duracao (dias)',
        'Desvio_Inicio (dias)',
        'Desvio_Fim (dias)'
    ]].copy()
    
    df_display.columns = [
        'Tarefa',
        f'Início ({version_a})', f'Fim ({version_a})', f'Duração ({version_a})',
        f'Início ({version_b})', f'Fim ({version_b})', f'Duração ({version_b})',
        'Diferença Duração (dias)',
        'Desvio Início (dias)',
        'Desvio Fim (dias)'
    ]
    
    st.markdown(f"**Comparação Detalhada: {version_b} vs {version_a}**")
    st.dataframe(df_display, use_container_width=True)
    
    st.markdown("---")
    st.markdown("**Resumo da Comparação**")
    
    total_diff = df_final['Diferenca_Duracao (dias)'].sum()
    
    if total_diff > 0:
        st.error(f"O planejamento **{version_b}** é **{total_diff} dias** mais longo que **{version_a}** (soma das diferenças de duração das tarefas).")
    elif total_diff < 0:
        st.success(f"O planejamento **{version_b}** é **{-total_diff} dias** mais curto que **{version_a}** (soma das diferenças de duração das tarefas).")
    else:
        st.info("A duração total das tarefas é a mesma em ambos os planejamentos.")
        
    st.markdown("---")
    st.markdown("Legenda:")
    st.markdown("- **Diferença Duração (dias)**: Duração B - Duração A. Positivo significa que a tarefa ficou mais longa em B.")
    st.markdown("- **Desvio Início/Fim (dias)**: Data B - Data A. Positivo significa que a tarefa começou/terminou mais tarde em B.")

# --- Aplicação Principal Streamlit ---

def main():
    st.set_page_config(layout="wide", page_title="Gantt Chart Baseline/Snapshot - AWS")
    st.title("📊 Gráfico de Gantt com Versionamento de Planejamento - AWS MySQL")

    create_snapshots_table()

    # 1. Processa mensagens do JavaScript primeiro
    handle_js_messages()

    # 2. Lógica de Execução de Ação do Menu de Contexto
    action_data = st.session_state.get("snapshot_action_data")

    if action_data:
        del st.session_state.snapshot_action_data
        
        action = action_data.get("action")
        empreendimento_alvo = action_data.get("empreendimento")
        
        df = create_mock_dataframe()
        
        if action == 'take_snapshot':
            try:
                version_name = take_snapshot(df, empreendimento_alvo)
                st.success(f"✅ Snapshot '{version_name}' criado com sucesso para o empreendimento '{empreendimento_alvo}'!")
            except Exception as e:
                st.error(f"❌ Erro ao criar snapshot: {e}")
                
        elif action == 'restore_snapshot':
            st.warning(f"⚠️ Ação 'Restaurar Snapshot' para '{empreendimento_alvo}' não implementada.")
            
        elif action == 'delete_snapshot':
            st.warning(f"⚠️ Ação 'Deletar Snapshot' para '{empreendimento_alvo}' não implementada via menu de contexto. Use a barra lateral.")
            
        st.rerun()
        return

    query_params = st.query_params
    take_snapshot_param = query_params.get('take_snapshot')
    view_period_param = query_params.get('view_period')
    empreendimento_param = query_params.get('empreendimento')
    
    if 'df' not in st.session_state:
        st.session_state.df = create_mock_dataframe()
    
    df = st.session_state.df
    snapshots = load_snapshots()
    
    empreendimentos = df['Empreendimento'].unique().tolist()
    selected_empreendimento = st.sidebar.selectbox("🏢 Selecione o Empreendimento", empreendimentos)
    
    df_filtered = df[df['Empreendimento'] == selected_empreendimento].copy()

    if take_snapshot_param == 'true' and empreendimento_param:
        try:
            selected_empreendimento_url = urllib.parse.unquote(empreendimento_param)
            
            if selected_empreendimento_url == selected_empreendimento:
                new_version_name = take_snapshot(df, selected_empreendimento)
                st.query_params.clear()
                st.success(f"✅ Snapshot '{new_version_name}' criado com sucesso no banco AWS!")
                st.rerun()
            else:
                st.error("Erro: Empreendimento na URL não corresponde ao selecionado.")
                st.query_params.clear()
                st.rerun()
            
        except Exception as e:
            st.error(f"❌ Erro ao criar snapshot: {e}")
            st.query_params.clear()
            st.rerun()
            
    if view_period_param == 'true' and empreendimento_param:
        st.query_params.clear()
        st.session_state.show_period_comparison = True
        st.rerun()
        
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📸 Gerenciar Snapshots")
    
    if st.sidebar.button("📸 Fotografar Cenário Real como Previsto", key="manual_snapshot_trigger", use_container_width=True):
        try:
            new_version_name = take_snapshot(df, selected_empreendimento)
            st.success(f"✅ Snapshot '{new_version_name}' criado com sucesso no banco AWS!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Erro ao criar snapshot: {e}")
    
    if st.sidebar.button("⏳ Visualizar Período entre Linhas de Base", key="manual_view_period_trigger", use_container_width=True):
        st.session_state.show_period_comparison = not st.session_state.get('show_period_comparison', False)
        st.rerun()
        
    if st.session_state.get('show_period_comparison', False):
        empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
        display_period_comparison(df_filtered, empreendimento_snapshots)
        
        st.markdown("---")
        st.subheader("Visualização do Gráfico de Gantt")
    
    empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
    version_options = ["Real Atual (Comparar com P0)"]
    version_options.extend(sorted(empreendimento_snapshots.keys()))
    
    selected_version = st.sidebar.selectbox(
        "Selecione a Versão de Planejamento (Baseline) para Comparação",
        version_options,
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
    
    inject_global_js_listener()
    
    gantt_area_html = create_gantt_chart(df_filtered)
    
    inject_js_context_menu(gantt_area_html, selected_empreendimento)
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 💾 Snapshots Salvos")
    
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
        
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📥 Exportar Dados")
    
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
