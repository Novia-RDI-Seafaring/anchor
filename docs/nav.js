// Navigation and search functionality
const pages = [
    { title: 'Home', url: 'index.html', keywords: 'anchor ui documentation home welcome' },
    { title: 'Getting Started', url: 'getting-started.html', keywords: 'installation setup configuration environment variables prerequisites' },
    { title: 'User Guide', url: 'user-guide.html', keywords: 'how to use guide tutorial workflow' },
    { title: 'Features', url: 'features.html', keywords: 'features functionality capabilities' },
    { title: 'Knowledge Base', url: 'knowledge-base.html', keywords: 'documents upload files pdf docx knowledge base' },
    { title: 'Chat Interface', url: 'chat-interface.html', keywords: 'chat conversation messages assistant' },
    { title: 'Settings', url: 'settings.html', keywords: 'settings configuration options preferences' },
    { title: 'MCP Tools', url: 'mcp-tools.html', keywords: 'mcp model context protocol tools extensions' },
    { title: 'Command Line', url: 'command-line.html', keywords: 'cli command line options arguments' },
    { title: 'Architecture', url: 'architecture.html', keywords: 'architecture design system structure components' },
    { title: 'Components', url: 'components.html', keywords: 'components frontend backend modules' },
    { title: 'API Reference', url: 'api-reference.html', keywords: 'api endpoints rest backend' },
    { title: 'Contributing', url: 'contributing.html', keywords: 'contribute development pull request' }
];

// Initialize navigation
function initNav() {
    const nav = document.getElementById('nav');
    if (!nav) return;
    
    const navHTML = '<ul>' + pages.map(page => 
        `<li><a href="${page.url}">${page.title}</a></li>`
    ).join('') + '</ul>';
    
    nav.innerHTML = navHTML;
    
    // Highlight current page
    const currentPage = window.location.pathname.split('/').pop() || 'index.html';
    nav.querySelectorAll('a').forEach(link => {
        if (link.getAttribute('href') === currentPage) {
            link.classList.add('active');
        }
    });
}

// Initialize search
function initSearch() {
    const searchInput = document.getElementById('searchInput');
    const searchResults = document.getElementById('searchResults');
    
    if (!searchInput || !searchResults) return;
    
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim();
        
        if (query.length < 2) {
            searchResults.classList.remove('active');
            return;
        }
        
        const matches = pages.filter(page => 
            page.title.toLowerCase().includes(query) || 
            page.keywords.toLowerCase().includes(query)
        );
        
        if (matches.length > 0) {
            searchResults.innerHTML = '<h3>Search Results</h3>' + 
                matches.map(page => 
                    `<a href="${page.url}">${page.title}</a>`
                ).join('');
            searchResults.classList.add('active');
        } else {
            searchResults.innerHTML = '<h3>No results found</h3>';
            searchResults.classList.add('active');
        }
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initNav();
    initSearch();
});

