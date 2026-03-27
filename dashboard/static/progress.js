/**
 * Real-time Deployment Progress Component
 * 
 * Connects to WebSocket for live deployment progress updates.
 * 
 * Usage:
 *   DeploymentProgress.startDeployment(appName, branch, environment);
 *   DeploymentProgress.connect(deploymentId);
 *   DeploymentProgress.disconnect();
 */

const DeploymentProgress = {
    socket: null,
    deploymentId: null,
    appId: null,
    environment: null,
    branch: null,
    commit: null,
    reconnectAttempts: 0,
    maxReconnectAttempts: 5,
    reconnectDelay: 1000,
    startTime: null,
    timerInterval: null,
    
    stepNames: {
        'git_fetch': 'Fetching code',
        'git_pull': 'Pulling changes',
        'install_deps': 'Installing dependencies',
        'build_assets': 'Building assets',
        'run_migrations': 'Running migrations',
        'clear_cache': 'Clearing cache',
        'restart_services': 'Restarting services',
        'health_check': 'Health check'
    },
    
    stepIcons: {
        'git_fetch': '📥',
        'git_pull': '⬇️',
        'install_deps': '📦',
        'build_assets': '🔨',
        'run_migrations': '🗃️',
        'clear_cache': '🧹',
        'restart_services': '🔄',
        'health_check': '💚'
    },
    
    async startDeployment(appName, branch = 'main', environment = 'production', commit = null) {
        try {
            const response = await fetch(`/api/apps/${appName}/deploy-async`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ branch, environment, commit })
            });
            
            const data = await response.json();
            
            if (!data.success) {
                showError(data.error || 'Failed to start deployment');
                return null;
            }
            
            this.deploymentId = data.deployment_id;
            this.appId = appName;
            this.environment = environment;
            this.branch = branch;
            this.commit = commit;
            this.startTime = Date.now();
            
            this.showModal();
            this.connect(data.websocket_room);
            this.startTimer();
            
            return data;
        } catch (error) {
            showError('Failed to start deployment: ' + error.message);
            return null;
        }
    },
    
    connect(room) {
        if (typeof io === 'undefined') {
            console.warn('Socket.IO not loaded, falling back to polling');
            this.startPolling();
            return;
        }
        
        this.socket = io({
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionAttempts: this.maxReconnectAttempts,
            reconnectionDelay: this.reconnectDelay
        });
        
        this.socket.on('connect', () => {
            console.log('WebSocket connected');
            this.reconnectAttempts = 0;
            this.socket.emit('join', { room: room });
        });
        
        this.socket.on('disconnect', () => {
            console.log('WebSocket disconnected');
        });
        
        this.socket.on('reconnect', (attemptNumber) => {
            console.log('WebSocket reconnected after', attemptNumber, 'attempts');
            this.socket.emit('join', { room: room });
            showInfo('Reconnected to deployment');
        });
        
        this.socket.on('reconnect_failed', () => {
            console.error('WebSocket reconnection failed');
            showError('Lost connection to deployment');
        });
        
        // Deployment events
        this.socket.on('deployment_started', (data) => this.onDeploymentStarted(data));
        this.socket.on('server_started', (data) => this.onServerStarted(data));
        this.socket.on('step_progress', (data) => this.onStepProgress(data));
        this.socket.on('deployment_complete', (data) => this.onDeploymentComplete(data));
        this.socket.on('deployment_failed', (data) => this.onDeploymentFailed(data));
        this.socket.on('deployment_error', (data) => this.onDeploymentError(data));
        this.socket.on('deployment_cancelled', (data) => this.onDeploymentCancelled(data));
        
        // State sync for reconnection
        this.socket.on('state_sync', (data) => this.onStateSync(data));
    },
    
    disconnect() {
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
        }
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
        }
    },
    
    startPolling() {
        const pollInterval = setInterval(async () => {
            if (!this.deploymentId) {
                clearInterval(pollInterval);
                return;
            }
            
            try {
                const response = await fetch(`/api/deployments/${this.deploymentId}`);
                const data = await response.json();
                
                if (data.success) {
                    this.updateFromState(data.deployment, data.steps, data.progress);
                    
                    if (['success', 'failed', 'cancelled'].includes(data.deployment.status)) {
                        clearInterval(pollInterval);
                        this.onDeploymentComplete(data.deployment);
                    }
                }
            } catch (error) {
                console.error('Polling error:', error);
            }
        }, 2000);
    },
    
    showModal() {
        const modal = document.getElementById('progress-modal');
        if (modal) {
            modal.style.display = 'flex';
            
            document.getElementById('progress-title').textContent = `Deploying ${this.appId}`;
            document.getElementById('progress-app').textContent = this.appId;
            document.getElementById('progress-branch').textContent = this.branch;
            document.getElementById('progress-commit').textContent = this.commit || 'latest';
            document.getElementById('progress-servers').innerHTML = '';
            document.getElementById('progress-output').innerHTML = '';
            this.updateProgress(0);
        }
    },
    
    closeModal() {
        const modal = document.getElementById('progress-modal');
        if (modal) {
            modal.style.display = 'none';
        }
        this.disconnect();
    },
    
    startTimer() {
        this.startTime = Date.now();
        this.timerInterval = setInterval(() => {
            const elapsed = Math.floor((Date.now() - this.startTime) / 1000);
            const minutes = Math.floor(elapsed / 60);
            const seconds = elapsed % 60;
            const timeEl = document.getElementById('progress-time');
            if (timeEl) {
                timeEl.textContent = `Started ${minutes}m ${seconds}s ago`;
            }
        }, 1000);
    },
    
    updateProgress(percent) {
        const bar = document.querySelector('#progress-bar .progress-fill');
        const text = document.getElementById('progress-percent');
        
        if (bar) bar.style.width = `${percent}%`;
        if (text) text.textContent = `${Math.round(percent)}%`;
    },
    
    getServerEl(server) {
        let el = document.querySelector(`.progress-server[data-server="${server}"]`);
        if (!el) {
            const container = document.getElementById('progress-servers');
            if (!container) return null;
            
            el = document.createElement('div');
            el.className = 'progress-server';
            el.dataset.server = server;
            el.innerHTML = `
                <div class="progress-server-header">
                    <span class="progress-server-name">${server}</span>
                    <span class="progress-server-status">Waiting</span>
                </div>
                <div class="progress-server-steps"></div>
            `;
            container.appendChild(el);
        }
        return el;
    },
    
    onDeploymentStarted(data) {
        showInfo(`Deployment started for ${data.app_name || this.appId}`);
    },
    
    onServerStarted(data) {
        const serverEl = this.getServerEl(data.server);
        if (serverEl) {
            serverEl.querySelector('.progress-server-status').textContent = 'Running';
            serverEl.querySelector('.progress-server-status').className = 'progress-server-status running';
        }
    },
    
    onStepProgress(data) {
        const serverEl = this.getServerEl(data.server);
        if (!serverEl) return;
        
        const stepsContainer = serverEl.querySelector('.progress-server-steps');
        let stepEl = stepsContainer.querySelector(`.progress-step[data-step="${data.step}"]`);
        
        if (!stepEl) {
            stepEl = document.createElement('div');
            stepEl.className = 'progress-step';
            stepEl.dataset.step = data.step;
            stepsContainer.appendChild(stepEl);
        }
        
        const icon = this.stepIcons[data.step] || '▶';
        const name = this.stepNames[data.step] || data.step;
        const statusClass = data.status === 'running' ? 'running' : 
                            data.status === 'success' ? 'success' : 
                            data.status === 'failed' ? 'failed' : '';
        
        stepEl.className = `progress-step ${statusClass}`;
        stepEl.innerHTML = `
            <span class="progress-step-icon">${icon}</span>
            <span class="progress-step-name">${name}</span>
            <span class="progress-step-status">${data.status}</span>
        `;
        
        if (data.progress) {
            this.updateProgress(data.progress);
        }
        
        if (data.output) {
            this.appendOutput(data.server, data.step, data.output);
        }
    },
    
    appendOutput(server, step, output) {
        const outputEl = document.getElementById('progress-output');
        if (!outputEl) return;
        
        const line = document.createElement('div');
        line.className = 'progress-output-line';
        line.innerHTML = `<span class="progress-output-server">[${server}]</span> ${output}`;
        outputEl.appendChild(line);
        outputEl.scrollTop = outputEl.scrollHeight;
    },
    
    onDeploymentComplete(data) {
        showSuccess(`Deployment completed successfully!`);
        this.updateProgress(100);
        
        document.querySelectorAll('.progress-server-status').forEach(el => {
            el.textContent = 'Complete';
            el.className = 'progress-server-status success';
        });
        
        document.getElementById('progress-cancel').style.display = 'none';
        
        setTimeout(() => {
            this.closeModal();
            window.location.reload();
        }, 2000);
    },
    
    onDeploymentFailed(data) {
        showError(`Deployment failed: ${data.error || 'Unknown error'}`);
        
        document.querySelectorAll('.progress-server-status').forEach(el => {
            if (el.textContent !== 'Complete' && el.textContent !== 'Success') {
                el.textContent = 'Failed';
                el.className = 'progress-server-status failed';
            }
        });
        
        document.getElementById('progress-cancel').textContent = 'Close';
    },
    
    onDeploymentError(data) {
        showError(`Deployment error: ${data.error}`);
    },
    
    onDeploymentCancelled(data) {
        showWarning('Deployment was cancelled');
        this.closeModal();
    },
    
    onStateSync(state) {
        // Restore state after reconnection
        if (state.deployment) {
            document.getElementById('progress-title').textContent = `Deploying ${state.deployment.app_id || this.appId}`;
        }
        
        if (state.servers) {
            Object.entries(state.servers).forEach(([server, info]) => {
                const serverEl = this.getServerEl(server);
                if (serverEl && info.status) {
                    serverEl.querySelector('.progress-server-status').textContent = info.status;
                }
            });
        }
        
        if (state.progress) {
            this.updateProgress(state.progress.progress_percent || 0);
        }
    },
    
    updateFromState(deployment, steps, progress) {
        if (!steps) return;
        
        steps.forEach(step => {
            this.onStepProgress({
                server: step.server,
                step: step.step,
                status: step.status,
                output: step.output
            });
        });
        
        if (progress) {
            this.updateProgress(progress.progress_percent || 0);
        }
    },
    
    async cancel() {
        if (!this.deploymentId) return;
        
        if (!confirm('Are you sure you want to cancel this deployment?')) return;
        
        try {
            const response = await fetch(`/api/deployments/${this.deploymentId}/cancel`, {
                method: 'POST'
            });
            
            const data = await response.json();
            
            if (data.success) {
                showWarning('Deployment cancelled');
                this.closeModal();
            } else {
                showError(data.error || 'Failed to cancel deployment');
            }
        } catch (error) {
            showError('Failed to cancel: ' + error.message);
        }
    }
};

// Global functions for HTML onclick handlers
function closeProgressModal() {
    DeploymentProgress.closeModal();
}

function cancelDeployment() {
    DeploymentProgress.cancel();
}

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DeploymentProgress;
}