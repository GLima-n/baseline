import streamlit as st
import pandas as pd
import json
from datetime import datetime
import mysql.connector
from mysql.connector import Error
from streamlit.components.v1 import html
import time

# --- Configuração da Página (Deve ser a primeira linha) ---
st.set_page_config(layout="wide", page_title="Gantt Chart Baseline", initial_sidebar_state="expanded")

# --- Configurações do Banco AWS ---
try:
    DB_CONFIG = {
        'host': st.secrets["aws_db"]["host"],
        'user': st.secrets["aws_db"]["user"],
        'password': st.secrets["aws_db"]["password"],
        'database': st.secrets["aws_db"]["database"],
        'port': 3306
    }
    # Removi o st.success aqui para limpar a interface visual
except Exception as e:
    DB_CONFIG = {
        'host': "mock_host",
        'user': "mock_user", 
        'password': "mock_password",
        'database': "mock_db",
        'port': 3306
    }

# --- Inicialização do Session State para "Staging" ---
if 'pending_snapshots' not in st.session_state:
    st.session_state.pending_snapshots = [] # Lista para armazenar snapshots antes de enviar para AWS

if 'df' not in st.session_state:
    # Função placeholder para criar dados iniciais
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
    st.session_state.df = df

# --- Funções de Banco de Dados ---

def get_db_connection():
    """Tenta estabelecer conexão com o banco de dados."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        if conn.is_connected():
            return conn
        else:
            return None
    except Exception:
        return None

def test_connection():
    conn = get_db_connection()
    if conn:
        conn.close()
        return True
    return False

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
            st.error(f"❌ Erro DB: {e}")
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        if 'mock_snapshots' not in st.session_state:
            st.session_state.mock_snapshots = {}

def load_snapshots_from_db():
    """Carrega snapshots APENAS do banco (confirmados)."""
    conn = get_db_connection()
    snapshots = {}
    if conn:
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
                
                try:
                    snapshot_data = json.loads(row['snapshot_data'])
                    snapshots[empreendimento][version_name] = {
                        "date": row['created_date'],
                        "data": snapshot_data,
                        "status": "saved" # Flag para indicar que está salvo
                    }
                except json.JSONDecodeError:
                    continue
            return snapshots
        except Error:
            return {}
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        return st.session_state.get('mock_snapshots', {})

def save_pending_to_aws():
    """Envia os snapshots da lista 'pending' para a AWS."""
    conn = get_db_connection()
    if not conn:
        st.error("❌ Sem conexão com AWS. Salvando localmente (Sessão).")
        # Lógica offline simplificada
        for item in st.session_state.pending_snapshots:
            if 'mock_snapshots' not in st.session_state: st.session_state.mock_snapshots = {}
            emp = item['empreendimento']
            if emp not in st.session_state.mock_snapshots: st.session_state.mock_snapshots[emp] = {}
            st.session_state.mock_snapshots[emp][item['version_name']] = {
                "date": item['created_date'], "data": item['snapshot_data']
            }
        st.session_state.pending_snapshots = []
        return True

    try:
        cursor = conn.cursor()
        insert_query = """
        INSERT INTO snapshots (empreendimento, version_name, snapshot_data, created_date)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE 
            snapshot_data = VALUES(snapshot_data), 
            created_date = VALUES(created_date)
        """
        
        for item in st.session_state.pending_snapshots:
            snapshot_json = json.dumps(item['snapshot_data'], ensure_ascii=False)
            cursor.execute(insert_query, (
                item['empreendimento'], 
                item['version_name'], 
                snapshot_json, 
                item['created_date']
            ))
        
        conn.commit()
        st.session_state.pending_snapshots = [] # Limpa a lista de pendentes
        return True
            
    except Error as e:
        st.error(f"❌ Erro ao salvar na AWS: {e}")
        return False
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

def delete_snapshot(empreendimento, version_name):
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            delete_query = "DELETE FROM snapshots WHERE empreendimento = %s AND version_name = %s"
            cursor.execute(delete_query, (empreendimento, version_name))
            conn.commit()
            return True
        except Error:
            return False
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    else:
        # Delete offline logic
        pass
    return False

# --- Lógica de Snapshot (Na Memória) ---

def buffer_new_snapshot(df, empreendimento):
    """Cria o snapshot mas salva apenas na LISTA DE PENDENTES (st.session_state)."""
    df_empreendimento = df[df['Empreendimento'] == empreendimento].copy()
    
    # Carrega o que já existe no banco + o que está pendente para calcular o nome P(n)
    existing_snapshots_db = load_snapshots_from_db().get(empreendimento, {})
    
    # Nomes do DB
    existing_names = list(existing_snapshots_db.keys())
    # Nomes Pendentes
    pending_names = [x['version_name'] for x in st.session_state.pending_snapshots if x['empreendimento'] == empreendimento]
    
    all_versions = existing_names + pending_names
    p_versions = [k for k in all_versions if k.startswith('P') and k.split('-')[0][1:].isdigit()]
    
    next_n = 1
    if p_versions:
        max_n = 0
        for v in p_versions:
            try:
                n_str = v.split('-')[0][1:]
                n = int(n_str)
                if n > max_n: max_n = n
            except ValueError: continue
        next_n = max_n + 1
    
    version_prefix = f"P{next_n}"
    current_date_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    version_name = f"{version_prefix}-({current_date_str})"
    
    # Prepara dados
    df_snapshot = df_empreendimento[['ID_Tarefa', 'Real_Inicio', 'Real_Fim']].copy()
    df_snapshot['Real_Inicio'] = df_snapshot['Real_Inicio'].dt.strftime('%Y-%m-%d')
    df_snapshot['Real_Fim'] = df_snapshot['Real_Fim'].dt.strftime('%Y-%m-%d')
    
    snapshot_data = df_snapshot.rename(
        columns={'Real_Inicio': f'{version_prefix}_Previsto_Inicio', 'Real_Fim': f'{version_prefix}_Previsto_Fim'}
    ).to_dict('records')

    # ADICIONA À LISTA DE PENDENTES
    new_pending = {
        'empreendimento': empreendimento,
        'version_name': version_name,
        'snapshot_data': snapshot_data,
        'created_date': current_date_str
    }
    
    st.session_state.pending_snapshots.append(new_pending)
    return version_name

# --- Menu de Contexto e Scripts JS ---

def create_context_menu_and_warning(selected_empreendimento, has_unsaved_changes):
    js_has_unsaved = str(has_unsaved_changes).lower()
    
    html_code = f"""
    <style>
    #gantt-area-container {{
        height: 300px; 
        border: 2px dashed #ccc; 
        display: flex; 
        align-items: center; 
        justify-content: center; 
        background-color: #f9f9f9; 
        cursor: context-menu;
        margin: 20px 0; 
        border-radius: 8px;
        position: relative; /* Importante para posicionamento */
    }}
    #gantt-area-container:hover {{
        background-color: #f1f1f1;
        border-color: #bbb;
    }}
    .custom-context-menu {{
        position: fixed; /* Fixed para garantir que fique sobre tudo */
        background: white;
        border: 1px solid #ddd;
        border-radius: 6px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        z-index: 999999;
        display: none;
        font-family: "Source Sans Pro", sans-serif;
        font-size: 14px;
        min-width: 180px;
    }}
    .custom-context-menu-item {{
        padding: 12px 20px;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 10px;
        color: #31333F;
    }}
    .custom-context-menu-item:hover {{
        background: #f0f2f6;
        color: #ff4b4b;
    }}
    </style>

    <div id="gantt-area-container" class="gantt-target">
        <div style="text-align: center; pointer-events: none;">
            <h3 style="margin:0; color: #31333F;">📈 Área do Gráfico de Gantt</h3>
            <p style="margin:5px 0 0 0; color: #666; font-size: 0.9em;">
                {selected_empreendimento}<br>
                <b>Clique com o botão direito aqui</b>
            </p>
        </div>
    </div>

    <div id="custom-context-menu" class="custom-context-menu">
        <div class="custom-context-menu-item" onclick="triggerSnapshotAction('take_snapshot')">
            <span>📸</span> Criar Snapshot (Local)
        </div>
        <div class="custom-context-menu-item" onclick="triggerSnapshotAction('view_details')">
            <span>👁️</span> Ver Detalhes
        </div>
    </div>

    <script>
    // Script encapsulado para não poluir escopo global desnecessariamente
    (function() {{
        // 1. Proteção de Dados (Unsaved Changes)
        const hasUnsaved = {js_has_unsaved};
        if (hasUnsaved) {{
            window.onbeforeunload = function(e) {{
                e = e || window.event;
                if (e) {{ e.returnValue = 'Dados não salvos!'; }}
                return 'Dados não salvos!';
            }};
        }} else {{
            window.onbeforeunload = null;
        }}

        // 2. Função de Ação Global
        window.triggerSnapshotAction = function(action) {{
            document.getElementById('custom-context-menu').style.display = 'none';
            const params = new URLSearchParams(window.location.search);
            params.set('snapshot_action', action);
            params.set('empreendimento', "{selected_empreendimento}");
            params.set('ts', Date.now());
            window.location.search = params.toString();
        }};

        // 3. LÓGICA DE EVENTO (DELEGAÇÃO)
        // Removemos listener antigo para evitar duplicação em reruns do Streamlit
        if (window.ganttContextMenuHandler) {{
            document.removeEventListener('contextmenu', window.ganttContextMenuHandler);
        }}
        
        if (window.ganttClickHandler) {{
            document.removeEventListener('click', window.ganttClickHandler);
        }}

        // Define o novo handler de Context Menu
        window.ganttContextMenuHandler = function(e) {{
            // Verifica se o elemento clicado (ou algum pai dele) é o nosso container
            const target = e.target.closest('#gantt-area-container');
            const menu = document.getElementById('custom-context-menu');

            if (target && menu) {{
                e.preventDefault(); // Bloqueia menu nativo do navegador
                menu.style.display = 'block';
                menu.style.left = e.pageX + 'px';
                menu.style.top = e.pageY + 'px';
            }} else if (menu) {{
                // Se clicar com direito fora, esconde
                menu.style.display = 'none';
            }}
        }};

        // Define handler para clicar fora (fechar menu)
        window.ganttClickHandler = function(e) {{
            const menu = document.getElementById('custom-context-menu');
            if (menu && !menu.contains(e.target)) {{
                menu.style.display = 'none';
            }}
        }};
        
        // Handler para ESC
        window.ganttEscHandler = function(e) {{
             if (e.key === 'Escape') {{
                 const menu = document.getElementById('custom-context-menu');
                 if(menu) menu.style.display = 'none';
             }}
        }};

        // Adiciona os listeners ao DOCUMENTO (garantia de funcionar mesmo com delay de render)
        document.addEventListener('contextmenu', window.ganttContextMenuHandler);
        document.addEventListener('click', window.ganttClickHandler);
        document.addEventListener('keydown', window.ganttEscHandler);

    }})();
    </script>
    """
    return html_code
    
def process_url_actions():
    """Processa a ação e LIMPA a URL imediatamente para evitar loops."""
    # Acessa query params da nova forma (st.query_params)
    query = st.query_params
    
    action = query.get('snapshot_action')
    emp = query.get('empreendimento')
    
    if action == 'take_snapshot' and emp:
        try:
            # Cria snapshot na lista de pendentes
            v_name = buffer_new_snapshot(st.session_state.df, emp)
            st.toast(f"📸 Snapshot {v_name} criado localmente! Verifique a barra lateral.", icon="💾")
        except Exception as e:
            st.error(f"Erro: {e}")
        
        # Limpa a URL para evitar reprocessamento e loop
        st.query_params.clear()
        time.sleep(0.1) # Pequeno delay para garantir sincronia
        st.rerun()

# --- Visualização de Comparação ---
def display_comparison(df_filtered, snapshots_dict):
    st.markdown("#### ⏳ Comparativo de Linhas de Base")
    
    flat_versions = ["P0 (Planejamento Original)"]
    
    # Junta versões salvas (DB) e pendentes (Session)
    saved_versions = list(snapshots_dict.keys())
    pending_versions = [x['version_name'] for x in st.session_state.pending_snapshots if x['empreendimento'] == df_filtered['Empreendimento'].iloc[0]]
    
    all_versions = sorted(list(set(saved_versions + pending_versions)))
    flat_versions.extend(all_versions)
    
    c1, c2 = st.columns(2)
    v_a = c1.selectbox("Versão A", flat_versions, 0)
    v_b = c2.selectbox("Versão B", flat_versions, min(1, len(flat_versions)-1))
    
    # (Lógica de comparação simplificada para brevidade do exemplo)
    st.info(f"Comparando {v_a} com {v_b}...")

# --- APP PRINCIPAL ---

def main():
    st.title("📊 Gerenciador de Gantt e Snapshots")
    
    # 1. Inicializar Banco na primeira execução
    if 'db_init' not in st.session_state:
        create_snapshots_table()
        st.session_state.db_init = True

    # 2. Processar Ações da URL (Menu de Contexto)
    process_url_actions()

    # 3. Carregar Dados
    df = st.session_state.df
    
    # Sidebar - Seleção
    st.sidebar.header("Navegação")
    emps = df['Empreendimento'].unique()
    selected_emp = st.sidebar.selectbox("Selecione o Empreendimento", emps)
    df_filtered = df[df['Empreendimento'] == selected_emp]
    
    # ---------------------------------------------------------
    #  ÁREA DE "STAGING" (PENDENTES) - AQUI ESTÁ A SOLUÇÃO
    # ---------------------------------------------------------
    pending_count = len(st.session_state.pending_snapshots)
    
    if pending_count > 0:
        st.sidebar.markdown("---")
        st.sidebar.error(f"⚠️ **{pending_count} Snapshot(s) Não Salvo(s)**")
        st.sidebar.markdown("Os dados estão apenas na memória. Se você sair agora, perderá os snapshots.")
        
        col_btn1, col_btn2 = st.sidebar.columns([3, 1])
        if col_btn1.button("☁️ ENVIAR PARA AWS", type="primary", use_container_width=True):
            with st.sidebar.status("Enviando dados...", expanded=True):
                if save_pending_to_aws():
                    st.success("Dados salvos com sucesso!")
                    time.sleep(1)
                    st.rerun()
        
        if col_btn2.button("🗑️", help="Descartar todos os pendentes"):
            st.session_state.pending_snapshots = []
            st.rerun()
            
        # Mostra lista de pendentes
        with st.sidebar.expander("Ver pendentes"):
            for p in st.session_state.pending_snapshots:
                st.caption(f"• {p['version_name']}")
    else:
        st.sidebar.markdown("---")
        st.sidebar.success("✅ Todos os dados sincronizados")

    # ---------------------------------------------------------
    
    # Carrega snapshots confirmados do banco para exibição
    db_snapshots = load_snapshots_from_db()
    emp_snapshots = db_snapshots.get(selected_emp, {})

    # Visualização Principal
    col_main, col_info = st.columns([3, 1])
    
    with col_main:
        # --- MUDANÇA AQUI ---
        # Gera o código HTML/JS
        html_code = create_context_menu_and_warning(selected_emp, has_unsaved_changes=(pending_count > 0))
        
        # USAR st.markdown COM unsafe_allow_html=True
        # Isso tira o código do iframe sandbox e joga na página real
        st.markdown(html_code, unsafe_allow_html=True) 
        
        st.subheader("Dados Atuais")
        st.dataframe(df_filtered.head(), use_container_width=True)

    with col_info:
        st.subheader("Histórico (AWS)")
        if emp_snapshots:
            for v_name in sorted(emp_snapshots.keys(), reverse=True):
                st.text(f"📅 {v_name}")
                if st.button("Deletar", key=f"del_{v_name}"):
                    delete_snapshot(selected_emp, v_name)
                    st.rerun()
        else:
            st.info("Nenhum histórico na AWS.")

    if st.checkbox("Mostrar Comparação"):
        display_comparison(df_filtered, emp_snapshots)

if __name__ == "__main__":
    main()
