import streamlit as st
import pandas as pd
import json
from datetime import datetime
import mysql.connector
from mysql.connector import Error
import time
import uuid

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
except Exception:
    DB_CONFIG = None # Define como None se falhar para ativar modo offline

# --- Inicialização do Session State ---
if 'pending_snapshots' not in st.session_state:
    st.session_state.pending_snapshots = []

if 'df' not in st.session_state:
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
    st.session_state.df = df

# --- Funções de Banco de Dados ---

def get_db_connection():
    if not DB_CONFIG: return None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        if conn.is_connected(): return conn
    except Exception: pass
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
            cursor.close()
            conn.close()
        except Error: pass
    else:
        if 'mock_snapshots' not in st.session_state:
            st.session_state.mock_snapshots = {}

def load_snapshots_from_db():
    conn = get_db_connection()
    snapshots = {}
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT empreendimento, version_name, snapshot_data, created_date FROM snapshots ORDER BY created_at DESC")
            results = cursor.fetchall()
            for row in results:
                emp = row['empreendimento']
                if emp not in snapshots: snapshots[emp] = {}
                try:
                    snapshots[emp][row['version_name']] = {
                        "date": row['created_date'],
                        "data": json.loads(row['snapshot_data'])
                    }
                except: continue
            cursor.close()
            conn.close()
            return snapshots
        except Error: return {}
    else:
        return st.session_state.get('mock_snapshots', {})

def save_pending_to_aws():
    conn = get_db_connection()
    if not conn:
        # Modo Offline
        if 'mock_snapshots' not in st.session_state: st.session_state.mock_snapshots = {}
        for item in st.session_state.pending_snapshots:
            emp = item['empreendimento']
            if emp not in st.session_state.mock_snapshots: st.session_state.mock_snapshots[emp] = {}
            st.session_state.mock_snapshots[emp][item['version_name']] = {
                "date": item['created_date'], "data": item['snapshot_data']
            }
        st.session_state.pending_snapshots = []
        return True

    try:
        cursor = conn.cursor()
        query = """
        INSERT INTO snapshots (empreendimento, version_name, snapshot_data, created_date)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE snapshot_data = VALUES(snapshot_data), created_date = VALUES(created_date)
        """
        for item in st.session_state.pending_snapshots:
            cursor.execute(query, (item['empreendimento'], item['version_name'], json.dumps(item['snapshot_data']), item['created_date']))
        conn.commit()
        cursor.close()
        conn.close()
        st.session_state.pending_snapshots = []
        return True
    except Error as e:
        st.error(f"Erro AWS: {e}")
        return False

def delete_snapshot(empreendimento, version_name):
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM snapshots WHERE empreendimento = %s AND version_name = %s", (empreendimento, version_name))
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Error: return False
    return False

# --- Lógica de Buffer ---

def buffer_new_snapshot(df, empreendimento):
    df_emp = df[df['Empreendimento'] == empreendimento].copy()
    existing_db = load_snapshots_from_db().get(empreendimento, {})
    existing_names = list(existing_db.keys())
    pending_names = [x['version_name'] for x in st.session_state.pending_snapshots if x['empreendimento'] == empreendimento]
    
    all_versions = existing_names + pending_names
    p_versions = [k for k in all_versions if k.startswith('P') and k.split('-')[0][1:].isdigit()]
    
    next_n = 1
    if p_versions:
        max_n = max([int(v.split('-')[0][1:]) for v in p_versions if v.split('-')[0][1:].isdigit()] + [0])
        next_n = max_n + 1
    
    version_prefix = f"P{next_n}"
    current_date = datetime.now().strftime("%d/%m/%Y %H:%M")
    version_name = f"{version_prefix}-({current_date})"
    
    df_snap = df_emp[['ID_Tarefa', 'Real_Inicio', 'Real_Fim']].copy()
    df_snap['Real_Inicio'] = df_snap['Real_Inicio'].dt.strftime('%Y-%m-%d')
    df_snap['Real_Fim'] = df_snap['Real_Fim'].dt.strftime('%Y-%m-%d')
    
    snapshot_data = df_snap.rename(columns={'Real_Inicio': f'{version_prefix}_Previsto_Inicio', 'Real_Fim': f'{version_prefix}_Previsto_Fim'}).to_dict('records')

    st.session_state.pending_snapshots.append({
        'empreendimento': empreendimento,
        'version_name': version_name,
        'snapshot_data': snapshot_data,
        'created_date': current_date
    })
    return version_name

# --- MENU DE CONTEXTO ROBUSTO (SOLUÇÃO FINAL) ---

def create_context_menu_safe(selected_empreendimento, has_unsaved_changes):
    # Gera IDs únicos para evitar conflitos de cache do Streamlit
    uid = str(uuid.uuid4())[:8]
    menu_id = f"ctx_menu_{uid}"
    
    js_unsaved = "true" if has_unsaved_changes else "false"

    html_code = f"""
    <style>
        /* Área de Clique */
        .gantt-area-final {{
            height: 300px;
            background-color: #f8f9fa;
            border: 2px dashed #ff4b4b; /* Borda vermelha visível */
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            cursor: context-menu;
            transition: background 0.2s;
            user-select: none; /* Importante para evitar seleção de texto */
        }}
        .gantt-area-final:hover {{
            background-color: #fff0f0;
        }}
        .gantt-area-final:active {{
            background-color: #ffe0e0; /* Feedback visual de clique */
        }}

        /* Menu Customizado */
        #{menu_id} {{
            display: none;
            position: fixed;
            z-index: 999999;
            width: 200px;
            background-color: #ffffff;
            border-radius: 6px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.3);
            border: 1px solid #e0e0e0;
            font-family: "Source Sans Pro", sans-serif;
            overflow: hidden;
        }}
        .ctx-item-final {{
            padding: 12px 16px;
            cursor: pointer;
            color: #333;
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 10px;
            transition: background 0.1s;
        }}
        .ctx-item-final:hover {{
            background-color: #ff4b4b;
            color: white;
        }}
        .ctx-separator {{
            height: 1px;
            background-color: #eee;
            margin: 0;
        }}
    </style>

    <div class="gantt-area-final" oncontextmenu="handleRightClick_{uid}(event)">
        <h3 style="margin:0; color:#333; pointer-events:none;">📈 Área Gantt: {selected_empreendimento}</h3>
        <p style="color:#666; pointer-events:none;">Clique com Botão Direito Aqui</p>
    </div>

    <script>
    // Cria o menu dinamicamente no BODY para evitar ser cortado
    (function() {{
        // 1. Configura proteção de saída
        if ({js_unsaved}) {{
            window.onbeforeunload = function(e) {{ e.returnValue = 'Dados pendentes!'; return 'Dados pendentes!'; }};
        }} else {{
            window.onbeforeunload = null;
        }}

        // 2. Remove menus antigos (limpeza)
        const existingMenu = document.getElementById("{menu_id}");
        if (existingMenu) existingMenu.remove();

        // 3. Cria o HTML do Menu
        const menu = document.createElement("div");
        menu.id = "{menu_id}";
        menu.innerHTML = `
            <div class="ctx-item-final" onclick="sendAction_{uid}('take_snapshot')">📸 Criar Snapshot</div>
            <div class="ctx-separator"></div>
            <div class="ctx-item-final" onclick="sendAction_{uid}('view_details')">👁️ Ver Detalhes</div>
        `;
        document.body.appendChild(menu);

        // 4. Define função global de clique direito
        window.handleRightClick_{uid} = function(e) {{
            e.preventDefault(); // Bloqueia menu do navegador
            
            // Posiciona o menu
            menu.style.display = "block";
            menu.style.left = e.pageX + "px";
            menu.style.top = e.pageY + "px";
        }};

        // 5. Define função global de envio de ação
        window.sendAction_{uid} = function(action) {{
            menu.style.display = "none";
            
            // Usa URLSearchParams para garantir encoding correto
            const params = new URLSearchParams(window.location.search);
            params.set("snapshot_action", action);
            params.set("empreendimento", "{selected_empreendimento}");
            params.set("ts", Date.now());
            
            window.location.search = params.toString();
        }};

        // 6. Fecha menu ao clicar fora (qualquer clique na página)
        window.addEventListener("click", function(e) {{
            if (menu && !menu.contains(e.target)) {{
                menu.style.display = "none";
            }}
        }});
        
        // 7. Fecha menu com ESC
        window.addEventListener("keydown", function(e) {{
            if (e.key === "Escape" && menu) menu.style.display = "none";
        }});

    }})();
    </script>
    """
    return html_code

def process_url_actions():
    try:
        # Compatibilidade com novas versões do Streamlit
        query = st.query_params
        action = query.get('snapshot_action')
        emp = query.get('empreendimento')
        
        if action == 'take_snapshot' and emp:
            try:
                v_name = buffer_new_snapshot(st.session_state.df, emp)
                st.toast(f"Snapshot {v_name} na memória!", icon="💾")
            except Exception as e:
                st.error(f"Erro: {e}")
            
            st.query_params.clear()
            time.sleep(0.2)
            st.rerun()
    except:
        pass

# --- APP ---

def main():
    st.title("📊 Sistema de Gantt Controlado")
    
    if 'db_init' not in st.session_state:
        create_snapshots_table()
        st.session_state.db_init = True

    process_url_actions()
    
    # Sidebar
    df = st.session_state.df
    emps = df['Empreendimento'].unique()
    selected_emp = st.sidebar.selectbox("Empreendimento", emps)
    df_filtered = df[df['Empreendimento'] == selected_emp]
    
    # --- Lógica de Pendentes ---
    pending_count = len(st.session_state.pending_snapshots)
    if pending_count > 0:
        st.sidebar.error(f"⚠️ {pending_count} Itens Pendentes")
        if st.sidebar.button("☁️ Enviar para AWS", type="primary"):
            if save_pending_to_aws():
                st.success("Salvo!")
                time.sleep(0.5)
                st.rerun()
        if st.sidebar.button("🗑️ Limpar"):
            st.session_state.pending_snapshots = []
            st.rerun()
    else:
        st.sidebar.success("✅ Sincronizado")
        
    # Layout Principal
    c1, c2 = st.columns([3, 1])
    
    with c1:
        # INJEÇÃO DO HTML SEGURO
        html_code = create_context_menu_safe(selected_emp, pending_count > 0)
        st.markdown(html_code, unsafe_allow_html=True)
        
        st.dataframe(df_filtered, use_container_width=True)
        
    with c2:
        st.write("**Histórico Salvo**")
        saved = load_snapshots_from_db().get(selected_emp, {})
        for k in sorted(saved.keys(), reverse=True):
            st.text(f"📅 {k}")
            if st.button("X", key=f"del_{k}"):
                delete_snapshot(selected_emp, k)
                st.rerun()

if __name__ == "__main__":
    main()
