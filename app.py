import streamlit as st
import pandas as pd
import json
from datetime import datetime
import mysql.connector
from mysql.connector import Error
from streamlit.components.v1 import html

# ... (mantenha todas as funções anteriores de banco de dados, snapshot, etc. iguais)

# --- Menu de Contexto com Botão Direito CORRIGIDO ---

def create_context_menu(selected_empreendimento):
    """Cria um menu de contexto com botão direito usando HTML/JS corrigido"""
    
    html_code = f"""
<script>
// Variável global para controlar se já processamos uma ação
let actionProcessed = false;

function showContextMenu(event) {{
    event.preventDefault();
    event.stopPropagation();
    
    const contextMenu = document.getElementById('context-menu');
    if (!contextMenu) return;
    
    // Posiciona o menu no local do clique
    const x = event.clientX;
    const y = event.clientY;
    
    contextMenu.style.left = x + 'px';
    contextMenu.style.top = y + 'px';
    contextMenu.style.display = 'block';
}}

function executeAction(action, empreendimento) {{
    console.log('Executando ação:', action, 'para:', empreendimento);
    
    // Previne execução múltipla
    if (actionProcessed) {{
        console.log('Ação já processada, ignorando...');
        return;
    }}
    actionProcessed = true;
    
    // Esconde o menu
    const contextMenu = document.getElementById('context-menu');
    if (contextMenu) {{
        contextMenu.style.display = 'none';
    }}
    
    // Cria elementos hidden para comunicação com Streamlit
    const hiddenDiv = document.createElement('div');
    hiddenDiv.id = 'context_menu_action_data';
    hiddenDiv.style.display = 'none';
    hiddenDiv.setAttribute('data-action', action);
    hiddenDiv.setAttribute('data-empreendimento', empreendimento);
    hiddenDiv.setAttribute('data-timestamp', Date.now().toString());
    
    // Remove qualquer elemento anterior
    const existingDiv = document.getElementById('context_menu_action_data');
    if (existingDiv) {{
        existingDiv.remove();
    }}
    
    document.body.appendChild(hiddenDiv);
    
    // Dispara um evento customizado que o Streamlit pode detectar
    const event = new CustomEvent('contextMenuAction', {{
        detail: {{ action, empreendimento }}
    }});
    document.dispatchEvent(event);
    
    // Força um rerun do Streamlit
    setTimeout(() => {{
        // Tenta usar a API do Streamlit para forçar atualização
        if (window.parent && window.parent.frameElement) {{
            const frame = window.parent.frameElement;
            if (frame.contentWindow && frame.contentWindow.location) {{
                // Adiciona parâmetro à URL para forçar recarregamento
                const currentUrl = new URL(window.location.href);
                currentUrl.searchParams.set('context_action', action);
                currentUrl.searchParams.set('context_emp', empreendimento);
                currentUrl.searchParams.set('t', Date.now().toString());
                
                // Navega para a nova URL
                window.location.href = currentUrl.toString();
            }}
        }}
    }}, 100);
}}

// Fecha o menu quando clicar em qualquer lugar
document.addEventListener('click', function(e) {{
    const contextMenu = document.getElementById('context-menu');
    if (contextMenu && !contextMenu.contains(e.target)) {{
        contextMenu.style.display = 'none';
    }}
}});

// Fecha o menu com ESC
document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') {{
        const contextMenu = document.getElementById('context-menu');
        if (contextMenu) {{
            contextMenu.style.display = 'none';
        }}
    }}
}});

// Previne o menu de contexto padrão na área do Gantt
document.addEventListener('contextmenu', function(e) {{
    if (e.target.closest('#gantt-area')) {{
        showContextMenu(e);
    }}
}}, true);

// Reset da flag quando a página carrega
window.addEventListener('load', function() {{
    actionProcessed = false;
}});
</script>

<style>
#context-menu {{
    position: fixed;
    background: white;
    border: 1px solid #ccc;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    z-index: 10000;
    display: none;
    padding: 8px 0;
    min-width: 200px;
    font-family: Arial, sans-serif;
    font-size: 14px;
}}

.menu-item {{
    padding: 10px 16px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 8px;
    border: none;
    background: none;
    width: 100%;
    text-align: left;
}}

.menu-item:hover {{
    background-color: #f0f0f0;
}}

#gantt-area {{
    height: 300px;
    border: 2px dashed #ccc;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: #f9f9f9;
    cursor: pointer;
    margin: 20px 0;
    border-radius: 10px;
    user-select: none;
}}
</style>

<div id="gantt-area">
    <div style="text-align: center;">
        <h3>📊 Área do Gráfico de Gantt</h3>
        <p>Clique com o botão direito para abrir o menu de contexto</p>
    </div>
</div>

<div id="context-menu">
    <button class="menu-item" onclick="executeAction('take_snapshot', '{selected_empreendimento}')">
        📸 <span>Tirar Snapshot</span>
    </button>
    <button class="menu-item" onclick="executeAction('restore_snapshot', '{selected_empreendimento}')">
        🔄 <span>Restaurar Snapshot</span>
    </button>
    <button class="menu-item" onclick="executeAction('delete_snapshot', '{selected_empreendimento}')">
        🗑️ <span>Deletar Snapshot</span>
    </button>
</div>
"""
    return html_code

# --- Processamento das Ações do Menu CORRIGIDO ---

def process_context_menu_actions():
    """Processa as ações do menu de contexto via query parameters"""
    query_params = st.query_params
    
    # Verifica tanto os parâmetros antigos quanto os novos
    action = query_params.get("action", [None])[0] or query_params.get("context_action", [None])[0]
    empreendimento = query_params.get("empreendimento", [None])[0] or query_params.get("context_emp", [None])[0]
    
    if action and empreendimento:
        st.toast(f"Processando: {action} para {empreendimento}", icon="🎯")
        
        # Limpa os parâmetros
        st.query_params.clear()
        
        df = st.session_state.df
        
        if action == 'take_snapshot':
            try:
                version_name = take_snapshot(df, empreendimento)
                st.success(f"✅ Snapshot '{version_name}' criado com sucesso!")
                # Usa st.rerun() em vez de st.experimental_rerun()
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao criar snapshot: {e}")
        
        elif action == 'restore_snapshot':
            st.session_state.show_restore_dialog = True
            st.rerun()
        
        elif action == 'delete_snapshot':
            st.session_state.show_delete_dialog = True
            st.rerun()

# --- Aplicação Principal ATUALIZADA ---

def main():
    st.set_page_config(layout="wide", page_title="Gantt Chart Baseline")
    st.title("📊 Gráfico de Gantt com Versionamento")
    
    # Inicialização SEGURA do session_state
    required_states = {
        'df': create_mock_dataframe(),
        'show_restore_dialog': False,
        'show_delete_dialog': False,
        'show_comparison': False
    }
    
    for key, default_value in required_states.items():
        if key not in st.session_state:
            st.session_state[key] = default_value
    
    create_snapshots_table()
    
    # Processa ações do menu de contexto PRIMEIRO (antes de qualquer UI)
    process_context_menu_actions()
    
    df = st.session_state.df
    snapshots = load_snapshots()
    
    # Sidebar
    st.sidebar.header("🔧 Configurações")
    empreendimentos = df['Empreendimento'].unique().tolist()
    selected_empreendimento = st.sidebar.selectbox("🏢 Empreendimento", empreendimentos)
    df_filtered = df[df['Empreendimento'] == selected_empreendimento].copy()
    
    # Ações rápidas na sidebar
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚡ Ações Rápidas")
    
    if st.sidebar.button("📸 Criar Snapshot", use_container_width=True, type="primary"):
        try:
            version_name = take_snapshot(df, selected_empreendimento)
            st.sidebar.success(f"✅ {version_name} criado!")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"❌ Erro: {e}")
    
    if st.sidebar.button("⏳ Comparar Períodos", use_container_width=True):
        st.session_state.show_comparison = not st.session_state.show_comparison
        st.rerun()
    
    # Visualização principal
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📋 Dados do Projeto")
        st.dataframe(df_filtered, use_container_width=True)
    
    with col2:
        st.subheader("💾 Snapshots")
        empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
        if empreendimento_snapshots:
            for version in sorted(empreendimento_snapshots.keys()):
                st.write(f"• **{version}**")
                st.caption(f"Criado em: {empreendimento_snapshots[version]['date']}")
        else:
            st.info("ℹ️ Nenhum snapshot disponível")
    
    # Menu de contexto com botão direito
    st.markdown("---")
    st.subheader("🎯 Menu de Contexto (Botão Direito)")
    
    context_menu_html = create_context_menu(selected_empreendimento)
    html(context_menu_html, height=350)
    
    # Debug info (opcional)
    with st.expander("🔍 Debug Info"):
        st.write("Query params atuais:", dict(st.query_params))
        st.write("Session state:", {k: v for k, v in st.session_state.items() if not k.startswith('_')})
    
    # Botões alternativos para garantir funcionalidade
    st.markdown("**Alternativa:** Use estes botões se o menu de contexto não funcionar:")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📸 Tirar Snapshot (Alternativo)", key="alt_take", use_container_width=True):
            try:
                version_name = take_snapshot(df, selected_empreendimento)
                st.success(f"✅ Snapshot '{version_name}' criado com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao criar snapshot: {e}")
    
    with col2:
        if st.button("🔄 Restaurar (Alternativo)", key="alt_restore", use_container_width=True):
            st.session_state.show_restore_dialog = True
            st.rerun()
    
    with col3:
        if st.button("🗑️ Gerenciar (Alternativo)", key="alt_delete", use_container_width=True):
            st.session_state.show_delete_dialog = True
            st.rerun()
    
    # Diálogos modais
    if st.session_state.show_restore_dialog:
        st.markdown("---")
        show_restore_dialog(selected_empreendimento, snapshots)
    
    if st.session_state.show_delete_dialog:
        st.markdown("---")
        show_delete_dialog(selected_empreendimento, snapshots)
    
    # Comparação de períodos
    if st.session_state.show_comparison:
        st.markdown("---")
        empreendimento_snapshots = snapshots.get(selected_empreendimento, {})
        if empreendimento_snapshots:
            display_period_comparison(df_filtered, empreendimento_snapshots)
        else:
            st.warning("Nenhum snapshot disponível para comparação")

if __name__ == "__main__":
    main()
