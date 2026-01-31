/**
 * BookContentPipeline Dashboard - Frontend Application
 */

// API endpoints
const API = {
    files: '/api/files',
    stats: '/api/corpus/stats',
    checkpoint: '/api/checkpoint',
    status: '/api/run/status',
    start: '/api/run/start',
    pause: '/api/run/pause',
    resume: '/api/run/resume',
    stop: '/api/run/stop',
    reset: '/api/run/reset',
};

// State
const state = {
    selectedFiles: new Set(),
    runStatus: 'idle',
    wsConnected: false,
    ws: null,
};

// DOM Elements
const elements = {
    connectionDot: document.getElementById('connectionDot'),
    connectionText: document.getElementById('connectionText'),
    fileList: document.getElementById('fileList'),
    refreshFilesBtn: document.getElementById('refreshFilesBtn'),
    forceReprocess: document.getElementById('forceReprocess'),
    startBtn: document.getElementById('startBtn'),
    pauseBtn: document.getElementById('pauseBtn'),
    stopBtn: document.getElementById('stopBtn'),
    statusBadge: document.getElementById('statusBadge'),
    progressStage: document.getElementById('progressStage'),
    progressPercent: document.getElementById('progressPercent'),
    progressBar: document.getElementById('progressBar'),
    progressMessage: document.getElementById('progressMessage'),
    logPanel: document.getElementById('logPanel'),
    checkpointInfo: document.getElementById('checkpointInfo'),
    refreshCheckpointBtn: document.getElementById('refreshCheckpointBtn'),
    statCharacters: document.getElementById('statCharacters'),
    statLocations: document.getElementById('statLocations'),
    statFactions: document.getElementById('statFactions'),
    statEvents: document.getElementById('statEvents'),
    statNodes: document.getElementById('statNodes'),
    statEdges: document.getElementById('statEdges'),
    // Token usage elements
    tokenPrompt: document.getElementById('tokenPrompt'),
    tokenOutput: document.getElementById('tokenOutput'),
    tokenTotal: document.getElementById('tokenTotal'),
    tokenCalls: document.getElementById('tokenCalls'),
};

// ============================================================
// WebSocket Connection
// ============================================================
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/progress`;

    state.ws = new WebSocket(wsUrl);

    state.ws.onopen = () => {
        state.wsConnected = true;
        updateConnectionStatus(true);
        console.log('WebSocket connected');
    };

    state.ws.onclose = () => {
        state.wsConnected = false;
        updateConnectionStatus(false);
        console.log('WebSocket disconnected, reconnecting in 2s...');
        setTimeout(connectWebSocket, 2000);
    };

    state.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };

    state.ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        handleWebSocketMessage(message);
    };

    // Ping to keep connection alive
    setInterval(() => {
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            state.ws.send('ping');
        }
    }, 30000);
}

function updateConnectionStatus(connected) {
    if (connected) {
        elements.connectionDot.classList.add('connected');
        elements.connectionText.textContent = 'Connected';
    } else {
        elements.connectionDot.classList.remove('connected');
        elements.connectionText.textContent = 'Disconnected';
    }
}

function handleWebSocketMessage(message) {
    if (message.type === 'progress') {
        updateProgress(message.data);
        addLogEntry(message.data);
    } else if (message.type === 'status') {
        updateRunStatus(message.data);
    }
}

// ============================================================
// API Functions
// ============================================================
async function fetchFiles() {
    try {
        const response = await fetch(API.files);
        const files = await response.json();
        renderFileList(files);
    } catch (error) {
        console.error('Error fetching files:', error);
        elements.fileList.innerHTML = '<div class="empty-state"><p>Error loading files</p></div>';
    }
}

async function fetchStats() {
    try {
        const response = await fetch(API.stats);
        const stats = await response.json();
        updateStats(stats);
    } catch (error) {
        console.error('Error fetching stats:', error);
    }
}

async function fetchCheckpoint() {
    try {
        const response = await fetch(API.checkpoint);
        const checkpoint = await response.json();
        renderCheckpoint(checkpoint);
    } catch (error) {
        console.error('Error fetching checkpoint:', error);
    }
}

async function fetchRunStatus() {
    try {
        const response = await fetch(API.status);
        const status = await response.json();
        updateRunStatus(status);
    } catch (error) {
        console.error('Error fetching status:', error);
    }
}

async function startRun() {
    const files = Array.from(state.selectedFiles);
    if (files.length === 0) {
        alert('Please select at least one file');
        return;
    }

    try {
        const response = await fetch(API.start, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                files: files,
                force: elements.forceReprocess.checked,
            }),
        });
        const result = await response.json();
        if (!result.success) {
            alert(result.message);
        }
    } catch (error) {
        console.error('Error starting run:', error);
        alert('Failed to start pipeline');
    }
}

async function pauseRun() {
    try {
        await fetch(API.pause, { method: 'POST' });
    } catch (error) {
        console.error('Error pausing:', error);
    }
}

async function resumeRun() {
    try {
        await fetch(API.resume, { method: 'POST' });
    } catch (error) {
        console.error('Error resuming:', error);
    }
}

async function stopRun() {
    try {
        await fetch(API.stop, { method: 'POST' });
    } catch (error) {
        console.error('Error stopping:', error);
    }
}

async function resetRun() {
    try {
        await fetch(API.reset, { method: 'POST' });
        fetchRunStatus();
    } catch (error) {
        console.error('Error resetting:', error);
    }
}

// ============================================================
// UI Rendering
// ============================================================
function renderFileList(files) {
    if (files.length === 0) {
        elements.fileList.innerHTML = `
            <div class="empty-state">
                <div class="icon">📭</div>
                <p>No EPUB files found in Data/</p>
            </div>
        `;
        return;
    }

    elements.fileList.innerHTML = files.map(file => `
        <label class="file-item" data-path="${file.path}">
            <input type="checkbox" class="file-checkbox" value="${file.path}">
            <span class="file-name" title="${file.name}">${file.name}</span>
            <span class="file-size">${file.size_mb} MB</span>
        </label>
    `).join('');

    // Add event listeners
    elements.fileList.querySelectorAll('.file-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', (e) => {
            const path = e.target.value;
            const item = e.target.closest('.file-item');

            if (e.target.checked) {
                state.selectedFiles.add(path);
                item.classList.add('selected');
            } else {
                state.selectedFiles.delete(path);
                item.classList.remove('selected');
            }

            updateControlButtons();
        });
    });
}

function updateStats(stats) {
    elements.statCharacters.textContent = stats.entities?.characters || 0;
    elements.statLocations.textContent = stats.entities?.locations || 0;
    elements.statFactions.textContent = stats.entities?.factions || 0;
    elements.statEvents.textContent = stats.entities?.timeline_events || 0;
    elements.statNodes.textContent = stats.graph?.nodes || 0;
    elements.statEdges.textContent = stats.graph?.edges || 0;
}

function renderCheckpoint(checkpoint) {
    if (!checkpoint.exists) {
        elements.checkpointInfo.innerHTML = '<div class="no-checkpoint">No active checkpoint</div>';
        return;
    }

    const progress = checkpoint.total_chapters > 0
        ? Math.round((checkpoint.completed_chapters / checkpoint.total_chapters) * 100)
        : 0;

    const errors = checkpoint.errors || [];

    elements.checkpointInfo.innerHTML = `
        <div class="checkpoint-item">
            <span class="checkpoint-label">Book</span>
            <span class="checkpoint-value">${checkpoint.book_title || checkpoint.book_id || 'Unknown'}</span>
        </div>
        <div class="checkpoint-item">
            <span class="checkpoint-label">Chapters</span>
            <span class="checkpoint-value">${checkpoint.completed_chapters || 0} / ${checkpoint.total_chapters || 0} (${progress}%)</span>
        </div>
        <div class="checkpoint-item">
            <span class="checkpoint-label">Entities</span>
            <span class="checkpoint-value">${checkpoint.entities_extracted || 0}</span>
        </div>
        <div class="checkpoint-item">
            <span class="checkpoint-label">Last Updated</span>
            <span class="checkpoint-value">${formatTime(checkpoint.last_updated)}</span>
        </div>
        ${errors.length > 0 ? `
        <div class="checkpoint-item" style="background: rgba(239, 68, 68, 0.1);">
            <span class="checkpoint-label" style="color: var(--error);">Errors</span>
            <span class="checkpoint-value" style="color: var(--error);">${errors.length}</span>
        </div>
        ` : ''}
    `;
}

function updateProgress(progress) {
    const stageText = progress.stage || 'Processing';
    const stageInfo = getStageInfo(stageText);

    elements.progressStage.textContent = `${stageInfo.icon} ${stageText}`;
    elements.progressStage.setAttribute('data-stage', stageInfo.type);
    elements.progressPercent.textContent = `${progress.percentage || 0}%`;
    elements.progressBar.style.width = `${progress.percentage || 0}%`;

    if (progress.message) {
        elements.progressMessage.textContent = progress.message;
    }
}

function getStageInfo(stage) {
    const lower = stage.toLowerCase();
    if (lower.includes('extract')) {
        return { icon: '🔍', type: 'extracting' };
    } else if (lower.includes('resolv') || lower.includes('alias')) {
        return { icon: '🔗', type: 'resolving' };
    } else if (lower.includes('summary') || lower.includes('description') || lower.includes('generat')) {
        return { icon: '📝', type: 'summarizing' };
    } else if (lower.includes('graph') || lower.includes('build')) {
        return { icon: '🕸️', type: 'building' };
    } else if (lower.includes('writ') || lower.includes('sav')) {
        return { icon: '💾', type: 'building' };
    } else if (lower.includes('index')) {
        return { icon: '📚', type: 'building' };
    } else if (lower.includes('complet')) {
        return { icon: '✅', type: 'complete' };
    } else if (lower.includes('load') || lower.includes('pars')) {
        return { icon: '📖', type: 'loading' };
    }
    return { icon: '⚡', type: 'default' };
}

function updateRunStatus(status) {
    state.runStatus = status.state;

    // Update badge
    elements.statusBadge.className = `status - badge status - ${status.state} `;
    elements.statusBadge.textContent = status.state.toUpperCase();

    // Update progress display
    if (status.current_stage) {
        elements.progressStage.textContent = status.current_stage;
    }

    if (status.progress_percent !== undefined) {
        elements.progressPercent.textContent = `${status.progress_percent}% `;
        elements.progressBar.style.width = `${status.progress_percent}% `;
    }

    if (status.message) {
        elements.progressMessage.textContent = status.message;
    }

    // Update token stats
    if (status.tokens) {
        updateTokenStats(status.tokens);
    }

    updateControlButtons();

    // Refresh stats and checkpoint on completion
    if (status.state === 'completed') {
        fetchStats();
        fetchCheckpoint();
    }
}

function updateTokenStats(tokens) {
    if (elements.tokenPrompt) {
        elements.tokenPrompt.textContent = formatNumber(tokens.total_prompt_tokens || 0);
    }
    if (elements.tokenOutput) {
        elements.tokenOutput.textContent = formatNumber(tokens.total_output_tokens || 0);
    }
    if (elements.tokenTotal) {
        elements.tokenTotal.textContent = formatNumber(tokens.total_tokens || 0);
    }
    if (elements.tokenCalls) {
        elements.tokenCalls.textContent = tokens.total_calls || 0;
    }
}

function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

function updateControlButtons() {
    const hasFiles = state.selectedFiles.size > 0;
    const isIdle = state.runStatus === 'idle' || state.runStatus === 'completed' || state.runStatus === 'error';
    const isRunning = state.runStatus === 'running';
    const isPaused = state.runStatus === 'paused';
    const isStopping = state.runStatus === 'stopping';

    // Start button
    elements.startBtn.disabled = !hasFiles || !isIdle;

    // Pause/Resume toggle
    if (isPaused) {
        elements.pauseBtn.textContent = '▶️ Resume';
        elements.pauseBtn.disabled = false;
        elements.pauseBtn.onclick = resumeRun;
    } else {
        elements.pauseBtn.textContent = '⏸️ Pause';
        elements.pauseBtn.disabled = !isRunning;
        elements.pauseBtn.onclick = pauseRun;
    }

    // Stop button
    elements.stopBtn.disabled = !(isRunning || isPaused);

    // If in completed/error state, show reset button behavior
    if (state.runStatus === 'completed' || state.runStatus === 'error') {
        elements.startBtn.textContent = '🔄 Reset & Start';
        elements.startBtn.onclick = async () => {
            await resetRun();
            await startRun();
        };
    } else {
        elements.startBtn.textContent = '▶️ Start';
        elements.startBtn.onclick = startRun;
    }
}

function addLogEntry(progress) {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    const message = progress.message
        ? `${progress.stage} - ${progress.message} `
        : progress.stage;

    const entry = document.createElement('div');
    entry.className = `log - entry ${progress.stage ? 'stage' : ''} `;
    entry.innerHTML = `
        < span class="log-time" > ${time}</span >
            <span class="log-message">${message}</span>
    `;

    // Keep only last 50 entries
    if (elements.logPanel.children.length > 50) {
        elements.logPanel.removeChild(elements.logPanel.firstChild);
    }

    elements.logPanel.appendChild(entry);
    elements.logPanel.scrollTop = elements.logPanel.scrollHeight;
}

// ============================================================
// Utility Functions
// ============================================================
function formatTime(isoString) {
    if (!isoString) return '-';
    try {
        const date = new Date(isoString);
        return date.toLocaleString();
    } catch {
        return isoString;
    }
}

// ============================================================
// Event Listeners
// ============================================================
elements.refreshFilesBtn.addEventListener('click', fetchFiles);
elements.refreshCheckpointBtn.addEventListener('click', fetchCheckpoint);
elements.startBtn.addEventListener('click', startRun);
elements.pauseBtn.addEventListener('click', pauseRun);
elements.stopBtn.addEventListener('click', stopRun);

// ============================================================
// Initialization
// ============================================================
async function init() {
    // Load initial data
    await Promise.all([
        fetchFiles(),
        fetchStats(),
        fetchCheckpoint(),
        fetchRunStatus(),
    ]);

    // Connect WebSocket
    connectWebSocket();

    // Periodic refresh
    setInterval(fetchStats, 30000);
    setInterval(fetchCheckpoint, 10000);
}

// Start the app
init();
