from flask import Flask, request, jsonify, send_file, send_from_directory, redirect, url_for
from flask_cors import CORS
import json
import uuid
import os
import pickle
import re
from threading import Event, Thread, Lock
from functools import wraps
from multiprocessing import Value
from .backend import generate_stimuli, custom_model_inference_handler
from .csv_export import EXPORT_VERSION, export_csv_bytes, raw_csv_bytes, read_archived_csv, download_names
from collections import defaultdict
import io
import shutil
from flask_socketio import SocketIO, emit
import time


WEB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = Flask(__name__, static_folder=os.path.join(WEB_ROOT, 'static'))
CORS(app)
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False,
    ping_timeout=30,  # Reduced timeout
    ping_interval=10,  # Reduced interval
    http_compression=False,
    manage_session=False,
    allow_upgrades=True,  # Allow transport upgrades
    transports=['polling', 'websocket'],  # Explicit transport order
)

# Create a session store directory
SESSION_DIR = os.path.join(WEB_ROOT, 'sessions')
if not os.path.exists(SESSION_DIR):
    os.makedirs(SESSION_DIR)

# Global session state dictionary, save the object reference of active sessions
# Use a lock to protect access to the dictionary
active_sessions = {}
sessions_lock = Lock()

# Get the session file path


def get_session_file(session_id):
    if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise ValueError("Invalid session ID")
    return os.path.join(SESSION_DIR, f"{session_id}.pkl")


def write_archive_exports(session_id, entry, dataframe):
    directory = os.path.splitext(get_session_file(session_id))[0]
    os.makedirs(directory, exist_ok=True)
    filename = entry['filename']
    if os.path.basename(filename) != filename:
        raise ValueError('Invalid result filename')
    config = entry.get('export_config', {})
    variants = {
        filename: export_csv_bytes(dataframe, config),
        filename + '.detailed.csv': export_csv_bytes(dataframe, config, detailed=True),
        filename + '.raw.csv': raw_csv_bytes(dataframe),
    }
    for name, content in variants.items():
        destination = os.path.join(directory, name)
        temporary = destination + '.' + uuid.uuid4().hex + '.tmp'
        try:
            with open(temporary, 'wb') as output:
                output.write(content)
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
    entry['export_version'] = EXPORT_VERSION
    entry['download_name'], entry['detailed_download_name'] = download_names(
        entry['created_at'], entry['rows'], entry.get('partial', False))


def ensure_archive_exports(session_id, entry):
    directory = os.path.splitext(get_session_file(session_id))[0]
    path = os.path.join(directory, entry['filename'])
    if entry.get('export_version') == EXPORT_VERSION and os.path.isfile(path + '.detailed.csv'):
        return
    source = path + '.raw.csv' if os.path.isfile(path + '.raw.csv') else path
    if not os.path.isfile(source):
        return
    with open(source, 'rb') as archived:
        dataframe = read_archived_csv(archived.read())
    write_archive_exports(session_id, entry, dataframe)


def archive_generation(session_id, state, partial=False):
    """Keep both CSV variants and source records for each completed batch."""
    filename = state.get('generation_file')
    dataframe = state.get('dataframe')
    history = state.setdefault('generation_history', [])
    if not filename or dataframe is None or any(row['filename'] == filename for row in history):
        return
    entry = {'filename': filename, 'created_at': time.time(), 'rows': len(dataframe),
             'partial': bool(partial), 'export_config': state.get('export_config', {})}
    write_archive_exports(session_id, entry, dataframe)
    history.insert(0, entry)

# Save the session state to a file


def save_session(session_id, session_state):
    # Create a serializable session state copy
    serializable_state = {
        'generation_file': session_state['generation_file'],
        'error_message': session_state['error_message'],
        'current_iteration_value': session_state['current_iteration'].value,
        'total_iterations_value': session_state['total_iterations'].value,
        # Save stop_event state
        'stop_event_is_set': session_state['stop_event'].is_set(),
        'generation_history': session_state.get('generation_history', []),
        'export_config': session_state.get('export_config', {}),
    }

    # If there is a dataframe and it is not None, convert it to a CSV string and save it
    if session_state.get('dataframe') is not None:
        try:
            csv_data = raw_csv_bytes(session_state['dataframe']).decode('utf-8-sig')
            serializable_state['dataframe_csv'] = csv_data
        except Exception as e:
            print(
                f"Error serializing dataframe for session {session_id}: {str(e)}")

    try:
        session_file = get_session_file(session_id)
        temporary_file = session_file + '.' + uuid.uuid4().hex + '.tmp'
        try:
            with open(temporary_file, 'wb') as f:
                pickle.dump(serializable_state, f)
            os.replace(temporary_file, session_file)
        finally:
            if os.path.exists(temporary_file):
                os.remove(temporary_file)
    except Exception as e:
        print(f"Error saving session {session_id}: {str(e)}")

# Create a new session state


def create_session_state():
    state = {
        'stop_event': Event(),  # Control the generation interrupt event
        'generation_file': None,  # Store the generated file path
        'error_message': None,  # Store the error message
        # Shared variable, used to store the current iteration count
        'current_iteration': Value('i', 0),
        # Shared variable, used to store the total iteration count
        'total_iterations': Value('i', 1),
        'generation_thread': None,  # Store the generation thread
        'dataframe': None,  # Reset the dataframe
        'generation_history': [],
        'export_config': {}
    }
    return state

# Load the session state from a file or use the state in the global dictionary


def load_session(session_id):
    # First check if there is an active session in the global dictionary
    with sessions_lock:
        if session_id in active_sessions:
            return active_sessions[session_id]

    # If there is no active session in the global dictionary, try to load it from the file
    try:
        session_file = get_session_file(session_id)
        if os.path.exists(session_file):
            with open(session_file, 'rb') as f:
                serialized_state = pickle.load(f)

            # Create a complete session state
            session_state = create_session_state()
            session_state['generation_file'] = serialized_state.get(
                'generation_file')
            session_state['error_message'] = serialized_state.get(
                'error_message')
            session_state['generation_history'] = serialized_state.get('generation_history', [])
            session_state['export_config'] = serialized_state.get('export_config', {})

            with session_state['current_iteration'].get_lock():
                session_state['current_iteration'].value = serialized_state.get(
                    'current_iteration_value', 0)

            with session_state['total_iterations'].get_lock():
                session_state['total_iterations'].value = serialized_state.get(
                    'total_iterations_value', 1)

            # Restore the stop_event state
            if serialized_state.get('stop_event_is_set', False):
                session_state['stop_event'].set()
            else:
                session_state['stop_event'].clear()

            # Restore the dataframe (if it exists)
            if 'dataframe_csv' in serialized_state and serialized_state['dataframe_csv']:
                try:
                    import pandas as pd
                    import io
                    csv_data = serialized_state['dataframe_csv']
                    session_state['dataframe'] = pd.read_csv(
                        io.StringIO(csv_data), keep_default_na=False)
                except Exception as e:
                    print(
                        f"Error deserializing dataframe for session {session_id}: {str(e)}")

            # Add the loaded session state to the global dictionary
            with sessions_lock:
                active_sessions[session_id] = session_state

            return session_state
    except Exception as e:
        print(f"Error loading session {session_id}: {str(e)}")

    # If loading fails, return a new session state and add it to the global dictionary
    session_state = create_session_state()
    with sessions_lock:
        active_sessions[session_id] = session_state
    return session_state

# WebSocket callback function, used to send messages to the frontend


def websocket_send(session_id, message_type, message):
    """
    Send WebSocket messages to the frontend
    """
    try:
        if not session_id:
            return

        # Dimension-heavy JSON outputs need more room than ordinary status text.
        # Keep a bounded payload and let the frontend show a plain-text fallback
        # if an exceptionally large output still needs truncation.
        structured = isinstance(message, str) and re.match(r"^(Generator|Validator|Scorer)'s Output:", message)
        message_limit = 65536 if structured else 1000
        if isinstance(message, str) and len(message) > message_limit:
            message_preview = message[:message_limit] + "... [truncated]"
        else:
            message_preview = message

        message_data = {
            'session_id': session_id,
            'type': message_type,
            'message': message_preview,
            'timestamp': time.time()
        }

        # Send message directly but with error protection
        try:
            socketio.emit('stimulus_update', message_data, room=session_id)
        except Exception as e:
            print(f"WebSocket send error: {str(e)}")

    except Exception as e:
        print(f"Error in websocket_send: {str(e)}")

# health check endpoint, used for cloud service monitoring


@app.route("/health")
def health_check():
    return jsonify({
        "status": "ok",
        "timestamp": time.time(),
        "version": "1.0.0",
        "service": "stimulus-generator"
    })


@app.route("/")
def homepage():
    # Create a new session ID
    session_id = str(uuid.uuid4())
    # Redirect to the URL with the session ID
    return redirect(f"/{session_id}")


@app.route("/<session_id>")
def session_homepage(session_id):
    # Return the homepage HTML
    root_dir = WEB_ROOT
    return send_from_directory(root_dir, 'webpage.html')


@app.route('/static/<path:filename>')
def serve_static(filename):
    root_dir = WEB_ROOT
    return send_from_directory(os.path.join(root_dir, 'static'), filename)


# Serialize request setup, including thread assignment/start, without blocking workers.
generation_setup_lock = Lock()


def serialize_generation_setup(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        if not generation_setup_lock.acquire(blocking=False):
            return jsonify({'status': 'error', 'message': 'Generation setup is busy. Please retry.'}), 409
        try:
            return func(*args, **kwargs)
        finally:
            generation_setup_lock.release()
    return wrapped


@app.route('/<session_id>/generate_stimulus', methods=['POST'])
@serialize_generation_setup
def generate_stimulus(session_id):
    try:
        # Load or create the session state
        session_state = load_session(session_id)

        # Ensure the previous state is thoroughly cleaned
        with sessions_lock:
            if session_id in active_sessions:
                print(
                    f"Session {session_id} - Thoroughly cleaning previous state before new generation")

                # Do not reset shared state while its worker may still be using it.
                if session_state['generation_thread'] and session_state['generation_thread'].is_alive():
                    return jsonify({'status': 'error', 'message': 'Previous generation is still running. Stop it and wait before retrying.'}), 409

        data = request.get_json()
        if not isinstance(data, dict) or not data:
            error_msg = "Missing request data"
            return jsonify({'status': 'error', 'message': error_msg}), 400

        # Record more detailed request information, including the iteration count
        iteration_count = data.get('iteration', 'unknown')
        print(
            f"Session {session_id} - Starting new generation with {iteration_count} iterations.")

        # Create a WebSocket callback function for the current session
        def session_websocket_callback(message_type, message):
            websocket_send(session_id, message_type, message)

        # Verify that the necessary parameters exist
        required_fields = ['experimentDesign', 'iteration']
        for field in required_fields:
            if field not in data:
                error_msg = f"Missing required field: {field}"
                return jsonify({'status': 'error', 'message': error_msg}), 400

        # Verify that the iteration count is a positive integer
        try:
            if type(data['iteration']) is bool or isinstance(data['iteration'], float):
                raise ValueError('Iteration must be an integer')
            iteration = int(data['iteration'])
            if iteration <= 0:
                return jsonify({'status': 'error', 'message': 'Iteration must be a positive integer'}), 400
        except (ValueError, TypeError):
            return jsonify({'status': 'error', 'message': 'Iteration must be a valid number'}), 400

        # Check the model choice
        model_choice = data.get('modelChoice', '')
        if not model_choice:
            return jsonify({'status': 'error', 'message': 'Please select a model'}), 400

        try:
            parsed_properties = {key: json.loads(data.get(key, default)) for key, default in (('agent1Properties', '{}'), ('agent2Properties', '{}'), ('agent3Properties', '{}'), ('previousStimuli', '[]'))}
        except (ValueError, TypeError):
            return jsonify({'status': 'error', 'message': 'Invalid JSON in agent properties or previous stimuli'}), 400

        settings = {
            'agent_1_properties': parsed_properties['agent1Properties'],
            'agent_2_properties': parsed_properties['agent2Properties'],
            'agent_3_properties': parsed_properties['agent3Properties'],
            'api_key': data.get('apiKey', ''),
            'model_choice': model_choice,
            'experiment_design': data['experimentDesign'],
            'previous_stimuli': parsed_properties['previousStimuli'],
            'iteration': iteration,
            'stop_event': session_state['stop_event'],
            'current_iteration': session_state['current_iteration'],
            'total_iterations': session_state['total_iterations'],
            'session_id': session_id,
            'websocket_callback': session_websocket_callback,
            'agent_2_individual_validation': data.get('agent2IndividualValidation', False),
            'agent_3_individual_scoring': data.get('agent3IndividualScoring', False),
            'avoid_duplication_fields': data.get('avoidDuplicationFields', []),
        }

        # Add custom model parameters if custom model is selected
        if model_choice == 'custom':
            settings['apiUrl'] = data.get('apiUrl', '')
            settings['modelName'] = data.get('modelName', '')
            settings['params'] = data.get('params', None)
            print(
                f"Session {session_id} - Custom model parameters: URL={settings['apiUrl']}, Model={settings['modelName']}")

        for name in ('agent_1_properties', 'agent_2_properties', 'agent_3_properties'):
            if not isinstance(settings[name], dict):
                return jsonify({'status': 'error', 'message': 'Agent properties must be JSON objects'}), 400
        if not isinstance(settings['previous_stimuli'], list):
            return jsonify({'status': 'error', 'message': 'Previous stimuli must be a JSON array'}), 400
        fields = settings['avoid_duplication_fields']
        if (not isinstance(fields, list) or any(not isinstance(field, str) or
                field not in settings['agent_1_properties'] for field in fields)):
            return jsonify({'status': 'error', 'message': 'Invalid avoid duplication fields'}), 400
        # Keep uniqueness elements first even when a client serializes JSON keys
        # in a different order (for example, numeric condition names).
        properties = settings['agent_1_properties']
        ordered_names = list(dict.fromkeys(fields + list(properties)))
        settings['agent_1_properties'] = {name: properties[name] for name in ordered_names}
        settings['previous_stimuli'] = [
            {name: stimulus[name] for name in dict.fromkeys(fields + list(stimulus)) if name in stimulus}
            if isinstance(stimulus, dict) else stimulus for stimulus in settings['previous_stimuli']]

        # Reset only after input validation has succeeded.
        with sessions_lock:
            archive_generation(session_id, session_state)
            session_state['export_config'] = {
                'element_fields': fields,
                'stimulus_fields': list(settings['agent_1_properties']),
                'score_fields': list(settings['agent_3_properties']),
                'validation_fields': list(settings['agent_2_properties']),
            }
            # Reset all states
            # Clear the previous stop signal
            session_state['stop_event'].clear()
            # Reset the generated file path
            session_state['generation_file'] = None
            # Clear the error message before each generation
            session_state['error_message'] = None
            session_state['dataframe'] = None  # Reset the dataframe
            # Clear the old thread reference
            session_state['generation_thread'] = None

            # Ensure the current iteration count is reset to zero
            with session_state['current_iteration'].get_lock():
                session_state['current_iteration'].value = 0

            # Save the cleared state, ensuring persistence
            save_session(session_id, session_state)

        # Initialize the total iteration count
        with session_state['total_iterations'].get_lock():
            session_state['total_iterations'].value = settings['iteration']

        # Save the updated session state
        save_session(session_id, session_state)

        # Create a callback function, used to update the session state
        def update_session_callback():
            # Save the updated session state
            save_session(session_id, session_state)
            with session_state['current_iteration'].get_lock(), session_state['total_iterations'].get_lock():
                # Ensure a valid denominator (not 0)
                denominator = max(1, session_state['total_iterations'].value)
                progress = (
                    session_state['current_iteration'].value / denominator) * 100
                # Avoid floating point precision issues causing abnormal progress display
                progress = min(100, max(0, progress))
                # Ensure the progress is an integer value, avoiding small numbers on the frontend
                progress = int(round(progress))

            print(
                f"Session {session_id} updated - Progress: {progress}%, Current: {session_state['current_iteration'].value}, Total: {session_state['total_iterations'].value}")
            # Send the progress update through WebSocket
            try:
                socketio.emit('progress_update', {
                    'session_id': session_id,
                    'progress': progress,
                    'timestamp': time.time()
                }, namespace='/', room=session_id)
            except Exception as e:
                print(f"Error sending progress update: {str(e)}")

        # Add the callback function to settings
        settings['session_update_callback'] = update_session_callback

        def run_generation():
            try:
                # Send the start generation message
                websocket_send(session_id, 'all',
                               "Starting generation process...")

                # Check if there is a stop signal
                if session_state['stop_event'].is_set():
                    print(
                        f"Session {session_id} - Stop detected before generation start.")
                    websocket_send(session_id, 'all',
                                   "Generation stopped before it started.")
                    return

                # Generate data
                settings["ablation"] = {
                    "use_agent_2": True,
                    "use_agent_3": True
                }
                df, filename = generate_stimuli(settings)

                # Check if there is a stop signal - but still save partial data if available
                is_stopped = session_state['stop_event'].is_set()
                if is_stopped:
                    print(
                        f"Session {session_id} - Stop detected after generation completed.")
                    # Don't return immediately - continue to save any partial data

                # Verify the returned results
                print(settings["ablation"])
                if df is None or filename is None:
                    if is_stopped:
                        # Stopped before any data was generated
                        print(
                            f"Session {session_id} - Stopped with no data generated")
                        websocket_send(
                            session_id, 'all', "Generation stopped. No data was generated.")
                        return
                    else:
                        error_msg = "Generation process returned None for dataframe or filename"
                        print(f"Session {session_id} - {error_msg}")
                        session_state['error_message'] = error_msg
                        session_state['generation_file'] = None
                        websocket_send(session_id, 'error', error_msg)
                        return

                # Verify the number of generated stimuli
                if not is_stopped and settings["ablation"]["use_agent_2"] == True:
                    if len(df) != settings['iteration']:
                        warning_msg = f"Warning: Expected {settings['iteration']} stimuli but got {len(df)}"
                        print(f"Session {session_id} - {warning_msg}")
                        websocket_send(session_id, 'all', warning_msg)

                # Force using a new timestamp, ensuring the file name is unique
                import time
                timestamp = int(time.time())
                updated_filename = f"experiment_stimuli_results_{session_id}_{timestamp}_{uuid.uuid4().hex[:8]}.csv"

                # Ensure the generated dataframe is new and contains complete data
                print(
                    f"Session {session_id} - Received dataframe with {len(df)} rows from generate_stimuli")

                # Lock the session access to ensure thread safety
                with sessions_lock:
                    if session_id in active_sessions:
                        # Clear the old dataframe and file information
                        print(
                            f"Session {session_id} - Cleaning up old dataframe and file information")
                        session_state['dataframe'] = None
                        session_state['generation_file'] = None

                        # Force saving the empty state, ensuring old data is cleared
                        save_session(session_id, session_state)

                        # Then set the new data
                        # Use deep copy, ensuring data is not shared
                        session_state['dataframe'] = df.copy()
                        # Use the newly generated file name
                        session_state['generation_file'] = updated_filename
                        partial = is_stopped or len(df) < settings['iteration']
                        archive_generation(session_id, session_state, partial=partial)

                        # Record the completion status
                        if is_stopped:
                            print(
                                f"Session {session_id} - Generation stopped with partial data. File: {updated_filename}, Stimuli count: {len(df)}")
                            websocket_send(
                                session_id, 'all', f"Generation stopped. Saved {len(df)} stimuli.")
                            # Don't clear stop_event here - let status check handle it
                            # so it can detect this is a stopped generation with partial data
                        else:
                            print(
                                f"Session {session_id} - Generation completed successfully. New file: {updated_filename}, Stimuli count: {len(df)}")
                            websocket_send(
                                session_id, 'all', f"Generation completed. Generated {len(df)} stimuli.")

                        # Save the updated session state
                        save_session(session_id, session_state)
                    else:
                        print(
                            f"Session {session_id} - Warning: Session no longer active, cannot update state")
                        return
            except Exception as e:
                session_state['error_message'] = str(
                    e)  # Record the error message
                print(
                    f"Session {session_id} - Error during generation:", str(e))
                # Send the error message through WebSocket
                websocket_send(session_id, 'error', str(e))
                # Save the updated session state
                save_session(session_id, session_state)

        # Create and start the generation thread
        # Final verification before starting new thread
        with sessions_lock:
            if session_id in active_sessions:
                old_thread = session_state.get('generation_thread')
                if old_thread and old_thread.is_alive():
                    error_msg = f"Session {session_id} - Cannot start new generation: old thread is still running"
                    print(error_msg)
                    return jsonify({'status': 'error', 'message': 'Previous generation is still running. Please wait and try again.'}), 409

        session_state['generation_thread'] = Thread(target=run_generation)
        # Set as a daemon thread
        session_state['generation_thread'].daemon = True

        # Add thread information for debugging
        thread_id = session_state['generation_thread'].ident
        print(
            f"Session {session_id} - Starting new generation thread (ID will be available after start)")

        session_state['generation_thread'].start()

        # Get actual thread ID after start
        actual_thread_id = session_state['generation_thread'].ident
        print(
            f"Session {session_id} - New generation thread started with ID: {actual_thread_id}")

        return jsonify({
            'status': 'success',
            'message': 'Stimulus generation started.',
            'session_id': session_id,
            'total_iterations': settings['iteration']
        })
    except Exception as e:
        print(f"Unexpected error in generate_stimulus API: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500


@app.route('/<session_id>/generation_status', methods=['GET'])
def generation_status(session_id):
    # First try to get the session state from the global dictionary
    with sessions_lock:
        if session_id in active_sessions:
            session_state = active_sessions[session_id]

            # First check stop_event
            if session_state['stop_event'].is_set():
                # Check if the generation thread is still running
                thread_running = session_state['generation_thread'] and session_state['generation_thread'].is_alive(
                )

                if thread_running:
                    # Thread is still running, wait for it to save partial data
                    print(
                        f"Session {session_id} - Stop signal set, waiting for thread to save partial data...")
                    # Return running status so frontend keeps polling
                    progress = (session_state['current_iteration'].value /
                                session_state['total_iterations'].value) * 100
                    progress = min(100, max(0, progress))
                    return jsonify({'status': 'running', 'progress': progress, 'stopping': True})

                print(
                    f"Session {session_id} - Generation stopped by user (in-memory check).")
                # Thread has finished - check if there's partial data available for download
                if session_state['generation_file'] and session_state['dataframe'] is not None:
                    filename = session_state['generation_file']
                    row_count = len(session_state['dataframe'])
                    print(
                        f"Session {session_id} - Returning partial data file: {filename} with {row_count} rows")
                    websocket_send(session_id, 'all',
                                   f"Generation stopped. {row_count} stimuli saved.")
                    # Clear stop event so we don't keep returning stopped status
                    session_state['stop_event'].clear()
                    save_session(session_id, session_state)
                    return jsonify({'status': 'completed', 'file': filename, 'partial': True})
                else:
                    # No data to save
                    websocket_send(session_id, 'all',
                                   "Generation stopped by user.")
                    session_state['generation_file'] = None
                    save_session(session_id, session_state)
                    return jsonify({'status': 'stopped'})

            if session_state['error_message']:
                return jsonify({'status': 'error', 'error_message': session_state['error_message']})

            with session_state['current_iteration'].get_lock(), session_state['total_iterations'].get_lock():
                # Check if the thread is still running
                thread_running = session_state['generation_thread'] and session_state['generation_thread'].is_alive(
                )

                # Get the current progress
                progress = (session_state['current_iteration'].value /
                            session_state['total_iterations'].value) * 100
                # Ensure the progress is within 0-100 range
                progress = min(100, max(0, progress))
                print(
                    f"Session {session_id} - Progress: {progress:.2f}%, Current: {session_state['current_iteration'].value}, Total: {session_state['total_iterations'].value}, Thread running: {thread_running}")

                # Only when the iteration is complete, the file is generated, and the generation thread is completed, it is truly completed
                if (session_state['current_iteration'].value == session_state['total_iterations'].value
                        and session_state['generation_file']
                        and not thread_running):

                    # Check if the file name contains the current session ID, avoiding returning files from other sessions
                    filename = session_state['generation_file']
                    if session_id in filename:
                        # Output file information for debugging
                        print(f"Returning completed file: {filename}")
                        return jsonify({'status': 'completed', 'file': filename})
                    else:
                        # The file name does not match the current session, possibly an incorrect file
                        print(
                            f"Warning: File {filename} does not match session {session_id}")
                        session_state['error_message'] = "Generated file does not match current session"
                        return jsonify({'status': 'error', 'error_message': 'Generated file does not match session'})
                else:
                    # If the thread is completed but the progress is incomplete or no file is produced, it may be an error during generation
                    if progress >= 100 and not thread_running and not session_state['generation_file']:
                        session_state['error_message'] = "Generation completed but no file was produced"
                        return jsonify({'status': 'error', 'error_message': 'Generation completed but no file was produced. Please refresh the page and try again.'})

                    return jsonify({'status': 'running', 'progress': progress})

    # If there is no active session in the global dictionary, fall back to loading from the file
    session_state = load_session(session_id)

    # First check stop_event
    if session_state['stop_event'].is_set():
        print(f"Session {session_id} - Generation stopped by user.")
        # Check if there's partial data available for download
        if session_state['generation_file'] and session_state.get('dataframe') is not None:
            filename = session_state['generation_file']
            row_count = len(session_state['dataframe'])
            print(
                f"Session {session_id} - Returning partial data file (from disk): {filename} with {row_count} rows")
            websocket_send(session_id, 'all',
                           f"Generation stopped. {row_count} stimuli saved.")
            session_state['stop_event'].clear()
            save_session(session_id, session_state)
            return jsonify({'status': 'completed', 'file': filename, 'partial': True})
        else:
            websocket_send(session_id, 'all', "Generation stopped by user.")
            session_state['generation_file'] = None
            save_session(session_id, session_state)
            return jsonify({'status': 'stopped'})

    if session_state['error_message']:
        return jsonify({'status': 'error', 'error_message': session_state['error_message']})

    with session_state['current_iteration'].get_lock(), session_state['total_iterations'].get_lock():
        progress = (session_state['current_iteration'].value /
                    session_state['total_iterations'].value) * 100
        # Ensure the progress is within 0-100 range
        progress = min(100, max(0, progress))
        print(
            f"Session {session_id} - Progress: {progress:.2f}%, Current: {session_state['current_iteration'].value}, Total: {session_state['total_iterations'].value}")

        # When loading from a file, there is no thread information, so only based on progress and file situation to judge
        if session_state['current_iteration'].value == session_state['total_iterations'].value and session_state['generation_file']:
            # Check if the file name contains the current session ID
            filename = session_state['generation_file']
            if session_id in filename:
                print(f"Returning completed file (from disk): {filename}")
                return jsonify({'status': 'completed', 'file': filename})
            else:
                print(
                    f"Warning: File {filename} does not match session {session_id}")
                session_state['error_message'] = "Generated file does not match current session"
                return jsonify({'status': 'error', 'error_message': 'Generated file does not match session'})
        else:
            return jsonify({'status': 'running', 'progress': progress})


@app.route('/<session_id>/stop_generation', methods=['POST'])
def stop_generation(session_id):
    # First try to get the session state from the global dictionary
    with sessions_lock:
        if session_id in active_sessions:
            session_state = active_sessions[session_id]
            # Directly set the stop_event in memory
            session_state['stop_event'].set()
            # Don't clear generation_file here - let the generation thread save partial data
            # The status check will return the file if partial data is available
            print(
                f"Session {session_id} - Stop signal set directly in memory. Generation will be stopped and partial data saved.")
            # Send the stop message through WebSocket
            websocket_send(
                session_id, 'all', "Stopping... Please wait for partial data to be saved.")
            # Still save to file for persistence
            save_session(session_id, session_state)
            return jsonify({'message': 'Stopping generation. Partial data will be saved if available.'})

    # If there is no active session in the global dictionary, fall back to loading from the file
    session_state = load_session(session_id)
    # Set the stop signal
    session_state['stop_event'].set()
    # Don't clear generation_file - let the generation thread save partial data
    # Send the stop message through WebSocket
    websocket_send(session_id, 'all',
                   "Stopping... Please wait for partial data to be saved.")
    print(
        f"Session {session_id} - Stop signal set. Generation will be stopped.")
    # Save the updated state
    save_session(session_id, session_state)
    return jsonify({'message': 'Stopping generation. Partial data will be saved if available.'})


@app.route('/<session_id>/generation_history', methods=['GET'])
def generation_history(session_id):
    state = load_session(session_id)
    with sessions_lock:
        archive_generation(session_id, state)
        for entry in state['generation_history']:
            ensure_archive_exports(session_id, entry)
        save_session(session_id, state)
        history = [{key: value for key, value in entry.items() if key != 'export_config'}
                   for entry in state['generation_history']]
    return jsonify({'history': history})


@app.route('/<session_id>/download/<filename>', methods=['GET'])
def download_file(session_id, filename):
    variant = request.args.get('variant', 'wide')
    if variant not in ('wide', 'detailed'):
        return jsonify({'message': 'Unknown CSV variant.'}), 400
    state = load_session(session_id)
    with sessions_lock:
        archive_generation(session_id, state)
        entry = next((row for row in state['generation_history']
                      if row['filename'] == filename), None)
        if not entry:
            return jsonify({'message': 'Requested result is not available in this session.'}), 404
        ensure_archive_exports(session_id, entry)
        suffix = '.detailed.csv' if variant == 'detailed' else ''
        path = os.path.join(os.path.splitext(get_session_file(session_id))[0], filename + suffix)
        if not os.path.isfile(path):
            return jsonify({'message': 'This result has expired.'}), 404
        download_name = entry.get('detailed_download_name' if variant == 'detailed' else 'download_name', filename)
        save_session(session_id, state)
    return send_file(path, as_attachment=True, download_name=download_name,
                     mimetype='text/csv; charset=utf-8', max_age=0)


# WebSocket initialization event
@socketio.on('connect')
def handle_connect():
    """
    Handle WebSocket connection event - simplified to avoid WSGI conflicts
    """
    try:
        # Get basic client info
        client_sid = request.sid if request and hasattr(
            request, 'sid') else None
        session_id = None

        try:
            if request and hasattr(request, 'args'):
                session_id = request.args.get('session_id')
        except:
            pass

        print(f'Client connected: {client_sid}, Session ID: {session_id}')

        # Do NOT perform any operations that might write to the response here
        # Just return True to allow the connection
        return True

    except Exception as e:
        print(f"Error in connection handler: {str(e)}")
        return True


@socketio.on('join_session')
def handle_join_session(data):
    """
    Handle explicit join session request from client after connection is established
    """
    try:
        client_sid = request.sid if request and hasattr(
            request, 'sid') else None
        if not client_sid:
            return

        session_id = data.get('session_id') if data else None
        if not session_id:
            return

        # Join room safely after connection is fully established
        from flask_socketio import join_room
        join_room(session_id)
        print(f'Client {client_sid} joined room {session_id}')

        # Send confirmation
        socketio.emit('server_status', {
            'status': 'connected',
            'message': f'Joined room {session_id}',
            'room_joined': True,
            'session_id': session_id
        }, room=client_sid)
        print(f'Sent confirmation to client {client_sid}')

    except Exception as e:
        print(f"Error in join_session handler: {str(e)}")


@socketio.on('disconnect')
def handle_disconnect(disconnect_reason=None):
    """
    Handle WebSocket disconnection event
    This function is called when a client disconnects from the WebSocket server
    """
    try:
        # Get client SID safely
        client_sid = request.sid if request and hasattr(
            request, 'sid') else "unknown"
        print(
            f'Client disconnected: {client_sid}, reason: {disconnect_reason}')

        # No need to explicitly leave rooms - Socket.IO does this automatically
        # But we can add additional cleanup if needed in the future
    except Exception as e:
        # Just log the error, don't try to send any messages (client is already disconnected)
        print(f"Error in disconnect handler: {str(e)}")

    # Return immediately to complete the disconnection process
    return


@socketio.on('ping')
def handle_ping(data):
    """
    Handle ping messages from clients to keep connections alive
    """
    try:
        client_sid = request.sid if request and hasattr(
            request, 'sid') else None
        if not client_sid:
            return

        response = {
            'time': data.get('time', 0) if data else 0,
            'server_time': time.time()
        }

        try:
            socketio.emit('pong', response, room=client_sid)
        except Exception as e:
            print(f"Pong error: {str(e)}")

    except Exception as e:
        print(f"Error in ping handler: {str(e)}")

    return


# Add session destruction function
def cleanup_session(session_id):
    """Remove the specified session from the global dictionary"""
    with sessions_lock:
        if session_id in active_sessions:
            # Ensure any running threads are stopped
            session_state = active_sessions[session_id]
            session_state['stop_event'].set()
            if session_state['generation_thread'] and session_state['generation_thread'].is_alive():
                try:
                    # Try to wait for the thread to end on its own
                    session_state['generation_thread'].join(timeout=0.5)
                except Exception as e:
                    print(
                        f"Error joining thread for session {session_id}: {str(e)}")

            # Remove from the dictionary
            del active_sessions[session_id]
            print(f"Session {session_id} removed from active sessions.")
            return True
    return False


# Modify the cleanup expired session function, including sessions in memory
def cleanup_sessions():
    import time
    import glob

    # Get all session files
    session_files = glob.glob(os.path.join(SESSION_DIR, '*.pkl'))
    current_time = time.time()

    for session_file in session_files:
        # Get the last modified time of the file
        file_mod_time = os.path.getmtime(session_file)
        # If the file has not been modified in the last 24 hours, delete it
        if current_time - file_mod_time > 86400:  # 24 hours = 86400 seconds
            try:
                # Extract the session ID from the file name
                session_id = os.path.basename(session_file).split('.')[0]
                # Clean up the session in the global dictionary
                cleanup_session(session_id)
                # Delete the file
                os.remove(session_file)
                shutil.rmtree(os.path.splitext(session_file)[0], ignore_errors=True)
                print(f"Removed expired session file: {session_file}")
            except Exception as e:
                print(
                    f"Failed to remove session file {session_file}: {str(e)}")

    # Additional check, clean up all sessions in the global dictionary that do not exist in the file
    with sessions_lock:
        active_session_ids = list(active_sessions.keys())

    for session_id in active_session_ids:
        session_file = get_session_file(session_id)
        if not os.path.exists(session_file):
            cleanup_session(session_id)
            print(f"Cleaned up orphaned session {session_id} from memory.")


# Add error handlers for Socket.IO
@socketio.on_error()
def handle_error(e):
    """
    Global error handler for all Socket.IO events
    This function is called when an error occurs during Socket.IO event handling
    """
    print(f"Socket.IO error: {str(e)}")
    # Don't try to send error messages here, as it might cause another error


@socketio.on_error_default
def handle_default_error(e):
    """
    Default error handler for Socket.IO events
    This function is called when an error occurs during Socket.IO event handling
    and no specific error handler exists
    """
    print(f"Socket.IO default error: {str(e)}")
    # Don't try to send error messages here, as it might cause another error


# Clean up expired sessions at startup
cleanup_sessions()


@app.route('/api/custom_model_inference', methods=['POST'])
def custom_model_inference():
    data = request.get_json()
    session_id = data.get('session_id')
    prompt = data.get('prompt')
    model = data.get('model')
    api_url = data.get('api_url')
    api_key = data.get('api_key')
    params = data.get('params')

    result, status_code = custom_model_inference_handler(
        session_id,
        prompt,
        model,
        api_url,
        api_key,
        params
    )
    return jsonify(result), status_code


if __name__ == '__main__':
    print("Starting Stimulus Generator server...")
    print("WebSocket server configured with:")
    print(f"  - Async mode: {socketio.async_mode}")
    print(f"  - Ping interval: 10s")
    print(f"  - Ping timeout: 30s")
    print(f"  - HTTP Compression: Disabled")
    print(f"  - Session Management: Disabled")

    # detect if running in production environment
    is_production = os.environ.get('PRODUCTION', 'false').lower() == 'true'

    # choose different configurations based on the environment
    if is_production:
        # production environment configuration
        print("Running in production mode")
        socketio.run(
            app,
            host='0.0.0.0',
            port=int(os.environ.get('PORT', 5000)),
            debug=False,
            allow_unsafe_werkzeug=True,
            log_output=False
        )
    else:
        # development environment configuration
        print("Running in development mode")
        socketio.run(
            app,
            host='0.0.0.0',
            port=5000,
            debug=True,
            allow_unsafe_werkzeug=True,
            log_output=True
        )
