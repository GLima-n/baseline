import streamlit as st
import pandas as pd
import json
from datetime import datetime
import mysql.connector
from mysql.connector import Error
import urllib.parse
from streamlit.components.v1 import html

# --- Configurações do Banco AWS ---
DB_CONFIG = {
    'host': st.secrets["aws_db"]["host"],
    'user': st.secrets["aws_db"]["user"],
    'password': st.secrets["aws_db"]["password"],
    'database': st.secrets["aws_db"]["database"],
    'port': 3306
}

# --- Funções de Banco de Dados ---

def create_snapshots_table():
    """Cria a tabela de snapshots se não existir"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
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

def load_snapshots():
    """Carrega todos os snapshots do banco AWS"""
    snapshots = {}
    
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
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
        st.error(f"Erro ao carregar snapshots: {e}")
        return {}
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()
    
    return snapshots

def save_snapshot(empreendimento, version_name, snapshot_data, created_date):
    """Salva um novo snapshot no banco AWS"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
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
        if conn.is_connected():
            cursor.close()
            conn.close()

def delete_snapshot(empreendimento, version_name):
    """Deleta um snapshot específico"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
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

# --- Função para criar DataFrame de exemplo ---

def create_mock_dataframe():
    """Cria um DataFrame de exemplo para simular os dados do Gantt."""
    data = {
        'ID_Tarefa': [1, 2, 3, 4, 5, 6],
        'Empreendimento': ['Projeto A', 'Projeto A', 'Projeto B', 'Projeto B', 'Projeto A', 'Projeto B'],
        'Tarefa': ['Fase 1', 'Fase 2', 'Design', 'Implementação', 'Teste', 'Deploy'],
        # Datas Reais (Atual) - Simulam o progresso atual
        'Real_Inicio': [pd.to_datetime('2025-10-01'), pd.to_datetime('2025-10-15'), pd.to_datetime('2025-11-01'), pd.to_datetime('2025-11-10'), pd.to_datetime('2025-10-26'), pd.to_datetime('2025-11-21')],
        'Real_Fim': [pd.to_datetime('2025-10-10'), pd.to_datetime('2025-10-25'), pd.to_datetime('2025-11-05'), pd.to_datetime('2025-11-20'), pd.to_datetime('2025-11-05'), pd.to_datetime('2025-11-25')],
        # Datas Previstas (Inicial - P0) - Simulam o planejamento original
        'P0_Previsto_Inicio': [pd.to_datetime('2025-09-25'), pd.to_datetime('2025-10-12'), pd.to_datetime('2025-10-28'), pd.to_datetime('2025-11-08'), pd.to_datetime('2025-10-20'), pd.to_datetime('2025-11-18')],
        'P0_Previsto_Fim': [pd.to_datetime('2025-10-05'), pd.to_datetime('2025-10-20'), pd.to_datetime('2025-11-03'), pd.to_datetime('2025-11-15'), pd.to_datetime('2025-10-30'), pd.to_datetime('2025-11-22')],
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
        raise Exception("Falha ao salvar snapshot no banco de dados")

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
    return '<div id="gantt-chart-area" style="height: 400px; border: 1px solid #ccc; margin-top: 10px; display: flex; align-items: center; justify-content: center; background-color: #f9f9f9;">Clique com o botão direito nesta área para o menu de Snapshot.</div>'

# --- Lógica de Interface (Frontend) ---

def inject_js_context_menu(gantt_area_html, selected_empreendimento):
    """
    Injeta o HTML da área do gráfico e o JavaScript para o menu de contexto.
    Usa uma abordagem com navigation para acionar o callback no Streamlit.
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
            contextMenu.style.borderRadius = '4px';
            contextMenu.style.padding = '8px 0';
            contextMenu.style.zIndex = '10000';
            contextMenu.style.boxShadow = '2px 2px 10px rgba(0,0,0,0.2)';
            contextMenu.style.fontFamily = 'Arial, sans-serif';
            contextMenu.style.fontSize = '14px';
            contextMenu.style.minWidth = '250px';
            
            contextMenu.innerHTML = `
                <div style="padding: 8px 16px; cursor: pointer; transition: background-color 0.2s;" 
                     onmouseover="this.style.backgroundColor='#f0f0f0'" 
                     onmouseout="this.style.backgroundColor='transparent'"
                     onclick="createSnapshot()">
                    📸 Fotografar Cenário Real como Previsto
                </div>
            `;
            
            document.body.appendChild(contextMenu);
            
            // Posiciona o menu próximo ao cursor
            const x = e.pageX;
            const y = e.pageY;
            const menuWidth = contextMenu.offsetWidth;
            const menuHeight = contextMenu.offsetHeight;
            const windowWidth = window.innerWidth;
            const windowHeight = window.innerHeight;
            
            // Ajusta a posição se o menu ultrapassar a borda da janela
            const adjustedX = x + menuWidth > windowWidth ? x - menuWidth : x;
            const adjustedY = y + menuHeight > windowHeight ? y - menuHeight : y;
            
            contextMenu.style.left = adjustedX + 'px';
            contextMenu.style.top = adjustedY + 'px';
            
            // Fecha o menu quando clicar em qualquer lugar
            function closeMenu(e) {{
                if (!contextMenu.contains(e.target)) {{
                    contextMenu.remove();
                    document.removeEventListener('click', closeMenu);
                }}
            }}
            
            // Aguarda um frame antes de adicionar o event listener para evitar fechar imediatamente
            setTimeout(() => {{
                document.addEventListener('click', closeMenu);
            }}, 0);
        }});
    }}
    </script>
    """
    
    # Injeta o HTML da área do gráfico e o script JS
    html(gantt_area_html + js_code, height=450)

# --- Aplicação Principal Streamlit ---

def main():
    st.set_page_config(layout="wide", page_title="Gantt Chart Baseline/Snapshot - AWS")
    st.title("📊 Gráfico de Gantt com Versionamento de Planejamento - AWS MySQL")

    # Inicializa a tabela no banco
    create_snapshots_table()

    # 1. Verifica se há parâmetros de snapshot na URL
    query_params = st.experimental_get_query_params()
    take_snapshot_param = query_params.get('take_snapshot', [''])[0]
    empreendimento_param = query_params.get('empreendimento', [''])[0]
    
    # 2. Processa o snapshot se solicitado via URL
    if take_snapshot_param == 'true' and empreendimento_param:
        try:
            # Decodifica o empreendimento
            selected_empreendimento = urllib.parse.unquote(empreendimento_param)
            
            # Carrega os dados
            if 'df' not in st.session_state:
                st.session_state.df = create_mock_dataframe()
            
            df = st.session_state.df
            
            # Cria o snapshot
            new_version_name = take_snapshot(df, selected_empreendimento)
            
            # Limpa os parâmetros da URL
            st.experimental_set_query_params()
            
            # Mostra mensagem de sucesso
            st.success(f"✅ Snapshot '{new_version_name}' criado com sucesso no banco AWS!")
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Erro ao criar snapshot: {e}")

    # 3. Inicialização e Carregamento de Dados
    if 'df' not in st.session_state:
        st.session_state.df = create_mock_dataframe()
    
    df = st.session_state.df
    snapshots = load_snapshots()  # Agora carrega do MySQL AWS
    
    # Mock de seleção de empreendimento
    empreendimentos = df['Empreendimento'].unique().tolist()
    selected_empreendimento = st.sidebar.selectbox("🏢 Selecione o Empreendimento", empreendimentos)
    
    # Filtra o DataFrame pelo empreendimento selecionado
    df_filtered = df[df['Empreendimento'] == selected_empreendimento].copy()
    
    # 4. Botão para criar snapshot
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📸 Gerenciar Snapshots")
    
    if st.sidebar.button("📸 Fotografar Cenário Real como Previsto", key="manual_snapshot_trigger", use_container_width=True):
        try:
            new_version_name = take_snapshot(df, selected_empreendimento)
            st.success(f"✅ Snapshot '{new_version_name}' criado com sucesso no banco AWS!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Erro ao criar snapshot: {e}")
    
    # 5. Gerenciamento de Snapshots
    st.sidebar.markdown("### 💾 Snapshots Salvos")
    empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
    
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
    
    # 6. Visualização Interativa (Seleção de Versão)
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔄 Comparação de Versões")
    
    # Lista de versões disponíveis para o empreendimento selecionado
    version_options = ["Real Atual (Comparar com P0)"]
    
    # Adiciona as versões salvas (Pn)
    version_options.extend(sorted(empreendimento_snapshots.keys()))
    
    selected_version = st.sidebar.selectbox(
        "Selecione a Versão de Planejamento (Baseline) para Comparação",
        version_options,
        index=0
    )
    
    # 7. Aplicação da Versão Selecionada ao DataFrame
    
    if selected_version == "Real Atual (Comparar com P0)":
        # Compara Real Atual com P0 (o planejamento original)
        df_filtered['Previsto_Inicio'] = df_filtered['P0_Previsto_Inicio']
        df_filtered['Previsto_Fim'] = df_filtered['P0_Previsto_Fim']
        st.info("📊 Comparando Real Atual com a Linha de Base **P0 (Padrão)**.")
    elif selected_version in empreendimento_snapshots:
        # Aplica os dados da versão selecionada
        version_data_list = empreendimento_snapshots[selected_version]['data']
        version_data = pd.DataFrame(version_data_list)
        
        # O nome das colunas no snapshot é Pn_Previsto_Inicio/Fim
        version_prefix = selected_version.split('-')[0]
        col_inicio = f'{version_prefix}_Previsto_Inicio'
        col_fim = f'{version_prefix}_Previsto_Fim'
        
        # Renomeia as colunas do snapshot para 'Previsto_Inicio' e 'Previsto_Fim'
        version_data = version_data.rename(columns={col_inicio: 'Previsto_Inicio', col_fim: 'Previsto_Fim'})
        
        # Converte as strings de data de volta para datetime
        version_data['Previsto_Inicio'] = pd.to_datetime(version_data['Previsto_Inicio'])
        version_data['Previsto_Fim'] = pd.to_datetime(version_data['Previsto_Fim'])
        
        # Merge com o DataFrame filtrado
        df_filtered = df_filtered.merge(
            version_data[['ID_Tarefa', 'Previsto_Inicio', 'Previsto_Fim']],
            on='ID_Tarefa',
            how='left',
            suffixes=('_atual', '_novo')
        )
        
        # Atualiza as colunas de previsão
        df_filtered['Previsto_Inicio'] = df_filtered['Previsto_Inicio_novo']
        df_filtered['Previsto_Fim'] = df_filtered['Previsto_Fim_novo']
        df_filtered = df_filtered.drop(columns=['Previsto_Inicio_atual', 'Previsto_Fim_atual', 'Previsto_Inicio_novo', 'Previsto_Fim_novo'], errors='ignore')
        
        st.info(f"📊 Comparando Real Atual com a Linha de Base: **{selected_version}**.")
    
    # 8. Geração do Gráfico e Injeção do JS
    
    # Cria o HTML da área do gráfico (mock)
    gantt_area_html = create_gantt_chart(df_filtered)
    
    # Injeta o menu de contexto JS e o HTML da área
    inject_js_context_menu(gantt_area_html, selected_empreendimento)
    
    # 9. Requisito de Download do Arquivo TXT
    
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
    
    # 10. Informações de Debug
    with st.sidebar.expander("🔧 Informações de Debug"):
        st.json(snapshots)
        st.metric("Total de Snapshots", sum(len(versions) for versions in snapshots.values()))
        st.metric("Snapshots deste Empreendimento", len(empreendimento_snapshots))

if __name__ == "__main__":
    main()
