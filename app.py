import streamlit as st
import pandas as pd
import json
from datetime import datetime
import mysql.connector
from mysql.connector import Error
import time
import textwrap
import uuid # Importante para gerar IDs únicos

# --- Configuração da Página ---
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
    DB_CONFIG = None # Modo Offline

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
            query = """
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
            cursor.execute(query)
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
            for row in cursor.fetchall():
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
    # Offline
    if not conn:
        if 'mock_snapshots' not in st.session_state: st.session_state.mock_snapshots = {}
        for item in st.session_state.pending_snapshots:
            emp = item['empreendimento']
            if emp not in st.session_state.mock_snapshots: st.session_state.mock_snapshots[emp] = {}
            st.session_state.mock_snapshots[emp][item['version_name']] = {
                "date": item['created_date'], "data": item['snapshot_data']
            }
        st.session_state.pending_snapshots = []
        return True
    
    # Online
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

# --- Buffer Logic ---

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

def clean_html(html_string):
    return "\n".join([line.strip() for line in html_string.splitlines()])

# --- FUNÇÃO CORRIGIDA (REACT SAFE) ---

def create_context_menu_stable(selected_empreendimento, has_unsaved_changes):
    js_unsaved = "true" if has_unsaved_changes else "false"
    
    # Geramos IDs únicos para os elementos para poder selecioná-los via JS
    # sem causar conflito com outros elementos da página
    unique_id = str(uuid.uuid4())[:8]
    box_id = f"gantt-box-{unique_id}"
    btn_id = f"gantt-btn-{unique_id}"

    # NOTA: Removemos todos os 'onclick' e 'oncontextmenu' do HTML abaixo
    # Eles serão adicionados via addEventListener no script, evitando o erro do React.
    raw_html = f"""
    <style>
        .gantt-box {{
            height: 300px;
            background-color: #fdfdfd;
            border: 2px dashed #aaa;
            border-radius: 8px;
            position: relative;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            user-select: none;
            transition: all 0.3s;
        }}
        .gantt-box:hover {{
            border-color: #ff4b4b;
            background-color: #fff5f5;
        }}
        .gantt-settings-btn {{
            position: absolute;
            top: 10px;
            right: 10px;
            font-size: 24px;
            cursor: pointer;
            opacity: 0.6;
            background: none;
            border: none;
            padding: 5px;
            z-index: 10;
        }}
        .gantt-settings-btn:hover {{
            opacity: 1;
            transform: scale(1.1);
        }}
        .custom-gantt-menu {{
            position: fixed;
            z-index: 9999999;
            background: white;
            border: 1px solid #ddd;
            box-shadow: 2px 2px 10px rgba(0,0,0,0.2);
            border-radius: 6px;
            width: 200px;
            display: none;
            font-family: sans-serif;
        }}
        .menu-item {{
            padding: 12px 16px;
            cursor: pointer;
            color: #333;
            font-size: 14px;
            border-bottom: 1px solid #f0f0f0;
        }}
        .menu-item:hover {{
            background-color: #ff4b4b;
            color: white;
        }}
    </style>

    <div id="{box_id}" class="gantt-box">
        <button id="{btn_id}" class="gantt-settings-btn" title="Opções">⚙️</button>
        <h3 style="margin:0; color:#444; pointer-events:none;">📈 Gantt: {selected_empreendimento}</h3>
        <p style="color:#888; font-size:14px; pointer-events:none;">Clique com <b>Botão Direito</b> ou na <b>Engrenagem</b></p>
    </div>

    <script>
    (function() {{
        // 1. Proteção de Saída
        if ({js_unsaved}) {{
            window.onbeforeunload = (e) => {{ e.returnValue = 'Dados pendentes!'; return 'Dados pendentes!'; }};
        }} else {{
            window.onbeforeunload = null;
        }}

        // 2. Limpeza de menus antigos
        const oldMenus = document.querySelectorAll('.custom-gantt-menu');
        oldMenus.forEach(el => el.remove());

        // 3. Criação do Menu
        const menu = document.createElement('div');
        menu.className = 'custom-gantt-menu';
        menu.innerHTML = `
            <div class="menu-item" id="menu-item-snap-{unique_id}">📸 Criar Snapshot</div>
            <div class="menu-item" id="menu-item-view-{unique_id}">👁️ Ver Detalhes</div>
        `;
        document.body.appendChild(menu);

        // 4. Funções Lógicas
        function abrirMenuGantt(e, isLeftClick = false) {{
            if (!isLeftClick) e.preventDefault(); 
            e.stopPropagation(); 
            const x = e.pageX || (e.clientX + window.scrollX);
            const y = e.pageY || (e.clientY + window.scrollY);
            menu.style.display = 'block';
            menu.style.left = (isLeftClick ? x - 180 : x) + 'px';
            menu.style.top = y + 'px';
        }}

        function acaoGantt(acao) {{
            menu.style.display = 'none';
            const params = new URLSearchParams(window.location.search);
            params.set('snapshot_action', acao);
            params.set('empreendimento', "{selected_empreendimento}");
            params.set('ts', Date.now());
            window.location.search = params.toString();
        }}

        // 5. ADICIONANDO LISTENERS VIA JS (EVITA ERRO REACT)
        
        // Listener para o DIV (Botão Direito)
        const box = document.getElementById('{box_id}');
        if (box) {{
            box.addEventListener('contextmenu', function(e) {{
                abrirMenuGantt(e, false);
            }});
        }}

        // Listener para o BOTÃO (Clique Esquerdo)
        const btn = document.getElementById('{btn_id}');
        if (btn) {{
            btn.addEventListener('click', function(e) {{
                abrirMenuGantt(e, true);
            }});
        }}

        // Listeners para os itens do menu (necessário pois removemos onclick do HTML string)
        document.getElementById('menu-item-snap-{unique_id}').addEventListener('click', function() {{
            acaoGantt('take_snapshot');
        }});
        
        document.getElementById('menu-item-view-{unique_id}').addEventListener('click', function() {{
            acaoGantt('view_details');
        }});

        // Fechar ao clicar fora
        const closeHandler = (e) => {{
            if (menu.style.display === 'block' && !menu.contains(e.target) && e.target !== btn) {{
                menu.style.display = 'none';
            }}
        }};
        
        // Cleanup listener global para não acumular
        if (window.globalGanttClose) document.removeEventListener('click', window.globalGanttClose);
        window.globalGanttClose = closeHandler;
        document.addEventListener('click', window.globalGanttClose);

    }})();
    </script>
    """
    
    return clean_html(raw_html)

def process_url_actions():
    try:
        query = st.query_params
        action = query.get('snapshot_action')
        emp = query.get('empreendimento')
        if action == 'take_snapshot' and emp:
            v_name = buffer_new_snapshot(st.session_state.df, emp)
            st.toast(f"Snapshot {v_name} criado!", icon="✅")
            st.query_params.clear()
            time.sleep(0.2)
            st.rerun()
    except: pass

# --- APP PRINCIPAL ---

def main():
    st.title("📊 Sistema de Gantt Controlado")
    
    if 'db_init' not in st.session_state:
        create_snapshots_table()
        st.session_state.db_init = True

    process_url_actions()
    
    df = st.session_state.df
    emps = df['Empreendimento'].unique()
    selected_emp = st.sidebar.selectbox("Empreendimento", emps)
    df_filtered = df[df['Empreendimento'] == selected_emp]
    
    pending_count = len(st.session_state.pending_snapshots)
    if pending_count > 0:
        st.sidebar.error(f"⚠️ {pending_count} Pendentes")
        c1, c2 = st.sidebar.columns(2)
        if c1.button("☁️ Salvar", type="primary"):
            if save_pending_to_aws():
                st.success("Salvo!"); time.sleep(0.5); st.rerun()
        if c2.button("🗑️ Limpar"):
            st.session_state.pending_snapshots = []; st.rerun()
    else:
        st.sidebar.success("✅ Sincronizado")
        
    col_main, col_hist = st.columns([3, 1])
    
    with col_main:
        # unsafe_allow_html=True renderiza o HTML limpo + Script que injeta os eventos
        html_code = create_context_menu_stable(selected_emp, pending_count > 0)
        st.markdown(html_code, unsafe_allow_html=True)
        
        st.dataframe(df_filtered, use_container_width=True)
        
    with col_hist:
        st.write("**Histórico (Banco)**")
        saved = load_snapshots_from_db().get(selected_emp, {})
        if not saved: st.info("Vazio")
        for k in sorted(saved.keys(), reverse=True):
            c_a, c_b = st.columns([4, 1])
            c_a.text(f"📅 {k}")
            if c_b.button("X", key=f"del_{k}"):
                delete_snapshot(selected_emp, k); st.rerun()

if __name__ == "__main__":
    main()
