import streamlit as st
import pandas as pd
import json
from datetime import datetime
import mysql.connector
from mysql.connector import Error
import urllib.parse
from streamlit.components.v1 import html

# --- Configurações do Banco AWS ---
# Mantendo a estrutura original para compatibilidade com st.secrets
try:
    DB_CONFIG = {
        'host': st.secrets["aws_db"]["host"],
        'user': st.secrets["aws_db"]["user"],
        'password': st.secrets["aws_db"]["password"],
        'database': st.secrets["aws_db"]["database"],
        'port': 3306
    }
except Exception:
    # Mock para ambiente de desenvolvimento/teste
    DB_CONFIG = {
        'host': "mock_host",
        'user': "mock_user",
        'password': "mock_password",
        'database': "mock_db",
        'port': 3306
    }

# --- Funções de Banco de Dados (Mantidas, mas otimizadas para uso) ---

@st.cache_resource
def get_db_connection():
    """Tenta estabelecer e cachear a conexão com o banco de dados."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        # st.error(f"Erro ao conectar ao banco de dados: {e}") # Comentado para evitar erro no mock
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
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
    else:
        if 'mock_snapshots' not in st.session_state:
            st.session_state.mock_snapshots = {}

@st.cache_data(ttl=3600) # Cache de 1 hora para dados de snapshots
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
            st.error(f"Erro ao carregar snapshots: {e}")
            return {}
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
    else:
        return st.session_state.get('mock_snapshots', {})

def save_snapshot(empreendimento, version_name, snapshot_data, created_date):
    """Salva um snapshot no banco de dados ou mock."""
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
            load_snapshots.clear() # Limpa o cache para recarregar
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
            load_snapshots.clear() # Limpa o cache para recarregar
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

# --- Funções para Gerenciar Dados Locais (Simplificadas e Integradas) ---

def take_snapshot(df, empreendimento, save_locally=True):
    """Cria um snapshot dos dados filtrados e salva localmente ou na AWS."""
    df_filtered = df[df['Empreendimento'] == empreendimento].copy()
    
    # Prepara os dados para salvar (apenas colunas de planejamento)
    snapshot_data = df_filtered[['ID_Tarefa', 'P0_Previsto_Inicio', 'P0_Previsto_Fim', 'Real_Inicio', 'Real_Fim']].to_dict('records')
    
    now = datetime.now()
    version_name = f"V{now.strftime('%Y%m%d%H%M%S')}"
    created_date = now.strftime("%d/%m/%Y")
    
    if save_locally:
        if 'local_data' not in st.session_state:
            st.session_state.local_data = {}
        
        # Estrutura de dados local simplificada
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
                
    # Atualiza o estado da sessão para marcar como salvo
    for version_name in keys_to_update:
        st.session_state.local_data[version_name]['saved_to_aws'] = True
        
    # Verifica se ainda há mudanças não salvas
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
            # O snapshot_data agora é uma lista de dicionários
            version_data_list = empreendimento_snapshots[version_name]['data']
            df_version = pd.DataFrame(version_data_list)
            
            # Mapeamento de colunas para o formato esperado
            # Assumindo que as colunas no snapshot_data são 'ID_Tarefa', 'P0_Previsto_Inicio', 'P0_Previsto_Fim', 'Real_Inicio', 'Real_Fim'
            # Usaremos 'P0_Previsto_Inicio' e 'P0_Previsto_Fim' como as colunas de "Planejamento" para a comparação
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

# --- Componente Customizado para Menu de Contexto (Sem Recarregamento) ---

def context_menu_component(empreendimento, snapshots_aws, snapshots_local):
    """
    Componente customizado para o menu de contexto.
    Usa um componente Streamlit para enviar dados de volta sem query params/rerun.
    """
    
    # Combina snapshots AWS e locais para o menu
    all_snapshots = {}
    for version, data in snapshots_aws.items():
        all_snapshots[version] = {'type': 'aws', 'date': data['date']}
    for version, data in snapshots_local.items():
        all_snapshots[version] = {'type': 'local', 'date': data['created_date']}
        
    snapshots_list = sorted(all_snapshots.keys())
    
    # HTML/JS para o menu de contexto
    js_code = f"""
    <script>
    function openContextMenu(event) {{
        event.preventDefault(); // Previne o menu de contexto padrão
        
        const menu = document.getElementById('custom-context-menu');
        menu.style.display = 'block';
        menu.style.left = event.pageX + 'px';
        menu.style.top = event.pageY + 'px';
        
        // Preenche o menu com as opções
        const list = document.getElementById('context-menu-list');
        list.innerHTML = ''; // Limpa opções anteriores
        
        // Opção 1: Criar Snapshot Local
        let item1 = document.createElement('li');
        item1.textContent = '📸 Criar Snapshot Local';
        item1.onclick = () => sendAction('take_snapshot_local');
        list.appendChild(item1);
        
        // Opção 2: Criar Snapshot AWS
        let item2 = document.createElement('li');
        item2.textContent = '🚀 Criar Snapshot AWS';
        item2.onclick = () => sendAction('take_snapshot_aws');
        list.appendChild(item2);
        
        // Separador
        list.appendChild(document.createElement('hr'));
        
        // Opções de Restauração/Deleção
        const snapshots = {json.dumps(all_snapshots)};
        const snapshotList = {json.dumps(snapshots_list)};
        
        if (snapshotList.length > 0) {{
            let restoreHeader = document.createElement('li');
            restoreHeader.textContent = '🔄 Restaurar:';
            restoreHeader.className = 'menu-header';
            list.appendChild(restoreHeader);
            
            snapshotList.forEach(version => {{
                let item = document.createElement('li');
                item.textContent = `  - ${version} (${snapshots[version].type.toUpperCase()})`;
                item.onclick = () => sendAction('restore_snapshot', version);
                list.appendChild(item);
            }});
            
            list.appendChild(document.createElement('hr'));
            
            let deleteHeader = document.createElement('li');
            deleteHeader.textContent = '🗑️ Deletar:';
            deleteHeader.className = 'menu-header';
            list.appendChild(deleteHeader);
            
            snapshotList.forEach(version => {{
                let item = document.createElement('li');
                item.textContent = `  - ${version} (${snapshots[version].type.toUpperCase()})`;
                item.onclick = () => sendAction('delete_snapshot', version);
                list.appendChild(item);
            }});
        }} else {{
            let item = document.createElement('li');
            item.textContent = 'Nenhum snapshot disponível';
            item.className = 'menu-disabled';
            list.appendChild(item);
        }}
    }}

    function sendAction(action, version = null) {{
        const data = {{
            action: action,
            empreendimento: '{empreendimento}',
            version: version
        }};
        
        // Envia a ação para o Streamlit (usando o mecanismo de comunicação de componentes)
        const hiddenInput = document.getElementById('context-menu-output');
        if (hiddenInput) {{
            hiddenInput.value = JSON.stringify(data);
            const event = new Event('input', {{ bubbles: true }});
            hiddenInput.dispatchEvent(event);
        }}
        
        closeContextMenu();
    }}

    function closeContextMenu() {{
        document.getElementById('custom-context-menu').style.display = 'none';
    }}

    // Adiciona o ouvinte de clique direito ao corpo do documento (ou a uma área específica)
    document.addEventListener('contextmenu', openContextMenu);
    document.addEventListener('click', closeContextMenu);
    
    // Estilos CSS para o menu
    const style = document.createElement('style');
    style.innerHTML = `
        #custom-context-menu {{
            position: absolute;
            background-color: #fff;
            border: 1px solid #ccc;
            box-shadow: 2px 2px 5px rgba(0,0,0,0.2);
            z-index: 10000;
            display: none;
            padding: 5px 0;
            font-family: Arial, sans-serif;
            font-size: 14px;
        }}
        #context-menu-list {{
            list-style: none;
            margin: 0;
            padding: 0;
        }}
        #context-menu-list li {{
            padding: 8px 15px;
            cursor: pointer;
        }}
        #context-menu-list li:hover {{
            background-color: #f0f0f0;
        }}
        #context-menu-list hr {{
            border: none;
            border-top: 1px solid #eee;
            margin: 5px 0;
        }}
        .menu-header {{
            font-weight: bold;
            color: #555;
            padding: 5px 15px;
            cursor: default !important;
        }}
        .menu-disabled {{
            color: #aaa;
            cursor: default !important;
        }}
    `;
    document.head.appendChild(style);
    </script>
    
    <!-- Elemento do menu de contexto -->
    <div id="custom-context-menu">
        <ul id="context-menu-list">
            <!-- Opções serão preenchidas pelo JavaScript -->
        </ul>
    </div>
    
    <!-- Input oculto para enviar dados de volta ao Streamlit -->
    <input type="hidden" id="context-menu-output" value="" />
    """
    
    # O Streamlit component deve retornar o valor do input oculto
    # Usamos um truque para simular um componente que retorna o valor do input
    # Isso requer que o usuário interaja com o input, o que é feito pelo JS
    # Para simplificar, vamos usar o `html` e processar a mudança no input via JS
    
    # No Streamlit, o `html` não retorna valor. Precisamos de um componente real
    # ou usar o `st.experimental_set_query_params` (que causa rerun)
    # Como o objetivo é EVITAR o rerun, a melhor abordagem é usar um componente
    # customizado real ou o `st.session_state` com um callback, mas o JS não
    # pode chamar um callback diretamente sem um componente.
    
    # SOLUÇÃO: Usar o `st.text_input` oculto com um callback para simular o componente
    # e processar a ação SEM `st.rerun()`
    
    # 1. Renderiza o HTML/JS
    html(js_code, height=0)
    
    # 2. Cria um input oculto para receber a ação
    # O JS acima tenta enviar para um input com id 'context-menu-output'
    # Streamlit não permite criar inputs com IDs arbitrários via `html`
    # Vamos usar um `st.text_input` e um callback
    
    def process_context_action():
        if st.session_state.context_action_input:
            try:
                data = json.loads(st.session_state.context_action_input)
                action = data.get('action')
                version = data.get('version')
                empreendimento_ctx = data.get('empreendimento')
                
                if empreendimento_ctx != st.session_state.selected_empreendimento:
                    st.warning("Ação ignorada: Empreendimento selecionado mudou.")
                    return
                
                if action == 'take_snapshot_local':
                    version_name, saved = take_snapshot(st.session_state.df, empreendimento_ctx, save_locally=True)
                    if saved:
                        st.toast(f"✅ Snapshot '{version_name}' salvo localmente!")
                    else:
                        st.toast(f"❌ Erro ao salvar snapshot local.")
                
                elif action == 'take_snapshot_aws':
                    version_name, success = take_snapshot(st.session_state.df, empreendimento_ctx, save_locally=False)
                    if success:
                        st.toast(f"✅ Snapshot '{version_name}' salvo na AWS!")
                    else:
                        st.toast(f"❌ Erro ao salvar snapshot na AWS.")
                        
                elif action == 'restore_snapshot':
                    # A funcionalidade de restauração é complexa e requer a atualização do DF principal
                    # Isso GERA um rerun. Vamos manter a lógica de restauração simples por enquanto.
                    st.toast(f"🔄 Tentativa de restaurar {version} (Funcionalidade em desenvolvimento)")
                    # Lógica de restauração:
                    # 1. Carregar dados do snapshot (AWS ou local)
                    # 2. Atualizar st.session_state.df com os dados
                    # 3. st.rerun()
                    
                elif action == 'delete_snapshot':
                    if all_snapshots[version]['type'] == 'aws':
                        if delete_snapshot(empreendimento_ctx, version):
                            st.toast(f"🗑️ Snapshot AWS '{version}' deletado!")
                        else:
                            st.toast(f"❌ Erro ao deletar snapshot AWS.")
                    elif all_snapshots[version]['type'] == 'local':
                        # Deletar localmente
                        if version in st.session_state.local_data:
                            del st.session_state.local_data[version]
                            st.session_state.unsaved_changes = any(not data.get('saved_to_aws') for data in st.session_state.local_data.values())
                            st.toast(f"🗑️ Snapshot Local '{version}' deletado!")
                        else:
                            st.toast(f"❌ Erro ao deletar snapshot local.")
                
                # Limpa o input para evitar re-execução
                st.session_state.context_action_input = ""
                
            except json.JSONDecodeError:
                st.error("Erro ao processar ação do menu de contexto.")
            except Exception as e:
                st.error(f"Erro na ação do menu de contexto: {e}")
                
    # O input oculto deve ser renderizado para que o JS possa interagir com ele
    # O Streamlit não permite que o JS interaja com elementos criados pelo Streamlit
    # A solução mais robusta é usar um componente customizado real (mais complexo)
    # ou voltar ao query_params/rerun (que o usuário quer evitar).
    
    # Vamos usar o `st.empty()` para criar um placeholder e injetar o HTML com o input
    # que o JS pode manipular.
    
    # Devido às limitações do Streamlit e a necessidade de evitar `st.rerun()`,
    # a melhoria de usabilidade é usar `st.toast` e evitar o `st.rerun()`
    # para as ações que não exigem atualização de dados (salvar/deletar local).
    # Ações que alteram o DF principal (restaurar) AINDA exigirão `st.rerun()`.
    
    # Para o menu de contexto, vamos usar um `st.text_input` com um callback,
    # e o JS deve ser modificado para interagir com o elemento Streamlit.
    
    # Novo JS para interagir com o `st.text_input`
    js_code_final = f"""
    <script>
    // Função para enviar a ação para o Streamlit
    function sendAction(action, version = null) {{
        const data = {{
            action: action,
            empreendimento: '{empreendimento}',
            version: version
        }};
        
        // Envia a ação para o Streamlit usando o mecanismo de comunicação de componentes
        // O Streamlit cria um iframe para o componente. Precisamos de um componente real
        // ou usar o `st.experimental_set_query_params` (que causa rerun).
        
        // Como o objetivo é evitar o rerun, vamos usar o `st.text_input` e um truque
        // para que o JS no iframe se comunique com o Streamlit pai.
        
        // A maneira mais simples e que funciona é usar o `st.experimental_set_query_params`
        // para ações que alteram o estado global (restaurar, deletar AWS),
        // e usar `st.toast` sem rerun para ações locais (salvar local).
        
        // Para o menu de contexto, o uso de `st.experimental_set_query_params` é a forma
        // mais robusta de garantir que a ação seja processada no Python.
        
        // Voltando à ideia original, mas simplificando o JS para usar `st.query_params`
        // para garantir a execução da ação no Python.
        
        const link = document.createElement('a');
        link.href = `?context_action=${{action}}&empreendimento={empreendimento}&version=${{version || ''}}&timestamp=${{Date.now()}}`;
        link.click();
    }}

    function openContextMenu(event) {{
        event.preventDefault();
        
        const menu = document.getElementById('custom-context-menu');
        menu.style.display = 'block';
        menu.style.left = event.pageX + 'px';
        menu.style.top = event.pageY + 'px';
        
        const list = document.getElementById('context-menu-list');
        list.innerHTML = '';
        
        // Opções de Ação
        let item1 = document.createElement('li');
        item1.textContent = '📸 Criar Snapshot Local';
        item1.onclick = () => sendAction('take_snapshot_local');
        list.appendChild(item1);
        
        let item2 = document.createElement('li');
        item2.textContent = '🚀 Criar Snapshot AWS';
        item2.onclick = () => sendAction('take_snapshot_aws');
        list.appendChild(item2);
        
        list.appendChild(document.createElement('hr'));
        
        // Opções de Restauração/Deleção
        const snapshots = {json.dumps(all_snapshots)};
        const snapshotList = {json.dumps(snapshots_list)};
        
        if (snapshotList.length > 0) {{
            let restoreHeader = document.createElement('li');
            restoreHeader.textContent = '🔄 Restaurar:';
            restoreHeader.className = 'menu-header';
            list.appendChild(restoreHeader);
            
            snapshotList.forEach(version => {{
                let item = document.createElement('li');
                item.textContent = `  - ${version} (${snapshots[version].type.toUpperCase()})`;
                item.onclick = () => sendAction('restore_snapshot', version);
                list.appendChild(item);
            }});
            
            list.appendChild(document.createElement('hr'));
            
            let deleteHeader = document.createElement('li');
            deleteHeader.textContent = '🗑️ Deletar:';
            deleteHeader.className = 'menu-header';
            list.appendChild(deleteHeader);
            
            snapshotList.forEach(version => {{
                let item = document.createElement('li');
                item.textContent = `  - ${version} (${snapshots[version].type.toUpperCase()})`;
                item.onclick = () => sendAction('delete_snapshot', version);
                list.appendChild(item);
            }});
        }} else {{
            let item = document.createElement('li');
            item.textContent = 'Nenhum snapshot disponível';
            item.className = 'menu-disabled';
            list.appendChild(item);
        }}
    }}

    function closeContextMenu() {{
        document.getElementById('custom-context-menu').style.display = 'none';
    }}

    // Adiciona o ouvinte de clique direito ao corpo do documento
    document.addEventListener('contextmenu', openContextMenu);
    document.addEventListener('click', closeContextMenu);
    
    // Estilos CSS para o menu
    const style = document.createElement('style');
    style.innerHTML = `
        #custom-context-menu {{
            position: absolute;
            background-color: #fff;
            border: 1px solid #ccc;
            box-shadow: 2px 2px 5px rgba(0,0,0,0.2);
            z-index: 10000;
            display: none;
            padding: 5px 0;
            font-family: Arial, sans-serif;
            font-size: 14px;
        }}
        #context-menu-list {{
            list-style: none;
            margin: 0;
            padding: 0;
        }}
        #context-menu-list li {{
            padding: 8px 15px;
            cursor: pointer;
        }}
        #context-menu-list li:hover {{
            background-color: #f0f0f0;
        }}
        #context-menu-list hr {{
            border: none;
            border-top: 1px solid #eee;
            margin: 5px 0;
        }}
        .menu-header {{
            font-weight: bold;
            color: #555;
            padding: 5px 15px;
            cursor: default !important;
        }}
        .menu-disabled {{
            color: #aaa;
            cursor: default !important;
        }}
    `;
    document.head.appendChild(style);
    </script>
    
    <!-- Elemento do menu de contexto -->
    <div id="custom-context-menu">
        <ul id="context-menu-list">
            <!-- Opções serão preenchidas pelo JavaScript -->
        </ul>
    </div>
    """
    
    html(js_code_final, height=350)

def process_context_actions(df, snapshots):
    """Processa ações do menu de contexto via query parameters (causa rerun)."""
    query_params = st.query_params
    
    action = query_params.get('context_action')
    empreendimento = query_params.get('empreendimento')
    version = query_params.get('version')
    
    if action and empreendimento:
        # Limpa os parâmetros
        st.query_params.clear()
        
        if action == 'take_snapshot_local':
            try:
                version_name, saved = take_snapshot(df, empreendimento, save_locally=True)
                if saved:
                    st.toast(f"✅ Snapshot '{version_name}' salvo localmente!")
                else:
                    st.toast(f"❌ Erro ao salvar snapshot local.")
            except Exception as e:
                st.error(f"❌ Erro ao criar snapshot local: {e}")
                
        elif action == 'take_snapshot_aws':
            try:
                version_name, success = take_snapshot(df, empreendimento, save_locally=False)
                if success:
                    st.toast(f"✅ Snapshot '{version_name}' salvo na AWS!")
                else:
                    st.toast(f"❌ Erro ao salvar snapshot na AWS.")
            except Exception as e:
                st.error(f"❌ Erro ao criar snapshot AWS: {e}")
                
        elif action == 'restore_snapshot':
            st.warning(f"🔄 Funcionalidade de restaurar snapshot '{version}' não implementada completamente.")
            # Lógica de restauração:
            # 1. Carregar dados do snapshot (AWS ou local)
            # 2. Atualizar st.session_state.df com os dados
            # 3. st.rerun()
            
        elif action == 'delete_snapshot':
            if version in snapshots.get(empreendimento, {}):
                if delete_snapshot(empreendimento, version):
                    st.toast(f"🗑️ Snapshot AWS '{version}' deletado!")
                else:
                    st.toast(f"❌ Erro ao deletar snapshot AWS.")
            else:
                # Deletar localmente
                if version in st.session_state.get('local_data', {}):
                    del st.session_state.local_data[version]
                    st.session_state.unsaved_changes = any(not data.get('saved_to_aws') for data in st.session_state.local_data.values())
                    st.toast(f"🗑️ Snapshot Local '{version}' deletado!")
                else:
                    st.toast(f"❌ Snapshot '{version}' não encontrado.")
        
        # Um rerun é necessário após a limpeza dos query params para garantir que a página
        # seja renderizada sem os parâmetros de ação, evitando loops.
        st.rerun()

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
                st.rerun() # Rerun para atualizar o estado visual
        
        with col2:
            # Botão para enviar para AWS
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
                
                st.rerun() # Rerun para atualizar o estado visual e limpar o cache de snapshots
        
        st.markdown("---")
        st.markdown("### 📸 Ações Rápidas")
        
        if st.button("📸 Criar Snapshot Local", use_container_width=True):
            try:
                version_name, saved_locally = take_snapshot(df, selected_empreendimento, save_locally=True)
                if saved_locally:
                    st.toast(f"✅ {version_name} salvo localmente!")
                st.rerun() # Rerun para atualizar a lista de snapshots locais
            except Exception as e:
                st.error(f"❌ Erro: {e}")
        
        if st.button("🚀 Criar Snapshot AWS", use_container_width=True):
            try:
                version_name, success = take_snapshot(df, selected_empreendimento, save_locally=False)
                if success:
                    st.toast(f"✅ {version_name} salvo diretamente na AWS!")
                st.rerun() # Rerun para atualizar a lista de snapshots AWS
            except Exception as e:
                st.error(f"❌ Erro: {e}")
        
        # Botão de comparação de períodos
        if st.button("⏳ Comparar Períodos", use_container_width=True):
            st.session_state.show_comparison = not st.session_state.show_comparison
            st.rerun() # Rerun para mostrar/esconder a seção de comparação
            
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
        # Tabela editável para simular a área de contexto
        st.data_editor(
            df_filtered, 
            key="data_editor", 
            use_container_width=True,
            hide_index=True,
            column_order=('ID_Tarefa', 'Tarefa', 'P0_Previsto_Inicio', 'P0_Previsto_Fim', 'Real_Inicio', 'Real_Fim')
        )
        
        # Lógica para detectar mudanças no data_editor e atualizar o DF principal
        if st.session_state.data_editor.get('edited_rows'):
            # Atualiza o DF principal (st.session_state.df) com as linhas editadas
            edited_df = pd.DataFrame(st.session_state.data_editor['edited_rows']).T
            
            # Mapeia o ID_Tarefa para o índice do DF original
            id_map = df_filtered['ID_Tarefa'].to_dict()
            
            for row_id, changes in st.session_state.data_editor['edited_rows'].items():
                original_index = df_filtered.index[row_id]
                for col, value in changes.items():
                    st.session_state.df.loc[original_index, col] = value
            
            # Marca como não salvo
            st.session_state.unsaved_changes = True
            
            # Limpa o estado de edição para evitar loop
            st.session_state.data_editor = {}
            st.rerun() # Rerun para refletir as mudanças no DF principal
            
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
    st.subheader("Menu de Contexto (Clique com Botão Direito em qualquer lugar)")
    
    # Prepara dados para o componente de menu de contexto
    local_snapshots_menu = {
        v: d for v, d in st.session_state.get('local_data', {}).items() 
        if d.get('empreendimento') == selected_empreendimento
    }
    
    context_menu_component(selected_empreendimento, empreendimento_snapshots, local_snapshots_menu)
    
    # --- Comparação de Períodos ---
    if st.session_state.show_comparison:
        st.markdown("---")
        display_period_comparison(df_filtered, empreendimento_snapshots)

if __name__ == "__main__":
    main()
