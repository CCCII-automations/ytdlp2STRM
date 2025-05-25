/* ===== THEME MANAGER ===== */
/* ytdlp2STRM - Theme Management System */

class ThemeManager {
    constructor() {
        this.STORAGE_KEY = 'ytdlp2strm-theme';
        this.THEMES = {
            light: {
                name: 'Light Mode',
                icon: '☀️'
            },
            dark: {
                name: 'Dark Mode',
                icon: '🌙'
            },
            auto: {
                name: 'Auto (System)',
                icon: '🔄'
            }
        };

        this.currentTheme = this.getSavedTheme();
        this.init();
    }

    init() {
        this.createThemeSwitcher();
        this.applyTheme(this.currentTheme);
        this.bindEvents();

        // Listen for system theme changes when in auto mode
        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
                if (this.currentTheme === 'auto') {
                    this.applyTheme('auto');
                }
            });
        }
    }

    getSavedTheme() {
        try {
            const saved = localStorage.getItem(this.STORAGE_KEY);
            return saved && this.THEMES[saved] ? saved : 'auto';
        } catch (error) {
            console.warn('Could not access localStorage for theme preference');
            return 'auto';
        }
    }

    saveTheme(theme) {
        try {
            localStorage.setItem(this.STORAGE_KEY, theme);
        } catch (error) {
            console.warn('Could not save theme preference to localStorage');
        }
    }

    createThemeSwitcher() {
        // Find existing theme switchers or create them
        const existingSwitchers = document.querySelectorAll('.theme-switcher');

        if (existingSwitchers.length === 0) {
            // Create theme switcher in header controls
            const headerControls = document.querySelector('.header-controls');
            if (headerControls) {
                const switcher = this.createSwitcherElement();
                headerControls.insertBefore(switcher, headerControls.firstChild);
            }
        } else {
            // Update existing switchers
            existingSwitchers.forEach(switcher => {
                const select = switcher.querySelector('.theme-select');
                if (select) {
                    this.populateSelect(select);
                    select.value = this.currentTheme;
                }
            });
        }
    }

    createSwitcherElement() {
        const switcher = document.createElement('div');
        switcher.className = 'theme-switcher';

        const select = document.createElement('select');
        select.className = 'theme-select';
        select.setAttribute('aria-label', 'Choose theme');

        this.populateSelect(select);
        select.value = this.currentTheme;

        switcher.appendChild(select);
        return switcher;
    }

    populateSelect(select) {
        select.innerHTML = '';

        Object.entries(this.THEMES).forEach(([key, theme]) => {
            const option = document.createElement('option');
            option.value = key;
            option.textContent = `${theme.icon} ${theme.name}`;
            select.appendChild(option);
        });
    }

    bindEvents() {
        // Listen for theme switcher changes
        document.addEventListener('change', (e) => {
            if (e.target.classList.contains('theme-select')) {
                this.setTheme(e.target.value);
            }
        });

        // Handle keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + Shift + T to toggle theme
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'T') {
                e.preventDefault();
                this.toggleTheme();
            }
        });
    }

    setTheme(theme) {
        if (!this.THEMES[theme]) {
            console.warn(`Unknown theme: ${theme}`);
            return;
        }

        this.currentTheme = theme;
        this.saveTheme(theme);
        this.applyTheme(theme);
        this.updateAllSwitchers();
    }

    applyTheme(theme) {
        const html = document.documentElement;

        // Remove existing theme classes
        html.removeAttribute('data-theme');
        html.classList.remove('theme-light', 'theme-dark');

        let effectiveTheme = theme;

        if (theme === 'auto') {
            // Detect system preference
            if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
                effectiveTheme = 'dark';
            } else {
                effectiveTheme = 'light';
            }
        }

        // Apply theme
        if (effectiveTheme === 'dark') {
            html.setAttribute('data-theme', 'dark');
            html.classList.add('theme-dark');
        } else {
            html.classList.add('theme-light');
        }

        // Update favicon if exists
        this.updateFavicon(effectiveTheme);

        // Dispatch custom event for other components
        window.dispatchEvent(new CustomEvent('themechange', {
            detail: {
                theme: this.currentTheme,
                effectiveTheme: effectiveTheme
            }
        }));
    }

    updateFavicon(theme) {
        const favicon = document.querySelector('link[rel="icon"]');
        if (favicon) {
            // You can set different favicons for different themes
            // favicon.href = theme === 'dark' ? '/favicon-dark.ico' : '/favicon-light.ico';
        }
    }

    updateAllSwitchers() {
        document.querySelectorAll('.theme-select').forEach(select => {
            select.value = this.currentTheme;
        });
    }

    toggleTheme() {
        const themes = Object.keys(this.THEMES);
        const currentIndex = themes.indexOf(this.currentTheme);
        const nextIndex = (currentIndex + 1) % themes.length;
        this.setTheme(themes[nextIndex]);
    }

    getCurrentTheme() {
        return this.currentTheme;
    }

    getEffectiveTheme() {
        if (this.currentTheme === 'auto') {
            return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }
        return this.currentTheme;
    }
}

// Initialize theme manager when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.themeManager = new ThemeManager();
    });
} else {
    window.themeManager = new ThemeManager();
}

// Utility functions for other scripts
window.getTheme = () => window.themeManager?.getCurrentTheme() || 'auto';
window.getEffectiveTheme = () => window.themeManager?.getEffectiveTheme() || 'light';
window.setTheme = (theme) => window.themeManager?.setTheme(theme);

// Add theme switcher to any element with class 'theme-switcher-container'
function addThemeSwitcherTo(containerSelector) {
    const container = document.querySelector(containerSelector);
    if (container && window.themeManager) {
        const switcher = window.themeManager.createSwitcherElement();
        container.appendChild(switcher);
    }
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ThemeManager;
}