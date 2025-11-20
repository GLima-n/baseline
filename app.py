import streamlit as st
import pandas as pd
import json
from datetime import datetime
import mysql.connector
from mysql.connector import Error
import urllib.parse
from streamlit.components.v1 import html

# --- Configurações do Banco AWS ---
# Inicializa DB_CONFIG como None.
DB_CONFIG = None
DB_CONNECTION_STATUS = "SUCCESS"

try:
    # Tenta carregar as configurações reais do Streamlit secrets
    DB_CONFIG = {
        'host': st.secrets["aws_db"]["host"],
        'user': st.secrets["aws_db"]["user"],
        'password': st.secrets["aws_db"]["password"],
        'database': st.secrets["aws_db"]["database"],
        'port': 3306
    }
except Exception as e:
    # Se falhar (ex: NameError ou KeyError), define o status como falha
    DB_CONNECTION_STATUS = f"FAILURE: Não foi possível carregar as credenciais do banco de dados (st.secrets). Usando dados de exemplo. Erro: {e}"
    st.warning(DB_CONNECTION_STATUS)


# --- Funções de Banco de Dados ---

def get_db_connection():
    """Tenta estabelecer uma conexão com o banco de dados. Retorna conn ou None em caso de falha."""
    if DB_CONFIG is None:
        return None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        st.error(f"Erro de conexão com o banco de dados: {e}. Usando dados de exemplo.")
        return None

def create_snapshots_table():
    """Cria a tabela de snapshots se não existir"""
    conn = get_db_connection()
    if conn is None:
        return
        
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

def load_snapshots():
    """Carrega todos os snapshots do banco AWS ou retorna dados de exemplo."""
    conn = get_db_connection()
    
    if conn is None:
        # Retorna dados de exemplo (mock) se a conexão falhar
        return {
            'Torre Alpha': {
                'P0-(20/11/2025)': {
                    "date": "20/11/2025",
                    "data": [
                        {'ID_Tarefa': 101, 'P0_Previsto_Inicio': '2025-01-05', 'P0_Previsto_Fim': '2025-02-05'},
                        {'ID_Tarefa': 102, 'P0_Previsto_Inicio': '2025-02-20', 'P0_Previsto_Fim': '2025-04-20'},
                    ]
                }
            },
            'Residencial Beta': {},
            'Comercial Gamma': {}
        }
        
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
            
            # Converte JSON string para dict
            snapshot_data = json.loads(row['snapshot_data'])
            snapshots[empreendimento][version_name] = {
                "date": row['created_date'],
                "data": snapshot_data
            }
            
    except Error as e:
        st.error(f"Erro ao carregar snapshots do banco: {e}. Usando dados de exemplo.")
        # Retorna dados de exemplo em caso de erro de consulta
        return {
            'Torre Alpha': {
                'P0-(20/11/2025)': {
                    "date": "20/11/2025",
                    "data": [
                        {'ID_Tarefa': 101, 'P0_Previsto_Inicio': '2025-01-05', 'P0_Previsto_Fim': '2025-02-05'},
                        {'ID_Tarefa': 102, 'P0_Previsto_Inicio': '2025-02-20', 'P0_Previsto_Fim': '2025-04-20'},
                    ]
                }
            },
            'Residencial Beta': {},
            'Comercial Gamma': {}
        }
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
    
    return snapshots

def save_snapshot(empreendimento, version_name, snapshot_data, created_date):
    """Salva um novo snapshot no banco AWS. Retorna False se a conexão falhar."""
    conn = get_db_connection()
    if conn is None:
        st.warning("Não foi possível salvar o snapshot: Conexão com o banco de dados indisponível.")
        return False
        
    try:
        cursor = conn.cursor()
        
        # Converte os dados para JSON string
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
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def delete_snapshot(empreendimento, version_name):
    """Deleta um snapshot específico. Retorna False se a conexão falhar."""
    conn = get_db_connection()
    if conn is None:
        st.warning("Não foi possível deletar o snapshot: Conexão com o banco de dados indisponível.")
        return False
        
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
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

# --- Função para criar DataFrame de exemplo ---

def create_mock_dataframe():
    """Cria um DataFrame de exemplo mais abrangente para simular os dados do Gantt."""
    data = {
        'ID_Tarefa': [101, 102, 103, 201, 202, 203, 301, 302, 303, 304],
        'Empreendimento': [
            'Torre Alpha', 'Torre Alpha', 'Torre Alpha', 
            'Residencial Beta', 'Residencial Beta', 'Residencial Beta', 
            'Comercial Gamma', 'Comercial Gamma', 'Comercial Gamma', 'Comercial Gamma'
        ],
        'Tarefa': [
            'Fundação', 'Estrutura', 'Acabamento', 
            'Terraplanagem', 'Alvenaria', 'Instalações', 
            'Design', 'Aprovação', 'Construção', 'Entrega'
        ],
        # Datas Reais (Atual) - Simulam o progresso atual
        'Real_Inicio': [
            pd.to_datetime('2025-01-01'), pd.to_datetime('2025-02-15'), pd.to_datetime('2025-05-01'), 
            pd.to_datetime('2025-03-10'), pd.to_datetime('2025-04-05'), pd.to_datetime('2025-06-20'), 
            pd.to_datetime('2025-01-20'), pd.to_datetime('2025-02-25'), pd.to_datetime('2025-04-15'), pd.to_datetime('2025-07-01')
        ],
        'Real_Fim': [
            pd.to_datetime('2025-02-10'), pd.to_datetime('2025-04-25'), pd.to_datetime('2025-07-30'), 
            pd.to_datetime('2025-04-01'), pd.to_datetime('2025-06-15'), pd.to_datetime('2025-08-10'), 
            pd.to_datetime('2025-02-20'), pd.to_datetime('2025-04-10'), pd.to_datetime('2025-06-25'), pd.to_datetime('2025-07-15')
        ],
        # Datas Previstas (Inicial - P0) - Simulam o planejamento original
        'P0_Previsto_Inicio': [
            pd.to_datetime('2025-01-05'), pd.to_datetime('2025-02-20'), pd.to_datetime('2025-04-15'), 
            pd.to_datetime('2025-03-01'), pd.to_datetime('2025-04-10'), pd.to_datetime('2025-06-01'), 
            pd.to_datetime('2025-01-15'), pd.to_datetime('2025-03-01'), pd.to_datetime('2025-04-01'), pd.to_datetime('2025-06-30')
        ],
        'P0_Previsto_Fim': [
            pd.to_datetime('2025-02-05'), pd.to_datetime('2025-04-20'), pd.to_datetime('2025-07-15'), 
            pd.to_datetime('2025-03-25'), pd.to_datetime('2025-06-05'), pd.to_datetime('2025-07-30'), 
            pd.to_datetime('2025-02-15'), pd.to_datetime('2025-03-30'), pd.to_datetime('2025-06-20'), pd.to_datetime('2025-07-10')
        ],
    }
    df = pd.DataFrame(data)
    
    # Inicializa as colunas de planejamento atuais com P0
    df['Previsto_Inicio'] = df['P0_Previsto_Inicio']
    df['Previsto_Fim'] = df['P0_Previsto_Fim']
    
    return df

# --- Lógica de Snapshot (Backend) ---

def take_snapshot(df, empreendimento):
    """
    Cria um novo snapshot (linha de base) para o empreendimento.
    As datas 'Real' atuais se tornam as novas datas 'Previstas' para a nova versão.
    """
    # Filtra o DataFrame pelo empreendimento
    df_empreendimento = df[df['Empreendimento'] == empreendimento].copy()
    
    # Determina o nome da nova versão
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
    
    # Cria o nome da nova versão (Pn)
    version_prefix = f"P{next_n}"
    current_date_str = datetime.now().strftime("%d/%m/%Y")
    version_name = f"{version_prefix}-({current_date_str})"
    
    # Prepara os dados do snapshot
    df_snapshot = df_empreendimento[['ID_Tarefa', 'Real_Inicio', 'Real_Fim']].copy()
    df_snapshot['Real_Inicio'] = df_snapshot['Real_Inicio'].dt.strftime('%Y-%m-%d')
    df_snapshot['Real_Fim'] = df_snapshot['Real_Fim'].dt.strftime('%Y-%m-%d')
    
    # Converte para lista de dicionários
    snapshot_data = df_snapshot.rename(
        columns={'Real_Inicio': f'{version_prefix}_Previsto_Inicio', 'Real_Fim': f'{version_prefix}_Previsto_Fim'}
    ).to_dict('records')

    # Salva no banco AWS
    success = save_snapshot(empreendimento, version_name, snapshot_data, current_date_str)
    
    if success:
        return version_name
    else:
        # Se falhar ao salvar, ainda retorna o nome da versão, mas a função chamadora deve lidar com o False
        raise Exception("Falha ao salvar snapshot no banco de dados (Conexão indisponível ou erro de DB)")

# --- Geração do Gráfico de Gantt (Mock) ---

def create_gantt_chart(df):
    """
    Função mock para simular a criação do gráfico de Gantt.
    Retorna o HTML para a área do gráfico.
    """
    
    # Usando st.dataframe como um placeholder visual para o gráfico de Gantt
    st.subheader("Gráfico de Gantt (Visualização Mock)")
    
    # Prepara os dados para exibição no mock
    df_display = df[['Empreendimento', 'Tarefa', 'Real_Inicio', 'Real_Fim', 'Previsto_Inicio', 'Previsto_Fim']].copy()
    
    # Formata as datas para melhor visualização
    for col in ['Real_Inicio', 'Real_Fim', 'Previsto_Inicio', 'Previsto_Fim']:
        df_display[col] = df_display[col].dt.strftime('%Y-%m-%d')
        
    st.dataframe(df_display, use_container_width=True)
    
    # Retorna o HTML da área do gráfico para o JS
    # A altura foi ajustada para garantir que o menu de contexto não fique fora do iframe.
    return '<div id="gantt-chart-area" style="height: 300px; border: 1px solid #ccc; margin-top: 10px; display: flex; align-items: center; justify-content: center; background-color: #f9f9f9;">Clique com o botão direito nesta área para o menu de Snapshot.</div>'

# --- Lógica de Interface (Frontend) ---

def inject_js_context_menu(gantt_area_html, selected_empreendimento):
    """
    Injeta o HTML da área do gráfico e o JavaScript para o menu de contexto.
    Usa o mecanismo original de recarregamento de página, mas com correção de posicionamento.
    """
    
    # Codifica o empreendimento para URL
    encoded_empreendimento = urllib.parse.quote(selected_empreendimento)
    
    # O JavaScript injetado para criar o menu de contexto
    js_code = f"""
    <script>
    function createSnapshot() {{
        // Navega para a mesma URL mas com parâmetros que indicam para criar snapshot
        const currentUrl = window.location.href.split('?')[0];
        const newUrl = currentUrl + '?take_snapshot=true&empreendimento={encoded_empreendimento}&t=' + Date.now();
        window.location.href = newUrl;
    }}

    const ganttArea = document.getElementById('gantt-chart-area');
    
    if (ganttArea) {{
        ganttArea.addEventListener('contextmenu', function(e) {{
            e.preventDefault(); // Previne o menu de contexto padrão do navegador
            
            // Remove menu existente se houver
            const existingMenu = document.getElementById('custom-context-menu');
            if (existingMenu) {{
                existingMenu.remove();
            }}
            
            // Cria o menu de contexto customizado
            const contextMenu = document.createElement('div');
            contextMenu.id = 'custom-context-menu';
            
            contextMenu.style.position = 'absolute';
            contextMenu.style.backgroundColor = 'white';
            contextMenu.style.border = '1px solid #ccc';
            contextMenu.style.boxShadow = '2px 2px 5px rgba(0,0,0,0.2)';
            contextMenu.style.zIndex = '1000';
            contextMenu.style.padding = '5px 0';
            
            // CORREÇÃO: Usar e.offsetX e e.offsetY (relativo ao elemento) e somar com a posição do elemento
            // para posicionar o menu corretamente em relação ao documento do iframe.
            const rect = ganttArea.getBoundingClientRect();
            contextMenu.style.left = (e.clientX - rect.left) + 'px';
            contextMenu.style.top = (e.clientY - rect.top) + 'px';
            
            // O menu deve ser anexado ao elemento que contém o gráfico, para que o posicionamento
            // 'absolute' funcione corretamente dentro do iframe.
            ganttArea.appendChild(contextMenu);
            
            // Item do menu: Criar Snapshot
            const snapshotItem = document.createElement('div');
            snapshotItem.textContent = 'Criar Snapshot (Nova Linha de Base)';
            snapshotItem.style.padding = '5px 15px';
            snapshotItem.style.cursor = 'pointer';
            snapshotItem.onmouseover = function() {{ this.style.backgroundColor = '#f0f0f0'; }};
            snapshotItem.onmouseout = function() {{ this.style.backgroundColor = 'white'; }};
            snapshotItem.onclick = function() {{
                createSnapshot();
                contextMenu.remove();
            }};
            
            contextMenu.appendChild(snapshotItem);
            
            // Fecha o menu ao clicar em qualquer lugar fora dele
            function closeMenu(event) {{
                // Verifica se o clique foi fora do menu de contexto
                if (event.target.id !== 'custom-context-menu' && !contextMenu.contains(event.target)) {{
                    contextMenu.remove();
                    document.removeEventListener('click', closeMenu);
                }}
            }}
            // Adiciona um pequeno atraso para evitar que o clique que abriu o menu o feche imediatamente
            setTimeout(() => {{
                document.addEventListener('click', closeMenu);
            }}, 100);
        }});
    }}
    </script>
    """
    
    # Combina o HTML da área do gráfico com o JavaScript
    full_html = gantt_area_html + js_code
    
    # Injeta o HTML no Streamlit
    html(full_html, height=350) # Altura ajustada para 350px

# --- Lógica Principal do Streamlit ---

def main():
    st.set_page_config(layout="wide", page_title="Gerenciamento de Linhas de Base")
    st.title("Gerenciamento de Linhas de Base do Cronograma")
    
    # 1. Inicialização do DataFrame e da Tabela
    if 'df' not in st.session_state:
        st.session_state.df = create_mock_dataframe()
    
    # create_snapshots_table() # Tenta criar a tabela se a conexão estiver OK
    
    # 2. Carregar Snapshots
    snapshots = load_snapshots()
    
    # 3. Seleção de Empreendimento
    empreendimentos = st.session_state.df['Empreendimento'].unique().tolist()
    selected_empreendimento = st.selectbox("Selecione o Empreendimento:", empreendimentos)
    
    # 4. Filtrar DataFrame
    df_filtered = st.session_state.df[st.session_state.df['Empreendimento'] == selected_empreendimento]
    
    # 5. Processar Ação de Snapshot (Callback do JS - Mecanismo Original)
    query_params = st.query_params
    
    if 'take_snapshot' in query_params and query_params['take_snapshot'] == 'true':
        empreendimento_param = query_params.get('empreendimento', [None])[0]
        
        if empreendimento_param:
            # Decodifica o nome do empreendimento
            decoded_empreendimento = urllib.parse.unquote(empreendimento_param)
            
            # Garante que a ação é para o empreendimento selecionado
            if decoded_empreendimento == selected_empreendimento:
                try:
                    new_version_name = take_snapshot(st.session_state.df, decoded_empreendimento)
                    st.success(f"Nova Linha de Base '{new_version_name}' criada com sucesso para {decoded_empreendimento}!")
                    
                    # Limpa os parâmetros da URL para evitar repetição da ação
                    # st.query_params.clear() # Removido para evitar erro de rerun no sandbox
                    
                except Exception as e:
                    st.error(f"Erro ao criar snapshot: {e}")
                    # st.query_params.clear() # Removido para evitar erro de rerun no sandbox
            else:
                # Caso o parâmetro não bata com o selecionado (pode acontecer em recargas)
                st.warning("Ação de snapshot ignorada: Empreendimento selecionado não corresponde ao parâmetro da URL.")
                # st.query_params.clear() # Removido para evitar erro de rerun no sandbox
        else:
            st.error("Erro: Parâmetro 'empreendimento' não encontrado na URL.")
            # st.query_params.clear() # Removido para evitar erro de rerun no sandbox

    # 6. Exibir Gráfico de Gantt (Mock)
    gantt_html = create_gantt_chart(df_filtered)
    
    # 7. Injetar Menu de Contexto
    inject_js_context_menu(gantt_html, selected_empreendimento)
    
    # 8. Exibir Snapshots Existentes
    st.subheader("Linhas de Base Existentes")
    
    if selected_empreendimento in snapshots:
        st.json(snapshots[selected_empreendimento])
    else:
        st.info(f"Nenhuma linha de base encontrada para {selected_empreendimento}.")

if __name__ == "__main__":
    main()
