/* Lógica JavaScript para o Menu Circular Minimalista */

function createSnapshot(empreendimento) {
    // Navega para a mesma URL mas com parâmetros que indicam para criar snapshot
    const currentUrl = window.location.href.split('?')[0];
    const encodedEmpreendimento = encodeURIComponent(empreendimento);
    const newUrl = currentUrl + '?take_snapshot=true&empreendimento=' + encodedEmpreendimento + '&t=' + Date.now();
    window.location.href = newUrl;
}

function viewPeriod(empreendimento) {
    // Navega para a mesma URL mas com parâmetros que indicam para visualizar período
    const currentUrl = window.location.href.split('?')[0];
    const encodedEmpreendimento = encodeURIComponent(empreendimento);
    // Adiciona um parâmetro para acionar a visualização do período
    const newUrl = currentUrl + '?view_period=true&empreendimento=' + encodedEmpreendimento + '&t=' + Date.now();
    window.location.href = newUrl;
}

function injectCircularMenu(empreendimento) {
    const ganttArea = document.getElementById('gantt-chart-area');
    
    if (ganttArea) {
        ganttArea.addEventListener('contextmenu', function(e) {
            e.preventDefault(); // Previne o menu de contexto padrão do navegador
            
            // Remove menu existente se houver
            const existingMenu = document.getElementById('circular-context-menu');
            if (existingMenu) {
                existingMenu.remove();
            }
            
            // Cria o container do menu circular
            const menuContainer = document.createElement('div');
            menuContainer.id = 'circular-context-menu';
            menuContainer.className = 'circular-menu';
            
            // Define a posição inicial do menu (no ponto do clique)
            const x = e.pageX;
            const y = e.pageY;
            menuContainer.style.left = x + 'px';
            menuContainer.style.top = y + 'px';

            // --- Itens do Menu ---
            
            // 1. Fotografar Linha de Base
            const item1 = document.createElement('div');
            item1.className = 'menu-item';
            item1.innerHTML = '<span class="menu-item-icon">📸</span>';
            item1.title = 'Fotografar Linha de Base';
            item1.onclick = () => {
                createSnapshot(empreendimento);
                menuContainer.remove();
            };

            // 2. Visualizar Período
            const item2 = document.createElement('div');
            item2.className = 'menu-item';
            item2.innerHTML = '<span class="menu-item-icon">⏳</span>';
            item2.title = 'Visualizar Período entre Linhas de Base';
            item2.onclick = () => {
                viewPeriod(empreendimento);
                menuContainer.remove();
            };

            // 3. Botão de Fechar (Opcional, mas útil)
            const closeButton = document.createElement('div');
            closeButton.className = 'menu-toggle';
            closeButton.innerHTML = '✖';
            closeButton.title = 'Fechar Menu';
            closeButton.onclick = () => {
                menuContainer.remove();
            };

            menuContainer.appendChild(item1);
            menuContainer.appendChild(item2);
            menuContainer.appendChild(closeButton);
            
            document.body.appendChild(menuContainer);
            
            // Força o reflow para garantir que a transição funcione
            void menuContainer.offsetWidth; 
            
            // Torna o menu visível para iniciar a transição
            menuContainer.classList.add('visible');

            // --- Lógica de Posicionamento Circular ---
            const radius = 80; // Raio do círculo
            const items = [item1, item2];
            const totalItems = items.length;
            const angleStep = 360 / totalItems; // Ângulo entre os itens

            items.forEach((item, index) => {
                // Calcula o ângulo em radianos (começando de cima, -90 graus)
                const angle = (index * angleStep - 90) * (Math.PI / 180);
                
                // Calcula a posição (x, y) no círculo
                const itemX = radius * Math.cos(angle);
                const itemY = radius * Math.sin(angle);

                // Aplica a translação para a posição final
                // O translate(-50%, -50%) já está no CSS para centralizar o item
                item.style.transform = `translate(calc(-50% + ${itemX}px), calc(-50% + ${itemY}px)) scale(1)`;
            });

            // Fecha o menu ao clicar fora
            function closeMenu(e) {
                if (!menuContainer.contains(e.target)) {
                    menuContainer.remove();
                    document.removeEventListener('click', closeMenu);
                }
            }
            
            // Adiciona o listener para fechar o menu
            setTimeout(() => {
                document.addEventListener('click', closeMenu);
            }, 0);
        });
    }
}
