/**
 * Toast Notification System
 * 
 * Usage:
 *   showToast('Success!', 'success');
 *   showToast('Error occurred', 'error');
 *   showToast('Info message', 'info');
 *   showToast('Warning!', 'warning');
 */

const Toast = {
    container: null,
    
    init() {
        if (!this.container) {
            this.container = document.getElementById('toast-container');
            if (!this.container) {
                this.container = document.createElement('div');
                this.container.id = 'toast-container';
                document.body.appendChild(this.container);
            }
        }
    },
    
    show(message, type = 'info', duration = 5000) {
        this.init();
        
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        const icons = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ℹ'
        };
        
        toast.innerHTML = `
            <span class="toast-icon">${icons[type] || 'ℹ'}</span>
            <span class="toast-message">${message}</span>
            <button class="toast-close" onclick="this.parentElement.remove()">×</button>
        `;
        
        this.container.appendChild(toast);
        
        // Animate in
        requestAnimationFrame(() => {
            toast.classList.add('toast-visible');
        });
        
        // Auto dismiss
        if (duration > 0) {
            setTimeout(() => {
                toast.classList.remove('toast-visible');
                setTimeout(() => toast.remove(), 300);
            }, duration);
        }
        
        return toast;
    },
    
    success(message, duration = 5000) {
        return this.show(message, 'success', duration);
    },
    
    error(message, duration = 7000) {
        return this.show(message, 'error', duration);
    },
    
    warning(message, duration = 6000) {
        return this.show(message, 'warning', duration);
    },
    
    info(message, duration = 5000) {
        return this.show(message, 'info', duration);
    },
    
    promise(promise, messages = {}) {
        const loadingToast = this.show(messages.loading || 'Loading...', 'info', 0);
        
        return promise
            .then(result => {
                loadingToast.remove();
                if (messages.success) {
                    this.success(messages.success);
                }
                return result;
            })
            .catch(error => {
                loadingToast.remove();
                this.error(messages.error || error.message || 'An error occurred');
                throw error;
            });
    }
};

// Convenience functions
function showToast(message, type = 'info', duration = 5000) {
    return Toast.show(message, type, duration);
}

function showSuccess(message, duration = 5000) {
    return Toast.success(message, duration);
}

function showError(message, duration = 7000) {
    return Toast.error(message, duration);
}

function showWarning(message, duration = 6000) {
    return Toast.warning(message, duration);
}

function showInfo(message, duration = 5000) {
    return Toast.info(message, duration);
}

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { Toast, showToast, showSuccess, showError, showWarning, showInfo };
}