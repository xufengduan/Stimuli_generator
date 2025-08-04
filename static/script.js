// Global variables
const generateButton = document.getElementById('generate_button');
const stopButton = document.getElementById('stop_button');
const clearButton = document.getElementById('clear_button');
const progressBar = document.getElementById('progress_bar');
const itemsContainer = document.getElementById('items-container');
const agent2Table = document.getElementById("agent2PropertiesTable");
const addAgent2Button = document.getElementById("add_agent_2_property_button");
const agent3PropertiesTable = document.getElementById('agent3PropertiesTable');
const addAgent3Button = document.getElementById('add_agent_3_property_button');
const modelChoice = document.getElementById('model_choice');
const apiKeyInput = document.getElementById('api_key');
const generationStatus = document.getElementById('generation_status'); // Get generation status element
const autoGenerateButton = document.getElementById('auto_generate_button'); // Get AutoGenerate button element

// Log display related elements
const generatorLog = document.getElementById('generator-log');
const validatorLog = document.getElementById('validator-log');
const scorerLog = document.getElementById('scorer-log');

// Get session ID from URL
const sessionId = window.location.pathname.split('/')[1];
console.log(`Using session ID: ${sessionId}`);

// Global socket variables
let socket;
let socketInitialized = false; // Flag variable to track if Socket is initialized
let socketReconnectAttempts = 0; // Track reconnection attempts
let socketReconnectTimer = null;
let socketBackoffDelay = 1000; // Initial backoff delay
const maxBackoffDelay = 30000; // Maximum backoff delay (30 seconds)
let socketConnectionInProgress = false;
const maxReconnectAttempts = 20; // Maximum reconnection attempts

// Prompt template for AutoGenerate properties
const autoGeneratePromptTemplate = `Based on the experimental design and the example stimuli provided below, please complete the following tasks:
1. Identify the experimental conditions associated with each stimulus.
2. Specify the requirements that each stimulus must fulfill according to the design constraints.
3. Propose scoring dimensions that should be used to evaluate the quality of each stimulus item.

<Example>
Experimental Design:
This experiment investigates whether individuals tend to prefer shorter words in predictive linguistic contexts.
Each stimulus item consists of a word pair and two sentence contexts:
- The two words differ in length, with the shorter being an abbreviation of the longer. They are semantically equivalent and commonly used interchangeably in everyday English (e.g., chimp/chimpanzee, math/mathematics, TV/television).
- Word pairs that form common multi-word expressions (e.g., final exam) are excluded.
- The target word is omitted at the end of both sentence contexts:
- One is a neutral context, which does not predict the target word.
- The other is a supportive context, which strongly predicts the target word.
- Both contexts are matched in length and plausibility.

Stimuli Examples:
- Stimulus 1:
word_pair: math / mathematics
neutral_context: Susan introduced herself as someone who loved…
supportive_context: Susan was very bad at algebra, so she hated…
- Stimulus 2:
word_pair: bike / bicycle
neutral_context: Last week John finally bought himself a…
supportive_context: For commuting to work, John got a new…

Expected Response Format:
Components:
["word_pair", "neutral_context", "supportive_context"]

Requirements:
{
  "Synonymy": "Do the two words convey the same meaning?",
  "Abbreviation": "Is the shorter word an abbreviation of the longer word?",
  "Shared morpheme": "Do both words share a common morpheme?",
  "Not Phrase": "Is neither word part of a multi-word phrase?",
  "Real Word": "Are both words attested and used in natural English?",
  "Short-Long Order": "Is the shorter word listed first in the pair?",
  "Neutral Context Unpredictive": "Is the neutral context truly non-predictive of the target word?",
  "Supportive Context Predictive": "Does the supportive context reliably elicit the target word?"
}

Scoring Dimensions:
{
  "unpredictability_neutral": "Degree to which the neutral context fails to predict the target (higher = more unpredictable; from 0 to 10)",
  "predictability_supportive": "Degree to which the supportive context cues the target (higher = more predictable; from 0 to 10)",
  "word_pair_frequency": "Frequency with which the two words are used interchangeably(higher = more frequent; from 0 to 10)",
  "word_frequency_short": "Corpus frequency of the short word(higher = more frequent; from 0 to 10)",
  "word_frequency_long": "Corpus frequency of the long word(higher = more frequent; from 0 to 10)",
  "neutral_context_plausibility": "Realism and coherence of the neutral context(higher = more plausible; from 0 to 10)",
  "supportive_context_plausibility": "Realism and coherence of the supportive context(higher = more plausible; from 0 to 10)"
}
</Example>

Task for New Experiment
Experimental Design:
{Experimental design}

Example Stimuli:
{Example stimuli}

Your Task:
Using the format illustrated above, please:
1. Identify the conditions represented in each stimulus item.
2. List the requirements for a valid stimulus pair in this experiment.
3. Propose a set of scoring dimensions to evaluate stimulus quality and conformity to design.
4. A valid stimulus must meet all the listed requirements. That is, each requirement must evaluate to TRUE. Stimuli that violate any single requirement are to be considered non-compliant with the experimental design.
5. Response me based on the expected format, without any introductary words.`;

// Initialise WebSocket connection
function initializeSocket() {
    // Prevent multiple connection attempts simultaneously
    if (socketConnectionInProgress) {
        console.log("WebSocket connection attempt already in progress, skipping");
        return;
    }

    socketConnectionInProgress = true;

    // If Socket exists, try to close the old connection
    if (socket) {
        try {
            // Remove all event listeners to avoid duplication
            socket.off('connect');
            socket.off('connect_error');
            socket.off('disconnect');
            socket.off('reconnect_attempt');
            socket.off('reconnect');
            socket.off('reconnect_failed');
            socket.off('progress_update');
            socket.off('stimulus_update');
            socket.off('server_status');
            socket.off('error');

            // If connected, disconnect first
            if (socket.connected) {
                console.log("Closing existing WebSocket connection...");
                socket.disconnect();
            }
        } catch (e) {
            console.error("Error closing old WebSocket connection:", e);
        }
    }

    // Clear all existing reconnection timers
    if (socketReconnectTimer) {
        clearTimeout(socketReconnectTimer);
        socketReconnectTimer = null;
    }

    socketInitialized = false; // Reset initialization flag

    // Get current page URL and protocol
    const currentUrl = window.location.origin;
    const isSecure = window.location.protocol === 'https:';

    // Create configuration object, add query parameters including session ID
    const socketOptions = {
        path: '/socket.io',
        transports: ['polling', 'websocket'],  // Start with polling, then upgrade to websocket
        reconnectionAttempts: 3,               // Reduced reconnection attempts
        reconnectionDelay: 2000,               // Longer initial delay
        reconnectionDelayMax: 10000,           // Longer max delay
        timeout: 10000,                        // Shorter timeout
        forceNew: true,                        // Force new connection
        autoConnect: true,                     // Auto connect
        query: { 'session_id': sessionId },    // Add session ID to query parameters
        upgrade: true,                         // Allow transport upgrade
        rememberUpgrade: false,                // Don't remember upgrade to avoid issues
    };

    console.log(`Connecting to Socket.IO: ${currentUrl}, Session ID: ${sessionId}`);

    try {
        // Create Socket.IO connection with error handling
        socket = io(currentUrl, socketOptions);

        // Add a timeout to detect connection issues
        const connectionTimeout = setTimeout(() => {
            if (!socket.connected) {
                console.warn("Socket.IO connection timeout after 10 seconds");
                // Force connection status update
                socketConnectionInProgress = false;
                handleReconnect();
            }
        }, 10000);

        // Connection event handling
        socket.on('connect', () => {
            // Clear connection timeout
            clearTimeout(connectionTimeout);

            console.log('WebSocket connection successful!', socket.id);
            socketInitialized = true; // Set initialization complete flag
            socketReconnectAttempts = 0; // Reset reconnection counter
            socketBackoffDelay = 1000; // Reset backoff delay
            socketConnectionInProgress = false; // Reset connection in progress flag

            // Join session room after connection is established
            setTimeout(() => {
                try {
                    socket.emit('join_session', { session_id: sessionId });
                    console.log('Sent join_session request for:', sessionId);
                } catch (e) {
                    console.warn("Failed to send join_session:", e);
                }
            }, 100);

            // Add ping to verify connection is working
            setTimeout(() => {
                try {
                    socket.emit('ping', { time: Date.now() });
                } catch (e) {
                    console.warn("Failed to send ping after connect:", e);
                }
            }, 1000);
        });

        socket.on('connect_error', (error) => {
            console.error('WebSocket connection error:', error);
            socketInitialized = false; // Reset flag on connection error
            socketConnectionInProgress = false; // Reset connection in progress flag

            // Use exponential backoff strategy for reconnection
            handleReconnect();
        });

        socket.on('error', (error) => {
            console.error('WebSocket error:', error);
            socketConnectionInProgress = false; // Reset connection in progress flag
        });

        socket.on('disconnect', (reason) => {
            console.log(`WebSocket disconnected: ${reason}`);
            socketInitialized = false; // Reset flag on disconnection
            socketConnectionInProgress = false; // Reset connection in progress flag

            // If disconnection reason is not client-initiated, try to reconnect
            if (reason !== 'io client disconnect' && reason !== 'io server disconnect') {
                // Use exponential backoff strategy for reconnection
                handleReconnect();
            }
        });

        socket.on('reconnect_attempt', (attemptNumber) => {
            console.log(`Attempting reconnection (${attemptNumber})...`);
            socketReconnectAttempts = attemptNumber;
        });

        socket.on('reconnect', (attemptNumber) => {
            console.log(`Reconnection successful, attempts: ${attemptNumber}`);
            socketInitialized = true; // Restore flag on successful reconnection
            socketReconnectAttempts = 0; // Reset reconnection counter
            socketBackoffDelay = 1000; // Reset backoff delay
        });

        socket.on('reconnect_failed', () => {
            console.error('WebSocket reconnection failed after maximum attempts');
            socketInitialized = false; // Reset flag on reconnection failure
            socketConnectionInProgress = false; // Reset connection in progress flag

            // Use our own reconnection strategy
            handleReconnect();
        });

        // Listen for progress_update event, update progress bar
        socket.on('progress_update', (data) => {
            console.log('Received progress update:', data);
            if (data.session_id === sessionId) {
                updateProgress(data.progress);
            }
        });

        // Listen for stimulus_update event, update logs
        socket.on('stimulus_update', (data) => {
            console.log('Received stimulus update:', data);
            if (data.session_id === sessionId) {
                handleLogMessage(data.type, data.message);
            }
        });

        // Listen for server_status event
        socket.on('server_status', (data) => {
            console.log('Received server status:', data);
            // Handle server status messages
        });

        // Add ping/pong handler for connection monitoring
        socket.on('pong', (data) => {
            const roundTripTime = Date.now() - (data.time || 0);
            console.log(`Received pong response, round-trip time: ${roundTripTime}ms`);

            // Schedule next ping to keep connection alive
            setTimeout(() => {
                if (socket && socket.connected) {
                    try {
                        socket.emit('ping', { time: Date.now() });
                    } catch (e) {
                        console.warn("Failed to send ping:", e);
                    }
                }
            }, 30000); // Send ping every 30 seconds
        });

    } catch (e) {
        console.error("Error creating WebSocket connection:", e);
        socketConnectionInProgress = false; // Reset connection in progress flag

        // Use exponential backoff strategy for reconnection
        handleReconnect();
    }
}

// Add exponential backoff reconnection handler
function handleReconnect() {
    // Clear any existing reconnection timer
    if (socketReconnectTimer) {
        clearTimeout(socketReconnectTimer);
        socketReconnectTimer = null;
    }

    // Increment reconnection attempts counter
    socketReconnectAttempts++;

    // Check if we've reached the maximum number of attempts
    if (socketReconnectAttempts > maxReconnectAttempts) {
        console.error(`Maximum reconnection attempts (${maxReconnectAttempts}) reached, stopping`);
        // Show a user-friendly message in the UI
        appendLogMessage(generatorLog, "WebSocket connection lost. Please refresh the page.", "error");
        appendLogMessage(validatorLog, "WebSocket connection lost. Please refresh the page.", "error");
        appendLogMessage(scorerLog, "WebSocket connection lost. Please refresh the page.", "error");
        return;
    }

    // Calculate exponential backoff delay with jitter
    // Add random jitter (±20%) to prevent reconnection storms
    const jitterFactor = 0.8 + (Math.random() * 0.4); // Random value between 0.8 and 1.2
    const baseDelay = socketBackoffDelay * Math.pow(1.5, socketReconnectAttempts - 1);
    const delay = Math.min(baseDelay * jitterFactor, maxBackoffDelay);

    console.log(`Scheduling reconnection attempt ${socketReconnectAttempts} in ${Math.round(delay)}ms`);

    // Set a timer for the next reconnection attempt
    socketReconnectTimer = setTimeout(() => {
        console.log(`Executing reconnection attempt ${socketReconnectAttempts}`);

        // Reset connection flag to allow a new connection attempt
        socketConnectionInProgress = false;

        // Try to reconnect
        try {
            // For later reconnection attempts, try to recreate the socket from scratch
            if (socketReconnectAttempts > 2 && socket) {
                try {
                    // Force close and cleanup
                    socket.close();
                    socket.disconnect();
                    socket = null;
                } catch (e) {
                    console.warn("Error during socket cleanup:", e);
                }
            }

            // Initialize a new socket connection
            initializeSocket();
        } catch (e) {
            console.error("Error during reconnection:", e);
            // If reconnection fails, schedule another attempt
            socketConnectionInProgress = false;
            handleReconnect();
        }
    }, delay);
}

// Check WebSocket connection status
function checkSocketConnection() {
    if (!socket || !socket.connected) {
        console.log("WebSocket not connected, reinitializing...");
        socketInitialized = false;

        // Only initialize if no connection attempt is in progress
        if (!socketConnectionInProgress) {
            initializeSocket();
        }
        return false;
    }
    return true;
}

// Ensure WebSocket connection and wait for connection establishment before executing callback
function ensureSocketConnection(callback, maxWaitTime = 5000) {
    // If WebSocket is already connected, execute callback directly
    if (socket && socket.connected) {
        console.log("WebSocket already connected, executing operation");
        callback();
        return;
    }

    console.log("WebSocket not connected, attempting reconnection...");

    // Reset retry counters
    socketReconnectAttempts = 0;
    socketBackoffDelay = 1000;

    // Set retry counter
    let retryCount = 0;
    const maxRetries = 3;

    // Create retry function
    function attemptConnection() {
        retryCount++;
        console.log(`Connection attempt ${retryCount}/${maxRetries}...`);

        // Reinitialize WebSocket connection
        socketConnectionInProgress = false; // Ensure new connection can be made
        initializeSocket();

        // Wait for connection establishment timeout
        const timeoutId = setTimeout(() => {
            console.warn(`WebSocket connection timeout (attempt ${retryCount}/${maxRetries})`);

            // If there are remaining retries, continue attempting
            if (retryCount < maxRetries) {
                attemptConnection();
            } else {
                console.error("WebSocket connection failed, attempting to continue operation");
                // Try to continue execution to maintain user experience
                callback();
            }
        }, maxWaitTime);

        // Listen for successful connection event
        socket.once('connect', () => {
            clearTimeout(timeoutId); // Clear timeout timer
            console.log("WebSocket connection successful");

            // Wait for server_status confirmation to ensure room join success
            const roomConfirmTimeoutId = setTimeout(() => {
                console.warn("No room confirmation received, continuing operation");
                // Brief delay to ensure event listeners are registered
                setTimeout(callback, 200);
            }, 1000);

            // Add one-time listener for server_status message
            socket.once('server_status', (data) => {
                clearTimeout(roomConfirmTimeoutId);
                console.log("Received server status confirmation:", data);

                if (data.room_joined) {
                    console.log("Successfully joined room:", data.session_id);
                } else {
                    console.warn("Failed to join room or no room information provided");
                }

                // Brief delay to ensure event listeners are registered
                setTimeout(callback, 200);
            });
        });
    }

    // Start first connection attempt
    attemptConnection();
}

// Handle log messages
function handleLogMessage(type, message) {
    switch (type) {
        case 'generator':
            appendLogMessage(generatorLog, message);
            break;
        case 'validator':
            appendLogMessage(validatorLog, message);
            break;
        case 'scorer':
            appendLogMessage(scorerLog, message);
            break;
        case 'all':
            // Send to all log panels
            appendLogMessage(generatorLog, message);
            appendLogMessage(validatorLog, message);
            appendLogMessage(scorerLog, message);
            break;
        case 'setup':
            // Send message to Console only
            console.log('Setup:', message);
            break;
        case 'error':
            // Send error messages to all panels with error style
            appendLogMessage(generatorLog, message, 'error');
            appendLogMessage(validatorLog, message, 'error');
            appendLogMessage(scorerLog, message, 'error');
            break;
        default:
            console.log('Unknown message type:', type, message);
    }
}

// Clear log function
function clearLog(logId) {
    const logElement = document.getElementById(logId);
    if (logElement) {
        logElement.innerHTML = '';
    }
}

// Add log message to panel
function appendLogMessage(logElement, message, className = '') {
    // Create message container
    const logMessage = document.createElement('div');

    // Determine message type based on content and className
    let messageType = className || 'info';
    if (message.toLowerCase().includes('error') || message.toLowerCase().includes('failed')) {
        messageType = 'error';
    } else if (message.toLowerCase().includes('passed') || message.toLowerCase().includes('completed') || message.toLowerCase().includes('success')) {
        messageType = 'success';
    } else if (message.toLowerCase().includes('warning') || message.toLowerCase().includes('early rejection') || message.toLowerCase().includes('regenerating')) {
        messageType = 'warning';
    }

    logMessage.className = `log-message ${messageType}`;

    // Add timestamp
    const timestamp = new Date().toLocaleTimeString();
    const timestampElement = document.createElement('div');
    timestampElement.className = 'log-timestamp';
    timestampElement.textContent = timestamp;

    // Create text container
    const textElement = document.createElement('div');
    textElement.className = 'log-text';

    // Format message content
    if (message.includes('=== No.')) {
        // Use special style for round information
        textElement.innerHTML = `<span class="message-round">${message}</span>`;
    } else if (message.includes('Output:')) {
        // Agent output, try to format JSON
        try {
            const parts = message.split('Output:');
            const prefix = parts[0];
            const jsonText = parts[1].trim();

            // Try to format JSON
            if (jsonText.startsWith('{') && jsonText.endsWith('}')) {
                const formattedJson = formatJson(jsonText);
                textElement.innerHTML = `<span class="message-output">${prefix}Output:</span><br>${formattedJson}`;
            } else {
                textElement.innerHTML = `<span class="message-output">${message}</span>`;
            }
        } catch (e) {
            textElement.innerHTML = `<span class="message-output">${message}</span>`;
        }
    } else {
        // General message
        textElement.innerHTML = `<span class="message-output">${message}</span>`;
    }

    // Append timestamp and text to message container
    logMessage.appendChild(timestampElement);
    logMessage.appendChild(textElement);

    // Add to log panel
    logElement.appendChild(logMessage);

    // Scroll to bottom
    logElement.scrollTop = logElement.scrollHeight;
}

// Format JSON string
function formatJson(jsonString) {
    try {
        const obj = JSON.parse(jsonString);
        return syntaxHighlight(obj);
    } catch (e) {
        return jsonString;
    }
}

// JSON syntax highlighting
function syntaxHighlight(json) {
    if (typeof json != 'string') {
        json = JSON.stringify(json, undefined, 2);
    }

    json = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return json.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
        let cls = 'json-number';
        if (/^"/.test(match)) {
            if (/:$/.test(match)) {
                cls = 'json-key';
            } else {
                cls = 'json-string';
            }
        } else if (/true|false/.test(match)) {
            cls = 'json-boolean';
        } else if (/null/.test(match)) {
            cls = 'json-null';
        }
        return '<span class="' + cls + '">' + match + '</span>';
    });
}

// Clear log display area
function clearLogs() {
    generatorLog.innerHTML = '';
    validatorLog.innerHTML = '';
    scorerLog.innerHTML = '';
}

// Get API URL prefix with session ID
function getApiUrl(endpoint) {
    return `/${sessionId}/${endpoint}`;
}

// Page initialization function
function initializePage() {
    // Ensure Stop button is disabled by default
    stopButton.disabled = true;

    // Ensure all other buttons and input elements are enabled
    generateButton.disabled = false;
    clearButton.disabled = false;
    addAgent2Button.disabled = false;
    addAgent3Button.disabled = false;

    // Determine API key input availability based on default model selection
    handleModelChange();

    // Ensure progress bar is at 0%
    updateProgress(0);

    // Initialize WebSocket connection
    initializeSocket();

    // Start periodic connection check
    periodicSocketCheck();

    // Set up UI protection mechanism
    setupUIProtection();

    // Display session ID in console for debugging
    console.log(`Initialized page with session ID: ${sessionId}`);
}

// Handle model switching function
function handleModelChange() {
    const modelSelect = document.getElementById('model_choice');
    const customModelConfig = document.getElementById('custom_model_config');
    const apiKeyInput = document.getElementById('api_key');

    if (modelSelect.value === 'custom') {
        customModelConfig.style.display = 'block';
        apiKeyInput.disabled = false;
        apiKeyInput.required = true;
        apiKeyInput.placeholder = 'Enter your API Key';
    } else if (modelSelect.value === 'GPT-4o') {
        customModelConfig.style.display = 'none';
        apiKeyInput.disabled = false;
        apiKeyInput.required = true;
        apiKeyInput.placeholder = 'Enter your OpenAI API Key';
    } else {
        customModelConfig.style.display = 'none';
        apiKeyInput.disabled = false;
        apiKeyInput.required = true;
        apiKeyInput.placeholder = 'API Key required';
    }
}

// Initial setup: Add event listeners for the first Item's buttons
document.querySelector('.add-component-btn').addEventListener('click', addComponentToAllItems);
document.querySelector('.delete-component-btn').addEventListener('click', deleteComponentFromAllItems);
document.querySelector('.add-item-btn').addEventListener('click', addNewItem);

// Add model selection listener
modelChoice.addEventListener('change', handleModelChange);

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializePage);

// Initialize model selection state
handleModelChange();

// Validate whether AutoGenerate required inputs are filled correctly
function validateAutoGenerateInputs() {
    const selectedModel = modelChoice.value;
    const apiKey = document.getElementById('api_key').value.trim();
    const experimentDesign = document.getElementById('experiment_design').value.trim();

    // Check if a model is selected
    if (!selectedModel) {
        alert('Please select a model!');
        return false;
    }

    // If GPT-4o is selected, check API Key
    if (selectedModel === 'GPT-4o' && !apiKey) {
        alert('OpenAI API Key cannot be empty when using GPT-4o!');
        return false;
    }

    // If custom model is selected, check API Key, URL, and model name
    if (selectedModel === 'custom') {
        const apiUrl = document.getElementById('custom_api_url').value.trim();  // Fixed field ID
        const modelName = document.getElementById('custom_model_name').value.trim();  // Add model name validation
        if (!apiKey) {
            alert('API Key cannot be empty when using custom model!');
            return false;
        }
        if (!modelName) {  // Add model name validation
            alert('Model Name cannot be empty when using custom model!');
            return false;
        }
        if (!apiUrl) {
            alert('API URL cannot be empty when using custom model!');
            return false;
        }

        // Validate custom parameters if provided
        const customParams = document.getElementById('custom_params').value.trim();
        if (customParams) {
            try {
                JSON.parse(customParams);
            } catch (e) {
                alert('Invalid JSON in custom parameters!');
                return false;
            }
        }
    }

    // Check experimental design
    if (!experimentDesign) {
        alert('Stimulus design cannot be empty!');
        return false;
    }

    // Check input in Item tables
    const itemContainers = document.querySelectorAll('.item-container');
    if (itemContainers.length === 0) {
        alert('At least one example stimulus item is required!');
        return false;
    }

    // Check if all example items are filled correctly
    for (let i = 0; i < itemContainers.length; i++) {
        const tbody = itemContainers[i].querySelector('.stimuli-table tbody');
        const rows = tbody.getElementsByTagName('tr');

        if (rows.length === 0) {
            alert(`No component rows in Example Item ${i + 1}!`);
            return false;
        }

        for (let j = 0; j < rows.length; j++) {
            const typeCell = rows[j].querySelector('.type-column input');
            const contentCell = rows[j].querySelector('.content-column input');

            if (typeCell && contentCell) {
                const typeValue = typeCell.value.trim();
                const contentValue = contentCell.value.trim();

                if (!typeValue || !contentValue) {
                    alert(`All "Components" and "Content" fields in Item ${i + 1} must be filled!`);
                    return false;
                }
            }
        }
    }

    return true;
}

// Collect data from Example Stimuli tables
function collectExampleStimuli() {
    const stimuli = [];
    const itemContainers = document.querySelectorAll('.item-container');

    itemContainers.forEach((itemContainer, index) => {
        const tbody = itemContainer.querySelector('.stimuli-table tbody');
        const rows = tbody.getElementsByTagName('tr');
        const itemData = {};

        for (let i = 0; i < rows.length; i++) {
            const typeCell = rows[i].querySelector('.type-column input');
            const contentCell = rows[i].querySelector('.content-column input');

            if (typeCell && contentCell) {
                const type = typeCell.value.trim();
                const content = contentCell.value.trim();

                if (type && content) {
                    itemData[type] = content;
                }
            }
        }

        // Only add to stimuli array when itemData is not empty
        if (Object.keys(itemData).length > 0) {
            stimuli.push(itemData);
        }
    });

    return stimuli;
}

// Add new component row to all tables
function addComponentToAllItems() {
    const tables = document.querySelectorAll('.stimuli-table tbody');
    tables.forEach(tbody => {
        const newRow = document.createElement('tr');
        newRow.innerHTML = `
            <td class="type-column"><input type="text" placeholder="Enter new component"></td>
            <td class="content-column"><input type="text" placeholder="Enter component's content"></td>
        `;
        tbody.appendChild(newRow);
    });
}

// Delete last component row from all tables
function deleteComponentFromAllItems() {
    const tables = document.querySelectorAll('.stimuli-table tbody');
    tables.forEach(tbody => {
        const rows = tbody.getElementsByTagName('tr');
        if (rows.length > 1) { // Ensure at least one row is kept
            tbody.removeChild(rows[rows.length - 1]);
        }
    });
}

// Add new Item
function addNewItem() {
    // Get current newest Item number and calculate new Item number
    const itemContainers = document.querySelectorAll('.item-container');
    const lastItem = itemContainers[itemContainers.length - 1];
    const lastItemId = lastItem.id;
    const lastItemNumber = parseInt(lastItemId.split('-')[1]);
    const newItemNumber = lastItemNumber + 1;

    // Get current table row count
    const lastItemTable = lastItem.querySelector('.stimuli-table tbody');
    const rowCount = lastItemTable.rows.length;

    // Create new Item container
    const newItem = document.createElement('div');
    newItem.className = 'item-container';
    newItem.id = `item-${newItemNumber}`;

    // Create Item title
    const itemTitle = document.createElement('div');
    itemTitle.className = 'item-title';
    itemTitle.textContent = `Item ${newItemNumber}`;
    newItem.appendChild(itemTitle);

    // Create table
    const table = document.createElement('table');
    table.className = 'stimuli-table';

    // Add table header
    const thead = document.createElement('thead');
    thead.innerHTML = `
        <tr>
            <th class="type-column">Components</th>
            <th class="content-column">Content</th>
        </tr>
    `;
    table.appendChild(thead);

    // Add table content
    const tbody = document.createElement('tbody');
    for (let i = 0; i < rowCount; i++) {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="type-column"><input type="text" placeholder="Enter new component"></td>
            <td class="content-column"><input type="text" placeholder="Enter component's content"></td>
        `;
        tbody.appendChild(row);
    }
    table.appendChild(tbody);
    newItem.appendChild(table);

    // Add buttons
    const buttonDiv = document.createElement('div');
    buttonDiv.className = 'item-buttons-row';
    buttonDiv.innerHTML = `
        <div class="left-buttons">
            <button class="add-component-btn">Add component</button>
            <button class="delete-component-btn">Delete component</button>
        </div>
        <div class="right-buttons">
            <button class="add-item-btn">Add item</button>
            <button class="delete-item-btn">Delete item</button>
        </div>
    `;
    newItem.appendChild(buttonDiv);

    // Remove buttons from previous Item container
    lastItem.querySelector('.item-buttons-row').remove();

    // Add new Item to container
    itemsContainer.appendChild(newItem);

    // Add event listeners for new buttons
    newItem.querySelector('.add-component-btn').addEventListener('click', addComponentToAllItems);
    newItem.querySelector('.delete-component-btn').addEventListener('click', deleteComponentFromAllItems);
    newItem.querySelector('.add-item-btn').addEventListener('click', addNewItem);
    newItem.querySelector('.delete-item-btn').addEventListener('click', function () {
        deleteItem(newItem.id);
    });
}

// Delete Item
function deleteItem(itemId) {
    const itemToDelete = document.getElementById(itemId);
    const itemContainers = document.querySelectorAll('.item-container');

    // If there's only one Item, don't perform delete operation
    if (itemContainers.length <= 1) {
        return;
    }

    // Get position of Item to be deleted
    let itemIndex = -1;
    for (let i = 0; i < itemContainers.length; i++) {
        if (itemContainers[i].id === itemId) {
            itemIndex = i;
            break;
        }
    }

    // If it's the last Item, need to add buttons to previous Item
    if (itemIndex === itemContainers.length - 1) {
        const previousItem = itemContainers[itemIndex - 1];
        const buttonDiv = document.createElement('div');
        buttonDiv.className = 'item-buttons-row';

        // If it's Item 1, no Delete item button needed
        if (previousItem.id === 'item-1') {
            buttonDiv.innerHTML = `
                <div class="left-buttons">
                    <button class="add-component-btn">Add component</button>
                    <button class="delete-component-btn">Delete component</button>
                </div>
                <div class="right-buttons">
                    <button class="add-item-btn">Add item</button>
                </div>
            `;
        } else {
            buttonDiv.innerHTML = `
                <div class="left-buttons">
                    <button class="add-component-btn">Add component</button>
                    <button class="delete-component-btn">Delete component</button>
                </div>
                <div class="right-buttons">
                    <button class="add-item-btn">Add item</button>
                    <button class="delete-item-btn">Delete item</button>
                </div>
            `;
        }

        previousItem.appendChild(buttonDiv);

        // Add event listeners for new buttons
        previousItem.querySelector('.add-component-btn').addEventListener('click', addComponentToAllItems);
        previousItem.querySelector('.delete-component-btn').addEventListener('click', deleteComponentFromAllItems);
        previousItem.querySelector('.add-item-btn').addEventListener('click', addNewItem);

        const deleteItemBtn = previousItem.querySelector('.delete-item-btn');
        if (deleteItemBtn) {
            deleteItemBtn.addEventListener('click', function () {
                deleteItem(previousItem.id);
            });
        }
    }

    // Delete Item
    itemToDelete.remove();
}

// Collect data from all Item tables
function collectItemsData() {
    const stimuli = [];
    const itemContainers = document.querySelectorAll('.item-container');

    itemContainers.forEach(itemContainer => {
        const tbody = itemContainer.querySelector('.stimuli-table tbody');
        const rows = tbody.getElementsByTagName('tr');
        const itemData = {};

        for (let i = 0; i < rows.length; i++) {
            const typeCell = rows[i].querySelector('.type-column input');
            const contentCell = rows[i].querySelector('.content-column input');

            if (typeCell && contentCell) {
                const type = typeCell.value.trim();
                const content = contentCell.value.trim();

                if (type && content) {
                    itemData[type] = content;
                }
            }
        }

        // Only add to stimuli array when itemData is not empty
        if (Object.keys(itemData).length > 0) {
            stimuli.push(itemData);
        }
    });

    return stimuli;
}


// This event listener was removed since we now have individual delete buttons for each row

// Show generating status text
function showGeneratingStatus() {
    generationStatus.textContent = "Generating...";
    generationStatus.className = "generation-status generating";
    generationStatus.style.display = "inline-block";
}

// Show checking status text
function showCheckingStatus() {
    generationStatus.textContent = "Scoring & Checking status & Creating file...";
    generationStatus.className = "generation-status checking";
    generationStatus.style.display = "inline-block";
}

// Hide status text
function hideGenerationStatus() {
    generationStatus.style.display = "none";
    generationStatus.textContent = "";
}

// Update progress bar
function updateProgress(progress) {
    console.log(`Updating progress bar to ${progress}%`);

    // Ensure progress value is a number
    if (typeof progress !== 'number') {
        try {
            progress = parseFloat(progress);
        } catch (e) {
            console.error("Invalid progress value:", progress);
            return;
        }
    }

    // Progress value should be between 0-100
    progress = Math.max(0, Math.min(100, progress));

    // Round to integer
    const roundedProgress = Math.round(progress);

    // Get current progress
    let currentProgressText = progressBar.style.width || '0%';
    let currentProgress = parseInt(currentProgressText.replace('%', ''), 10) || 0;

    // For special cases:
    // 1. If current progress is already 100%, no updates are accepted (unless explicitly reset to 0%)
    if (currentProgress >= 100 && roundedProgress > 0) {
        console.log(`Progress already at 100%, ignoring update to ${roundedProgress}%`);
        return;
    }

    // 2. If the received progress is less than the current progress and the difference is more than 10%, it may be a new generation process
    //    At this time, we accept the smaller progress value
    const progressDifference = currentProgress - roundedProgress;
    if (progressDifference > 10 && roundedProgress <= 20) {
        console.log(`Accepting progress ${roundedProgress}% as start of new generation`);
        currentProgress = 0; // Reset progress
    }
    // 3. Otherwise, if the received progress is less than the current progress, ignore it (unless it's 0% to indicate reset)
    else if (roundedProgress < currentProgress && roundedProgress > 0) {
        console.log(`Ignoring backward progress update: ${roundedProgress}% < ${currentProgress}%`);
        return;
    }

    // Update progress display
    progressBar.style.width = `${roundedProgress}%`;
    document.getElementById('progress_percentage').textContent = `${roundedProgress}%`;

    console.log(`Progress bar updated to ${roundedProgress}%`);

    // When progress reaches 100%, switch status text
    if (roundedProgress >= 100) {
        showCheckingStatus();
    }

    // Enable/disable buttons
    if (roundedProgress > 0 && roundedProgress < 100) {
        // In progress
        generateButton.disabled = true;
        stopButton.disabled = false;
    } else if (roundedProgress >= 100) {
        // Completed
        generateButton.disabled = false;
        stopButton.disabled = true;
    }
}

function resetUI() {
    // Hide generating status text
    hideGenerationStatus();

    // Enable all buttons
    generateButton.disabled = false;
    clearButton.disabled = false;
    stopButton.disabled = true; // Stop button remains disabled

    // Enable all table-related buttons
    addAgent2Button.disabled = false;
    addAgent3Button.disabled = false;

    // Enable Add/Delete buttons in all tables
    document.querySelectorAll('.add-component-btn, .delete-component-btn, .add-item-btn, .delete-item-btn').forEach(btn => {
        btn.disabled = false;
    });

    // Enable model selection dropdown
    document.getElementById('model_choice').disabled = false;

    // Determine whether API Key input box is available based on the currently selected model
    const selectedModel = document.getElementById('model_choice').value;
    if (selectedModel === 'GPT-4o') {
        document.getElementById('api_key').disabled = false;
    } else {
        document.getElementById('api_key').disabled = true;
    }

    // Enable all other input boxes and text areas
    document.getElementById('iteration').disabled = false;
    document.getElementById('experiment_design').disabled = false;

    // Enable all input boxes in all tables
    document.querySelectorAll('input[type="text"], input[type="number"], textarea').forEach(input => {
        if (input.id !== 'api_key') { // API Key input box is excluded
            input.disabled = false;
        }
    });

    // Reset progress bar
    updateProgress(0);
}

function validateInputs() {
    const selectedModel = modelChoice.value;
    const apiKey = document.getElementById('api_key').value.trim();
    const iteration = document.getElementById('iteration').value.trim();
    const experimentDesign = document.getElementById('experiment_design').value.trim();

    // Check if a model is selected
    if (!selectedModel) {
        alert('Please choose a model!');
        return false;
    }

    // If GPT-4o is selected, check API Key
    if (selectedModel === 'GPT-4o' && !apiKey) {
        alert('OpenAI API Key cannot be empty when using GPT-4o!');
        return false;
    }

    // If custom model is selected, check API Key and URL
    if (selectedModel === 'custom') {
        const apiUrl = document.getElementById('custom_api_url').value.trim();  // Fixed field ID
        const modelName = document.getElementById('custom_model_name').value.trim();  // Add model name validation
        if (!apiKey) {
            alert('API Key cannot be empty when using custom model!');
            return false;
        }
        if (!modelName) {  // Add model name validation
            alert('Model Name cannot be empty when using custom model!');
            return false;
        }
        if (!apiUrl) {
            alert('API URL cannot be empty when using custom model!');
            return false;
        }

        // Validate custom parameters if provided
        const customParams = document.getElementById('custom_params').value.trim();
        if (customParams) {
            try {
                JSON.parse(customParams);
            } catch (e) {
                alert('Invalid JSON in custom parameters!');
                return false;
            }
        }
    }

    // Check inputs in Item tables
    const itemContainers = document.querySelectorAll('.item-container');
    for (let i = 0; i < itemContainers.length; i++) {
        const tbody = itemContainers[i].querySelector('.stimuli-table tbody');
        const rows = tbody.getElementsByTagName('tr');

        for (let j = 0; j < rows.length; j++) {
            const typeCell = rows[j].querySelector('.type-column input');
            const contentCell = rows[j].querySelector('.content-column input');

            if (typeCell && contentCell) {
                const typeValue = typeCell.value.trim();
                const contentValue = contentCell.value.trim();

                if (!typeValue || !contentValue) {
                    alert(`All Components and Content fields in the "Item ${i + 1}" table must be filled!`);
                    return false;
                }
            }
        }
    }

    // Check Experiment Design
    if (!experimentDesign) {
        alert('Stimulus design cannot be empty!');
        return false;
    }

    const agent2Rows = document.getElementById('agent2PropertiesTable').getElementsByTagName('tr');
    for (let i = 1; i < agent2Rows.length; i++) { // Skip header
        const cells = agent2Rows[i].getElementsByTagName('input');
        if (cells.length === 2) {
            const propertyValue = cells[0].value.trim();
            const descriptionValue = cells[1].value.trim();
            if (!propertyValue || !descriptionValue) {
                alert('All fields in the "Validator" table must be filled!');
                return false;
            }
        }
    }

    // Check agent3PropertiesTable
    const agent3Rows = document.getElementById('agent3PropertiesTable').getElementsByTagName('tr');
    for (let i = 1; i < agent3Rows.length; i++) { // Skip header
        const cells = agent3Rows[i].getElementsByTagName('input');
        if (cells.length === 4) {
            const propertyValue = cells[0].value.trim();
            const descriptionValue = cells[1].value.trim();
            const minValue = cells[2].value.trim();
            const maxValue = cells[3].value.trim();

            if (!propertyValue || !descriptionValue || !minValue || !maxValue) {
                alert('All fields in the "Scorer" table must be filled!');
                return false;
            }

            // Ensure Minimum and Maximum are integers
            if (!/^\d+$/.test(minValue) || !/^\d+$/.test(maxValue)) {
                alert('Min and Max scores must be non-negative integers (e.g., 0, 1, 2, 3...)');
                return false;
            }

            const minInt = parseInt(minValue, 10);
            const maxInt = parseInt(maxValue, 10);
            if (maxInt <= minInt) {
                alert('Max score must be greater than Min score!');
                return false;
            }
        }
    }

    // Check if Iteration is a positive integer
    if (!/^\d+$/.test(iteration) || parseInt(iteration, 10) <= 0) {
        alert("'The number of items' must be a positive integer!");
        return false;
    }

    return true; // If all checks pass, return true
}

// Modify generateButton click handler
generateButton.addEventListener('click', () => {
    if (!validateInputs()) {
        return; // If frontend input checks fail, terminate "Generate Stimulus" related operations
    }

    // Ensure WebSocket connection
    ensureSocketConnection(startGeneration);
});

// Extract generation process as a standalone function
function startGeneration() {
    updateProgress(0);

    // Show "Generating..." status text
    showGeneratingStatus();

    // Clear log display area
    clearLogs();

    // Ensure WebSocket connection status is normal before generation starts
    checkSocketConnection();

    // Disable all buttons, except Stop button
    generateButton.disabled = true;
    clearButton.disabled = true;
    stopButton.disabled = false;

    // Disable all table-related buttons
    addAgent2Button.disabled = true;
    addAgent3Button.disabled = true;

    // Disable Add/Delete buttons in all tables
    document.querySelectorAll('.add-component-btn, .delete-component-btn, .add-item-btn, .delete-item-btn').forEach(btn => {
        btn.disabled = true;
    });

    // Disable model selection dropdown
    document.getElementById('model_choice').disabled = true;

    // Disable all input boxes and text areas
    document.getElementById('api_key').disabled = true;
    document.getElementById('iteration').disabled = true;
    document.getElementById('experiment_design').disabled = true;

    // Disable all input boxes in all tables
    document.querySelectorAll('input[type="text"], input[type="number"], textarea').forEach(input => {
        input.disabled = true;
    });

    // Collect table data
    const stimuli = collectItemsData();
    const previousStimuli = JSON.stringify(stimuli); // Convert to JSON string

    // Modify the logic to get agent1Properties
    // Get data from Components column of the first Item table
    const agent1Properties = {};
    // Find the first Item table
    const firstItemTable = document.querySelector('#item-1 .stimuli-table');
    if (firstItemTable) {
        // Get all rows (skip header)
        const componentRows = Array.from(firstItemTable.querySelectorAll('tbody tr'));
        componentRows.forEach(row => {
            // Get input value from Components column
            const componentInput = row.querySelector('td.type-column input');
            if (componentInput && componentInput.value.trim()) {
                agent1Properties[componentInput.value.trim()] = { type: 'string' };
            }
        });
    }

    // Get agent2_properties
    const agent2Rows = Array.from(agent2Table.rows).slice(1);
    let agent2Properties = {};
    agent2Rows.forEach(row => {
        const propertyName = row.cells[0].querySelector("input").value.trim();
        const propertyDesc = row.cells[1].querySelector("input").value.trim();
        if (propertyName && propertyDesc) {
            agent2Properties[propertyName] = {
                "type": "boolean",
                "description": propertyDesc
            };
        }
    });



    // Get agent3_properties
    const agent3PropertiesTable = document.getElementById('agent3PropertiesTable');
    const agent3Rows = Array.from(agent3PropertiesTable.rows).slice(1); // Skip header
    let agent3Properties = {};

    agent3Rows.forEach(row => {
        let property = row.cells[0].querySelector('input').value.trim();
        let description = row.cells[1].querySelector('input').value.trim();
        let min = row.cells[2].querySelector('input').value.trim();
        let max = row.cells[3].querySelector('input').value.trim();

        if (property && description && min && max) {
            agent3Properties[property] = {
                "type": "integer",
                "description": description,
                "minimum": parseInt(min, 10),
                "maximum": parseInt(max, 10)
            };
        }
    });

    const settings = {
        agent1Properties: JSON.stringify(agent1Properties),
        agent2Properties: JSON.stringify(agent2Properties),
        agent3Properties: JSON.stringify(agent3Properties),
        apiKey: document.getElementById('api_key').value,
        modelChoice: document.getElementById('model_choice').value,
        experimentDesign: document.getElementById('experiment_design').value,
        previousStimuli: previousStimuli,
        iteration: parseInt(document.getElementById('iteration').value),
        agent2IndividualValidation: document.getElementById('agent2_individual_validation').checked,
        agent3IndividualScoring: document.getElementById('agent3_individual_scoring').checked
    };

    // Add custom model parameters if custom model is selected
    if (settings.modelChoice === 'custom') {
        settings.apiUrl = document.getElementById('custom_api_url').value.trim();
        settings.modelName = document.getElementById('custom_model_name').value.trim();  // Fixed field ID
        const customParams = document.getElementById('custom_params').value.trim();
        if (customParams) {
            try {
                settings.params = JSON.parse(customParams);
            } catch (e) {
                alert('Invalid JSON in custom parameters!');
                resetUI();
                return;
            }
        }
    }

    // Add request timeout control
    const fetchWithTimeout = (url, options, timeout = 10000) => {
        return Promise.race([
            fetch(url, options),
            new Promise((_, reject) =>
                setTimeout(() => reject(new Error('Request timed out')), timeout)
            )
        ]);
    };

    // Add retry counter
    let fetchRetryCount = 0;
    const maxFetchRetries = 2;

    // Function to handle fetch requests
    function attemptFetch() {
        fetchRetryCount++;
        console.log(`Fetch attempt ${fetchRetryCount}/${maxFetchRetries + 1}...`);

        fetchWithTimeout(getApiUrl('generate_stimulus'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        }, 15000)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Failed to start stimulus generation: ${response.status} ${response.statusText.trim()}.`);
                }
                return response.json();
            })
            .then(data => {
                console.log('Stimulus generation started, server response:', data);
                alert('Stimulus generation started!');

                // Start checking generation status
                checkGenerationStatus();
            })
            .catch(error => {
                console.error('Error starting stimulus generation:', error);

                // If there are retries left, continue trying
                if (fetchRetryCount <= maxFetchRetries) {
                    console.log(`Request failed, trying again...`);
                    setTimeout(attemptFetch, 2000);  // Wait 2 seconds before retrying
                } else {
                    resetUI();
                    alert(`Failed to start stimulus generation: ${error.message}. Please try again later.`);
                }
            });
    }

    // Start first request attempt
    attemptFetch();
}

function checkGenerationStatus() {
    // Ensure WebSocket connection is active, if not, try to reconnect
    if (!socket || !socket.connected) {
        console.log("Detected WebSocket connection disconnected, trying to reconnect");
        initializeSocket();
    }

    fetch(getApiUrl('generation_status'))
        .then(response => {
            if (!response.ok) {
                if (response.status === 400) {
                    // Maybe session expired, wait 2 seconds before retrying
                    console.log("Session may be temporarily unavailable, retrying...");
                    window.statusCheckTimer = setTimeout(function () {
                        checkGenerationStatus();
                    }, 2000);
                    return null; // Don't continue processing current response
                }
                throw new Error(`Status error: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (!data) return; // If null (due to session issue), return immediately

            console.log("Generation status:", data);

            if (data.status === 'error') {
                // If session invalid error, try to restart generation process
                if (data.error_message === 'Invalid session') {
                    console.log("Session expired, refreshing page...");
                    alert("Your session has expired. The page will refresh.");
                    window.location.reload();
                    return;
                }

                alert('Error: ' + data.error_message);
                resetUI();
                return; // Immediately stop polling
            }

            if (data.status === 'completed') {
                // Confirm again that there is a file before displaying completion message
                if (data.file) {
                    // Save current file name for future check to avoid duplicates
                    const currentFile = data.file;

                    // Ensure file contains current session ID to prevent downloading incorrect file
                    if (!currentFile.includes(sessionId)) {
                        console.error("File does not match current session:", currentFile, sessionId);
                        alert('Error: Generated file does not match current session. Please try again.');
                        resetUI();
                        return;
                    }

                    // Use timestamp to ensure file name is unique, avoid browser cache
                    const timestamp = Date.now();
                    const downloadUrl = `${getApiUrl(`download/${currentFile}`)}?t=${timestamp}`;
                    console.log(`Preparing to download from: ${downloadUrl}`);

                    // Clear previous polling timer
                    if (window.statusCheckTimer) {
                        clearTimeout(window.statusCheckTimer);
                        window.statusCheckTimer = null;
                    }

                    // Create download link element
                    const link = document.createElement('a');
                    hideGenerationStatus(); // Hide status text

                    // Use timestamp URL to avoid browser cache
                    link.href = downloadUrl;
                    link.download = currentFile;
                    document.body.appendChild(link); // Add to DOM

                    // Show success message
                    alert('Stimulus generation complete!');

                    // Download file
                    setTimeout(() => {
                        link.click();
                        // Remove link from DOM after completion
                        setTimeout(() => {
                            document.body.removeChild(link);
                        }, 100);
                    }, 500);

                    // Reset UI state
                    resetUI();

                    // Reset polling counter
                    window.retryCount = 0;
                } else {
                    // If there is no file but status is completed, this is an error
                    console.error("Status reported as completed but no file was returned");
                    alert('Generation completed but no file was produced. Please try again.');
                    resetUI();
                }
            } else if (data.status === 'stopped') {
                // Clear stop status and reset UI
                console.log("Generation has been stopped by user");
                resetUI();
            } else if (data.status === 'running') {
                updateProgress(data.progress);

                // Add extra check - if progress is 100 but status is still running
                if (data.progress >= 100) {
                    console.log("Progress is 100% but status is still running, waiting for file...");
                    // Set to "Checking status & Creating file..."
                    showCheckingStatus();
                    // Give server more time to complete file generation
                    window.statusCheckTimer = setTimeout(function () {
                        checkGenerationStatus();
                    }, 2000); // Extend to 2 seconds to wait for file generation
                } else {
                    // Ensure "Generating..." text is displayed
                    if (data.progress > 0 && data.progress < 100) {
                        showGeneratingStatus();
                    }

                    // Adjust polling frequency based on progress, the higher the progress, the more frequent the check
                    let pollInterval = 1000; // Default 1 second
                    if (data.progress > 0) {
                        // When progress is greater than 0, check more frequently
                        pollInterval = 500; // Change to 0.5 seconds
                    }
                    window.statusCheckTimer = setTimeout(function () {
                        checkGenerationStatus();
                    }, pollInterval);
                }
            } else {
                // Handle unknown status
                console.error("Unknown status received:", data.status);
                alert("Received unexpected status from server. Generation may have failed. Please try again later.");
                resetUI();
            }
        })
        .catch(error => {
            console.error('Error checking generation status:', error);
            // If there is an error, wait 3 seconds before retrying, but only up to 3 times
            if (!window.retryCount) window.retryCount = 0;
            window.retryCount++;

            if (window.retryCount <= 3) {
                console.log(`Retrying status check (${window.retryCount}/3)...`);
                window.statusCheckTimer = setTimeout(function () {
                    checkGenerationStatus();
                }, 3000);
            } else {
                window.retryCount = 0; // Reset counter
                alert('Error checking generation status. Please try again.');
                resetUI();
            }
        });
}

stopButton.addEventListener('click', () => {
    // Add confirmation dialogue box
    const confirmStop = confirm('Are you sure you want to stop?');

    // Only execute stop operation when user clicks "Yes"
    if (confirmStop) {
        fetch(getApiUrl('stop_generation'), { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                alert(data.message);
                // Immediately stop progress polling to prevent unexpected status check
                if (window.statusCheckTimer) {
                    clearTimeout(window.statusCheckTimer);
                }
                resetUI();
                // Ensure stop status is displayed
                updateProgress(0);
            })
            .catch(error => {
                console.error('Error stopping generation:', error);
                alert('Failed to stop generation. Please try again in a few seconds.');
            });
    }
    // If user clicks "No", do nothing
});

clearButton.addEventListener('click', () => {
    // Reset model selection
    document.getElementById('model_choice').value = '';
    // Disable API key input box
    document.getElementById('api_key').disabled = true;

    const textAreas = [
        'agent1_properties',
        'agent2_properties',
        'agent3_properties',
        'api_key',
        'iteration',
        'experiment_design'
    ];
    textAreas.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.value = ''; // Clear text box and text area values
        }
    });

    // Clear all Items, only keep one initial Item
    while (itemsContainer.firstChild) {
        itemsContainer.removeChild(itemsContainer.firstChild);
    }

    // Create new Item 1
    const newItem = document.createElement('div');
    newItem.className = 'item-container';
    newItem.id = 'item-1';
    newItem.innerHTML = `
        <div class="item-title">Item 1</div>
        <table class="stimuli-table">
            <thead>
                <tr>
                    <th class="type-column">Components</th>
                    <th class="content-column">Content</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td class="type-column"><input type="text" placeholder="e.g., word pair"></td>
                    <td class="content-column"><input type="text" placeholder="e.g., math/mathematics"></td>
                </tr>
            </tbody>
        </table>
        <div class="item-buttons-row">
            <div class="left-buttons">
                <button class="add-component-btn">Add component</button>
                <button class="delete-component-btn">Delete component</button>
            </div>
            <div class="right-buttons">
                <button class="add-item-btn">Add item</button>
            </div>
        </div>
    `;
    itemsContainer.appendChild(newItem);

    // Add event listener to new buttons
    newItem.querySelector('.add-component-btn').addEventListener('click', addComponentToAllItems);
    newItem.querySelector('.delete-component-btn').addEventListener('click', deleteComponentFromAllItems);
    newItem.querySelector('.add-item-btn').addEventListener('click', addNewItem);

    // Add Agent 2 table clear functionality
    const agent2Rows = Array.from(agent2Table.rows).slice(1); // Skip header
    // First delete extra rows
    while (agent2Table.rows.length > 2) {
        agent2Table.deleteRow(2); // Always delete second row and all following rows
    }
    // Clear input in first row of two columns
    agent2Table.rows[1].cells[0].querySelector('input').value = '';
    agent2Table.rows[1].cells[1].querySelector('input').value = '';

    // Add Agent 3 table clear functionality
    const agent3Rows = Array.from(agent3PropertiesTable.rows).slice(1); // Skip header
    // First delete extra rows
    while (agent3PropertiesTable.rows.length > 2) {
        agent3PropertiesTable.deleteRow(2); // Always delete second row and all following rows
    }
    // Clear input in first row of four columns
    agent3PropertiesTable.rows[1].cells[0].querySelector('input').value = '';
    agent3PropertiesTable.rows[1].cells[1].querySelector('input').value = '';
    agent3PropertiesTable.rows[1].cells[2].querySelector('input').value = '';
    agent3PropertiesTable.rows[1].cells[3].querySelector('input').value = '';

    // Reset progress bar
    updateProgress(0);

    // Clear log area
    clearLogs();
});

// Function to periodically check WebSocket status
function periodicSocketCheck() {
    if (!socket || !socket.connected) {
        if (socketInitialized) {
            console.log("Detected WebSocket connection disconnected, resetting connection flag");
            socketInitialized = false;
        }

        // Only try to reconnect if there is no connection attempt in progress, and the time since last attempt is reasonable
        if (!socketConnectionInProgress && (!socketReconnectTimer || socketReconnectAttempts > 10)) {
            console.log("Trying to reconnect WebSocket");
            socketReconnectAttempts = 0; // Reset attempt counter
            socketBackoffDelay = 1000; // Reset backoff delay
            initializeSocket();
        }
    }

    // Check connection status every 30 seconds
    setTimeout(periodicSocketCheck, 30000);
}

// Disable all interactive elements on the page
function disableAllElements() {
    // Start safety timeout
    startSafetyTimeout();

    // Disable all dropdowns, text boxes, and text areas
    document.querySelectorAll('input, textarea, select').forEach(element => {
        element.disabled = true;
    });

    // Disable all buttons (except the AutoGenerate button)
    document.querySelectorAll('button').forEach(button => {
        if (button.id !== 'auto_generate_button') {
            button.disabled = true;
        }
    });

    // Add disabled style to tables
    document.querySelectorAll('table').forEach(table => {
        table.classList.add('disabled-table');
    });

    // Add semi-transparent overlay to prevent user interaction
    const overlay = document.createElement('div');
    overlay.id = 'page-overlay';
    overlay.className = 'page-overlay';

    // Add loading animation
    const spinner = document.createElement('div');
    spinner.className = 'loading-spinner';

    // Add processing text
    const loadingText = document.createElement('div');
    loadingText.className = 'loading-text';
    loadingText.textContent = 'Generating properties...';

    // Add animation and text to overlay
    overlay.appendChild(spinner);
    overlay.appendChild(loadingText);

    document.body.appendChild(overlay);
}

// Enable all interactive elements on the page
function enableAllElements() {
    // Clear safety timeout
    clearSafetyTimeout();

    // Enable all dropdowns, text boxes, and text areas
    document.querySelectorAll('input, textarea, select').forEach(element => {
        // Check if element is API key input box, and model selection requires API key
        if (element.id === 'api_key' && modelChoice.value !== 'GPT-4o' && modelChoice.value !== 'custom') {
            element.disabled = true; // Keep API key input box disabled
        } else {
            element.disabled = false;
        }
    });

    // Enable all buttons
    document.querySelectorAll('button').forEach(button => {
        button.disabled = false;
    });

    // Restore Stop button state (should be disabled by default)
    if (stopButton) {
        stopButton.disabled = true;
    }

    // Remove table disabled style
    document.querySelectorAll('table').forEach(table => {
        table.classList.remove('disabled-table');
    });

    // Remove page overlay
    const overlay = document.getElementById('page-overlay');
    if (overlay) {
        document.body.removeChild(overlay);
    }
}

// Modify AutoGenerate button click event
autoGenerateButton.addEventListener('click', function () {
    // First validate inputs
    if (!validateAutoGenerateInputs()) {
        return;
    }

    // Show loading status
    autoGenerateButton.disabled = true;
    autoGenerateButton.innerText = "Generating...";

    // Disable all other elements on the page
    disableAllElements();

    // Collect example stimuli from tables
    const exampleStimuli = collectExampleStimuli();
    // Get experimental design
    const experimentDesign = document.getElementById('experiment_design').value.trim();

    // Build prompt, replace placeholders
    let prompt = autoGeneratePromptTemplate
        .replace('{Experimental design}', experimentDesign)
        .replace('{Example stimuli}', JSON.stringify(exampleStimuli, null, 2));

    // Record used model and built prompt
    const selectedModel = modelChoice.value;
    console.log("Model used:", selectedModel);
    console.log("Experimental Design:", experimentDesign);
    console.log("Example Stimuli:", exampleStimuli);
    console.log("Complete Prompt:", prompt);

    if (selectedModel === 'GPT-4o') {
        // Use OpenAI API
        callOpenAIAPI(prompt);
    } else if (selectedModel === 'custom') {
        // Use custom model API
        callcustomAPI(prompt);
    }
});

// Modify OpenAI API call function, enable page elements when successful or failed
function callOpenAIAPI(prompt) {
    try {
        const apiKey = document.getElementById('api_key').value.trim();


        // Prepare request body
        const requestBody = {
            model: "gpt-4o",
            messages: [
                {
                    role: "user",
                    content: prompt
                }
            ],

            max_tokens: 2000
        };

        // Send API request
        fetch('https://api.openai.com/v1/chat/completions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${apiKey}`
            },
            body: JSON.stringify(requestBody)
        })
            .then(response => {
                // Check response status
                if (!response.ok) {
                    throw new Error(`API request failed: ${response.status} ${response.statusText.trim()}`);
                }
                return response.json();
            })
            .then(data => {
                // Clear safety timeout when API call succeeds
                clearSafetyTimeout();

                // Process API response
                const content = data.choices[0].message.content;
                // Wrap processing in try-catch
                try {
                    processAPIResponse(content);
                } catch (processingError) {
                    console.error('Error processing response:', processingError);
                    // Ensure page is not locked
                    enableAllElements();
                    alert(`Error processing response: ${processingError.message}`);
                }
            })
            .catch(error => {
                console.error('OpenAI API call error:', error);
                // Clear safety timeout when API call fails
                clearSafetyTimeout();
                // Ensure page is not locked
                enableAllElements();
                alert(`OpenAI API call failed: ${error.message}. Please check your input is correct and try again later.`);
            })
            .finally(() => {
                // Restore button state
                autoGenerateButton.disabled = false;
                autoGenerateButton.innerText = "AutoGenerate properties";
            });
    } catch (error) {
        // Catch any errors that occur before setting up or executing API call
        console.error('Error setting up API call:', error);
        clearSafetyTimeout();
        enableAllElements();
        autoGenerateButton.disabled = false;
        autoGenerateButton.innerText = "AutoGenerate properties";
        alert(`Error setting up API call: ${error.message}`);
    }
}




// Add custom model API call function
function callcustomAPI(prompt) {
    const apiUrl = document.getElementById('custom_api_url').value.trim();
    const apiKey = document.getElementById('api_key').value.trim();
    const modelName = document.getElementById('custom_model_name').value.trim();

    const requestBody = {
        model: modelName,
        messages: [
            { role: "user", content: prompt }
        ]
    };

    fetch(apiUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${apiKey}`
        },
        body: JSON.stringify(requestBody)
    })
        .then(response => {
            if (!response.ok) {
                throw new Error(`API request failed: ${response.status} ${response.statusText.trim()}`);
            }
            return response.json();
        })
        .then(data => {
            // Clear safety timeout when API call succeeds
            clearSafetyTimeout();

            const content = data.choices[0].message.content;
            processAPIResponse(content);
        })
        .catch(error => {
            console.error('Custom model API call error:', error);
            clearSafetyTimeout();
            enableAllElements();
            alert(`Custom model API call failed: ${error.message}. Please check your input is correct and try again later.`);
        })
        .finally(() => {
            autoGenerateButton.disabled = false;
            autoGenerateButton.innerText = "AutoGenerate properties";
        });
}



// Process API response
function processAPIResponse(response) {
    try {
        console.log("API response:", response);

        // Clear safety timeout when starting to process response
        clearSafetyTimeout();

        // Extract Requirements dictionary
        const requirementsMatch = response.match(/Requirements:\s*\{([^}]+)\}/s);
        let requirements = {};

        if (requirementsMatch && requirementsMatch[1]) {
            try {
                // Try to parse complete JSON
                requirements = JSON.parse(`{${requirementsMatch[1]}}`);
            } catch (e) {
                console.error("Failed to parse Requirements JSON:", e);

                // Use regular expression to parse key-value pairs
                const keyValuePairs = requirementsMatch[1].match(/"([^"]+)":\s*"([^"]+)"/g);
                if (keyValuePairs) {
                    keyValuePairs.forEach(pair => {
                        const matches = pair.match(/"([^"]+)":\s*"([^"]+)"/);
                        if (matches && matches.length === 3) {
                            requirements[matches[1]] = matches[2];
                        }
                    });
                }
            }
        }

        // Extract Scoring Dimensions dictionary
        const scoringMatch = response.match(/Scoring Dimensions:\s*\{([^}]+)\}/s);
        let scoringDimensions = {};

        if (scoringMatch && scoringMatch[1]) {
            try {
                // Try to parse complete JSON
                scoringDimensions = JSON.parse(`{${scoringMatch[1]}}`);
            } catch (e) {
                console.error("Failed to parse Scoring Dimensions JSON:", e);

                // Use regular expression to parse key-value pairs
                const keyValuePairs = scoringMatch[1].match(/"([^"]+)":\s*"([^"]+)"/g);
                if (keyValuePairs) {
                    keyValuePairs.forEach(pair => {
                        const matches = pair.match(/"([^"]+)":\s*"([^"]+)"/);
                        if (matches && matches.length === 3) {
                            scoringDimensions[matches[1]] = matches[2];
                        }
                    });
                }
            }
        }

        // If no content is found above, try to find curly braces
        if (Object.keys(requirements).length === 0 && Object.keys(scoringDimensions).length === 0) {
            const jsonMatches = response.match(/\{([^{}]*)\}/g);
            if (jsonMatches && jsonMatches.length >= 2) {
                try {
                    requirements = JSON.parse(jsonMatches[0]);
                    scoringDimensions = JSON.parse(jsonMatches[1]);
                } catch (e) {
                    console.error("Failed to parse JSON objects:", e);
                }
            }
        }

        // Confirm content has been extracted
        if (Object.keys(requirements).length === 0 || Object.keys(scoringDimensions).length === 0) {
            // First enable all elements, then display error message
            enableAllElements();
            throw new Error("Could not extract valid Requirements or Scoring Dimensions from API response.");
        }

        // Fill validator table
        fillValidatorTable(requirements);

        // Fill scorer table
        fillScorerTable(scoringDimensions);

        // Ensure all elements are enabled before displaying completion message
        enableAllElements();

        alert("Auto-generation complete! Please carefully review the content in the Validator and Scorer tables to ensure they meet your experimental design requirements.");
    } catch (error) {
        console.error("Error processing API response:", error);
        // Clear safety timeout even on error
        clearSafetyTimeout();
        // Ensure all elements are enabled regardless
        enableAllElements();
        alert(`Failed to process API response: ${error.message}. Please try again later.`);
    }
}

// Fill validator table
function fillValidatorTable(requirements) {
    // Clear current table content
    const tbody = agent2Table.querySelector('tbody');
    const currentRowCount = tbody.querySelectorAll('tr').length;
    const requirementsCount = Object.keys(requirements).length;

    console.log(`Validator table: current rows = ${currentRowCount}, required rows = ${requirementsCount}`);

    // Calculate how many rows need to be added or deleted
    if (requirementsCount > currentRowCount) {
        // Need to add rows
        const rowsToAdd = requirementsCount - currentRowCount;
        console.log(`Adding ${rowsToAdd} rows to Validator table`);

        // Add rows directly using DOM operations, not through clicking buttons
        for (let i = 0; i < rowsToAdd; i++) {
            // Create new row
            const newRow = document.createElement('tr');

            // Create and add first cell (property name)
            const propertyCell = document.createElement('td');
            propertyCell.className = "agent_2_properties-column";
            const propertyInput = document.createElement('input');
            propertyInput.type = "text";
            propertyInput.placeholder = "Enter new property";
            propertyCell.appendChild(propertyInput);

            // Create and add second cell (description)
            const descriptionCell = document.createElement('td');
            descriptionCell.className = "agent_2_description-column";
            const descriptionInput = document.createElement('input');
            descriptionInput.type = "text";
            descriptionInput.placeholder = "Enter property's description";
            descriptionCell.appendChild(descriptionInput);

            // New: Add Delete button
            const actionCell = document.createElement('td');
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'delete-row-btn delete-btn';
            deleteBtn.textContent = 'Delete';
            actionCell.appendChild(deleteBtn);
            newRow.appendChild(propertyCell);
            newRow.appendChild(descriptionCell);
            newRow.appendChild(actionCell);

            // Add row to table
            tbody.appendChild(newRow);
        }
    } else if (requirementsCount < currentRowCount) {
        // Need to delete rows
        const rowsToDelete = currentRowCount - requirementsCount;
        console.log(`Deleting ${rowsToDelete} rows from Validator table`);

        // Delete extra rows, starting from the last row
        for (let i = 0; i < rowsToDelete; i++) {
            tbody.removeChild(tbody.lastElementChild);
        }
    }

    // Get updated rows and fill in content
    const updatedRows = agent2Table.querySelectorAll('tbody tr');
    let index = 0;

    for (const [key, value] of Object.entries(requirements)) {
        if (index < updatedRows.length) {
            const cells = updatedRows[index].querySelectorAll('input');
            if (cells.length >= 2) {
                cells[0].value = key;
                cells[1].value = value;
            }
            index++;
        }
    }
}

// Fill scorer table
function fillScorerTable(scoringDimensions) {
    // Clear current table content
    const tbody = agent3PropertiesTable.querySelector('tbody');
    const currentRowCount = tbody.querySelectorAll('tr').length;
    const dimensionsCount = Object.keys(scoringDimensions).length;

    console.log(`Scorer table: current rows = ${currentRowCount}, required rows = ${dimensionsCount}`);

    // Calculate how many rows need to be added or deleted
    if (dimensionsCount > currentRowCount) {
        // Need to add rows
        const rowsToAdd = dimensionsCount - currentRowCount;
        console.log(`Adding ${rowsToAdd} rows to Scorer table`);

        // Add rows directly using DOM operations, not through clicking buttons
        for (let i = 0; i < rowsToAdd; i++) {
            // Create new row
            const newRow = document.createElement('tr');

            // Create and add first cell (aspect name)
            const aspectCell = document.createElement('td');
            aspectCell.className = "agent_3_properties-column";
            const aspectInput = document.createElement('input');
            aspectInput.type = "text";
            aspectInput.placeholder = "Enter new aspect";
            aspectCell.appendChild(aspectInput);

            // Create and add second cell (description)
            const descriptionCell = document.createElement('td');
            descriptionCell.className = "agent_3_description-column";
            const descriptionInput = document.createElement('input');
            descriptionInput.type = "text";
            descriptionInput.placeholder = "Enter aspect's description";
            descriptionCell.appendChild(descriptionInput);

            // Create and add third cell (minimum value)
            const minCell = document.createElement('td');
            minCell.className = "agent_3_minimum-column";
            const minInput = document.createElement('input');
            minInput.type = "number";
            minInput.min = "0";
            minInput.placeholder = "e.g. 0";
            minCell.appendChild(minInput);

            // Create and add fourth cell (maximum value)
            const maxCell = document.createElement('td');
            maxCell.className = "agent_3_maximum-column";
            const maxInput = document.createElement('input');
            maxInput.type = "number";
            maxInput.min = "0";
            maxInput.placeholder = "e.g. 10";
            maxCell.appendChild(maxInput);

            // New: Add Delete button
            const actionCell = document.createElement('td');
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'delete-row-btn delete-btn';
            deleteBtn.textContent = 'Delete';
            actionCell.appendChild(deleteBtn);
            newRow.appendChild(aspectCell);
            newRow.appendChild(descriptionCell);
            newRow.appendChild(minCell);
            newRow.appendChild(maxCell);
            newRow.appendChild(actionCell);

            // Add row to table
            tbody.appendChild(newRow);
        }
    } else if (dimensionsCount < currentRowCount) {
        // Need to delete rows
        const rowsToDelete = currentRowCount - dimensionsCount;
        console.log(`Deleting ${rowsToDelete} rows from Scorer table`);

        // Delete extra rows, starting from the last row
        for (let i = 0; i < rowsToDelete; i++) {
            tbody.removeChild(tbody.lastElementChild);
        }
    }

    // Get updated rows and fill in content
    const updatedRows = agent3PropertiesTable.querySelectorAll('tbody tr');
    let index = 0;

    for (const [key, value] of Object.entries(scoringDimensions)) {
        if (index < updatedRows.length) {
            const cells = updatedRows[index].querySelectorAll('input');
            if (cells.length >= 4) {
                cells[0].value = key;
                cells[1].value = value;
                cells[2].value = '0';  // Default minimum value
                cells[3].value = '10'; // Default maximum value
            }
            index++;
        }
    }
}

// Add global error handler, ensure page is not locked
window.addEventListener('error', function (event) {
    console.error('Global error:', event.error || event.message);

    // If page overlay exists and has been active for more than 30 seconds, remove it automatically
    const overlay = document.getElementById('page-overlay');
    if (overlay && document.body.contains(overlay)) {
        console.warn('Detected global error, removing possibly frozen page overlay');
        clearSafetyTimeout();
        document.body.removeChild(overlay);

        // Restore normal page interaction
        enableUI();
    }
});

// Add safety timeout, ensure page is unlocked after 90 seconds
function startSafetyTimeout() {
    console.log('Starting safety timeout');
    window.safetyTimeoutId = setTimeout(function () {
        console.log('Safety timeout triggered');
        if (document.getElementById('page-overlay')) {
            console.log('Removing overlay due to safety timeout');
            enableAllElements();
            alert("Operation timed out. The page has been unlocked. Please try again.");
            autoGenerateButton.disabled = false;
            autoGenerateButton.innerText = "AutoGenerate properties";
        }
    }, 90000); // 90 second timeout
}

function clearSafetyTimeout() {
    if (window.safetyTimeoutId) {
        console.log('Clearing safety timeout');
        clearTimeout(window.safetyTimeoutId);
        window.safetyTimeoutId = null;
    }
}

// Add UI safety timeout protection, ensure interface is not locked for more than 30 seconds
function setupUIProtection() {
    // Global timeout protection: ensure page is not locked for more than 30 seconds
    window.uiProtectionTimeout = null;
}

// Modify disableUI function to add timeout protection
function disableUI() {
    // Disable main buttons and input elements
    generateButton.disabled = true;
    clearButton.disabled = true;
    addAgent2Button.disabled = true;
    addAgent3Button.disabled = true;
    modelSelect.disabled = true;
    apiKeyInput.disabled = true;

    // Enable Stop button
    stopButton.disabled = false;

    // Add element to display "Generating..." status
    updateGenerationStatus('generating');

    // Create and display page overlay
    createPageOverlay("Generating stimuli, please wait...");

    // Set UI protection timeout, ensure interface is not locked indefinitely
    if (window.uiProtectionTimeout) {
        clearTimeout(window.uiProtectionTimeout);
    }

    window.uiProtectionTimeout = setTimeout(() => {
        console.warn("UI protection timeout triggered - interface will automatically restore after 90 seconds");
        enableUI();

        // Remove overlay (if it exists)
        const overlay = document.getElementById('page-overlay');
        if (overlay && document.body.contains(overlay)) {
            document.body.removeChild(overlay);
        }

        // Display warning message
        alert("Operation timed out. If you are waiting for the generation result, please try again later.");
    }, 90000); // 90 second timeout
}

// Modify enableUI function to clear timeout protection
function enableUI() {
    // Enable main buttons and input elements
    generateButton.disabled = false;
    clearButton.disabled = false;
    addAgent2Button.disabled = false;
    addAgent3Button.disabled = false;
    modelSelect.disabled = false;

    // Determine if API key input box is available based on current model selection
    handleModelChange();

    // Disable Stop button
    stopButton.disabled = true;

    // Clear "Generating..." status display
    updateGenerationStatus('idle');

    // Remove overlay (if it exists)
    const overlay = document.getElementById('page-overlay');
    if (overlay && document.body.contains(overlay)) {
        document.body.removeChild(overlay);
    }

    // Clear UI protection timeout
    if (window.uiProtectionTimeout) {
        clearTimeout(window.uiProtectionTimeout);
        window.uiProtectionTimeout = null;
    }
}

// Modify createPageOverlay function to add click event handling
function createPageOverlay(message) {
    // If overlay already exists, remove it first
    const existingOverlay = document.getElementById('page-overlay');
    if (existingOverlay) {
        document.body.removeChild(existingOverlay);
    }

    // Create overlay element
    const overlay = document.createElement('div');
    overlay.id = 'page-overlay';
    overlay.className = 'page-overlay';

    // Create loading animation
    const spinner = document.createElement('div');
    spinner.className = 'loading-spinner';
    overlay.appendChild(spinner);

    // Create loading text
    const loadingText = document.createElement('div');
    loadingText.className = 'loading-text';
    loadingText.textContent = message || 'Loading...';
    overlay.appendChild(loadingText);

    // Add to page
    document.body.appendChild(overlay);
    return overlay;
}

// Add event delegation for row deletion in Validator table
agent2Table.addEventListener('click', function (e) {
    if (e.target && e.target.classList.contains('delete-row-btn')) {
        const row = e.target.closest('tr');
        if (row.parentNode.rows.length > 1) {
            row.remove();
        }
    }
});

// Add event delegation for row deletion in Scorer table
agent3PropertiesTable.addEventListener('click', function (e) {
    if (e.target && e.target.classList.contains('delete-row-btn')) {
        const row = e.target.closest('tr');
        if (row.parentNode.rows.length > 1) {
            row.remove();
        }
    }
});

// Modify addAgent2Button click handler to add Delete button in new row
addAgent2Button.addEventListener('click', function () {
    const tbody = agent2Table.querySelector('tbody');
    const newRow = document.createElement('tr');
    newRow.innerHTML = `
    <td class="agent_2_properties-column"><input type="text" placeholder="e.g. Synonym"></td>
    <td class="agent_2_description-column"><input type="text" placeholder="e.g. Whether the words in the word pair are synonyms."></td>
    <td><button class="delete-row-btn">Delete</button></td>
  `;
    tbody.appendChild(newRow);
});

// Modify addAgent3Button click handler to add Delete button in new row
addAgent3Button.addEventListener('click', function () {
    const tbody = agent3PropertiesTable.querySelector('tbody');
    const newRow = document.createElement('tr');
    newRow.innerHTML = `
    <td class="agent_3_properties-column"><input type="text" placeholder="e.g. Word Pair Frequency"></td>
    <td class="agent_3_description-column"><input type="text" placeholder="e.g. How frequent the word pair are used in English"></td>
    <td class="agent_3_minimum-column"><input type="number" min="0" placeholder="e.g. 0"></td>
    <td class="agent_3_maximum-column"><input type="number" min="0" placeholder="e.g. 10"></td>
    <td><button class="delete-row-btn">Delete</button></td>
  `;
    tbody.appendChild(newRow);
});
