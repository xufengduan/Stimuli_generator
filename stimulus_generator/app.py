from flask import Flask, request, jsonify, send_file, send_from_directory, redirect, url_for
from flask_cors import CORS
import json
import uuid
import os
import pickle
from threading import Event, Thread, Lock
from multiprocessing import Value
from .backend import generate_stimuli
from collections import defaultdict
import io
from flask_socketio import SocketIO, emit
import time


app = Flask(__name__, static_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static'))
CORS(app)
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,  # reduce log output
    engineio_logger=False,  # reduce engine log output
    ping_timeout=60,
    ping_interval=25,
    http_compression=False,
    manage_session=False,
    always_connect=True,  # ensure connection always established
    max_http_buffer_size=5 * 1024 * 1024  # increase buffer size to 5MB
)

# Create a session store directory
SESSION_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sessions')
if not os.path.exists(SESSION_DIR):
    os.makedirs(SESSION_DIR)

# Global session state dictionary, save the object reference of active sessions
# Use a lock to protect access to the dictionary
active_sessions = {}
sessions_lock = Lock()

# Get the session file path
def get_session_file(session_id):
    return os.path.join(SESSION_DIR, f"{session_id}.pkl")

# Save the session state to a file
def save_session(session_id, session_state):
    # Create a serializable session state copy
    serializable_state = {
        'generation_file': session_state['generation_file'],
        'error_message': session_state['error_message'],
        'current_iteration_value': session_state['current_iteration'].value,
        'total_iterations_value': session_state['total_iterations'].value,
        'stop_event_is_set': session_state['stop_event'].is_set(),  # Save stop_event state
    }
    
    # If there is a dataframe and it is not None, convert it to a CSV string and save it
    if session_state.get('dataframe') is not None:
        try:
            csv_data = session_state['dataframe'].to_csv(index=False)
            serializable_state['dataframe_csv'] = csv_data
        except Exception as e:
            print(f"Error serializing dataframe for session {session_id}: {str(e)}")
    
    try:
        with open(get_session_file(session_id), 'wb') as f:
            pickle.dump(serializable_state, f)
    except Exception as e:
        print(f"Error saving session {session_id}: {str(e)}")

# Create a new session state
def create_session_state():
    state = {
        'stop_event': Event(),  # Control the generation interrupt event
        'generation_file': None,  # Store the generated file path
        'error_message': None,  # Store the error message
        'current_iteration': Value('i', 0),  # Shared variable, used to store the current iteration count
        'total_iterations': Value('i', 1),  # Shared variable, used to store the total iteration count
        'generation_thread': None,  # Store the generation thread
        'dataframe': None  # Reset the dataframe
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
            session_state['generation_file'] = serialized_state.get('generation_file')
            session_state['error_message'] = serialized_state.get('error_message')
            
            with session_state['current_iteration'].get_lock():
                session_state['current_iteration'].value = serialized_state.get('current_iteration_value', 0)
            
            with session_state['total_iterations'].get_lock():
                session_state['total_iterations'].value = serialized_state.get('total_iterations_value', 1)
            
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
                    session_state['dataframe'] = pd.read_csv(io.StringIO(csv_data))
                except Exception as e:
                    print(f"Error deserializing dataframe for session {session_id}: {str(e)}")
            
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
    session_id: session ID
    message_type: message type (generator, validator, scorer, all, setup)
    message: the message content to send
    """
    try:
        # safe check: ensure session_id is valid
        if not session_id:
            print("Warning: Attempted to send WebSocket message with empty session_id")
            return
            
        # Truncate long messages to prevent Socket.IO issues
        if isinstance(message, str) and len(message) > 5000:
            message_preview = message[:5000] + "... [Message too long, truncated]"
        else:
            message_preview = message
            
        # build message data
        message_data = {
            'session_id': session_id, 
            'type': message_type, 
            'message': message_preview,
            'timestamp': time.time()
        }
        
        # use try-except to wrap the emit call to prevent connection issues from causing application crashes
        try:
            print(f"Sending {message_type} message to session {session_id}")
            socketio.emit('stimulus_update', message_data, namespace='/', room=session_id)
        except Exception as emit_error:
            print(f"Socket.IO emit error: {str(emit_error)}")
            # try alternative method - send directly to all connections
            try:
                socketio.emit('stimulus_update', message_data)
            except:
                pass  # if the alternative method also fails, silent handling
    except Exception as e:
        print(f"Error preparing WebSocket message: {str(e)}")

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
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return send_from_directory(root_dir, 'webpage.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return send_from_directory(os.path.join(root_dir, 'static'), filename)


@app.route('/<session_id>/generate_stimulus', methods=['POST'])
def generate_stimulus(session_id):
    try:
        # Load or create the session state
        session_state = load_session(session_id)
        
        # Ensure the previous state is thoroughly cleaned
        with sessions_lock:
            if session_id in active_sessions:
                print(f"Session {session_id} - Thoroughly cleaning previous state before new generation")
                
                # Stop any running threads
                session_state['stop_event'].set()
                if session_state['generation_thread'] and session_state['generation_thread'].is_alive():
                    try:
                        # Try to wait for the thread to end, but not too long
                        session_state['generation_thread'].join(timeout=0.5)
                    except Exception as e:
                        print(f"Session {session_id} - Error joining previous thread: {str(e)}")
                
                # Reset all states
                session_state['stop_event'].clear()  # Clear the previous stop signal
                session_state['generation_file'] = None  # Reset the generated file path
                session_state['error_message'] = None  # Clear the error message before each generation
                session_state['dataframe'] = None  # Reset the dataframe
                session_state['generation_thread'] = None  # Clear the old thread reference

                # Ensure the current iteration count is reset to zero
                with session_state['current_iteration'].get_lock():
                    session_state['current_iteration'].value = 0
                
                # Save the cleared state, ensuring persistence
                save_session(session_id, session_state)
        
        data = request.get_json()
        if not data:
            error_msg = "Missing request data"
            return jsonify({'status': 'error', 'message': error_msg}), 400
            
        # Record more detailed request information, including the iteration count
        iteration_count = data.get('iteration', 'unknown')
        print(f"Session {session_id} - Starting new generation with {iteration_count} iterations.")

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
            iteration = int(data['iteration'])
            if iteration <= 0:
                return jsonify({'status': 'error', 'message': 'Iteration must be a positive integer'}), 400
        except ValueError:
            return jsonify({'status': 'error', 'message': 'Iteration must be a valid number'}), 400

        # Check the model choice
        model_choice = data.get('modelChoice', '')
        if not model_choice:
            return jsonify({'status': 'error', 'message': 'Please select a model'}), 400

        settings = {
            'agent_1_properties': json.loads(data.get('agent1Properties', '{}')),
            'agent_2_properties': json.loads(data.get('agent2Properties', '{}')),
            'agent_3_properties': json.loads(data.get('agent3Properties', '{}')),
            'api_key': data.get('apiKey', ''),
            'model_choice': model_choice,
            'experiment_design': data['experimentDesign'],
            'previous_stimuli': json.loads(data.get('previousStimuli', '[]')),
            'iteration': iteration,
            'stop_event': session_state['stop_event'],
            'current_iteration': session_state['current_iteration'],
            'total_iterations': session_state['total_iterations'],
            'session_id': session_id,
            'websocket_callback': session_websocket_callback,
        }
        
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
                progress = (session_state['current_iteration'].value / denominator) * 100
                # Avoid floating point precision issues causing abnormal progress display
                progress = min(100, max(0, progress))
                # Ensure the progress is an integer value, avoiding small numbers on the frontend
                progress = int(round(progress))
                
            print(f"Session {session_id} updated - Progress: {progress}%, Current: {session_state['current_iteration'].value}, Total: {session_state['total_iterations'].value}")
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
                websocket_send(session_id, 'all', "Starting generation process...")
                
                # Check if there is a stop signal
                if session_state['stop_event'].is_set():
                    print(f"Session {session_id} - Stop detected before generation start.")
                    websocket_send(session_id, 'all', "Generation stopped before it started.")
                    return
                    
                # Generate data
                df, filename = generate_stimuli(settings)
                
                # Check if there is a stop signal again
                if session_state['stop_event'].is_set():
                    print(f"Session {session_id} - Stop detected after generation completed.")
                    return
                    
                # Verify the returned results
                if df is None or filename is None:
                    error_msg = "Generation process returned None for dataframe or filename"
                    print(f"Session {session_id} - {error_msg}")
                    session_state['error_message'] = error_msg
                    session_state['generation_file'] = None
                    websocket_send(session_id, 'error', error_msg)
                    return
                    
                # Verify the number of generated stimuli
                if len(df) != settings['iteration']:
                    warning_msg = f"Warning: Expected {settings['iteration']} stimuli but got {len(df)}"
                    print(f"Session {session_id} - {warning_msg}")
                    websocket_send(session_id, 'all', warning_msg)
                
                # Force using a new timestamp, ensuring the file name is unique
                import time
                timestamp = int(time.time())
                updated_filename = f"experiment_stimuli_results_{session_id}_{timestamp}.csv"
                
                # Ensure the generated dataframe is new and contains complete data
                print(f"Session {session_id} - Received dataframe with {len(df)} rows from generate_stimuli")
                
                # Lock the session access to ensure thread safety
                with sessions_lock:
                    if session_id in active_sessions:
                        # Clear the old dataframe and file information
                        print(f"Session {session_id} - Cleaning up old dataframe and file information")
                        session_state['dataframe'] = None
                        session_state['generation_file'] = None
                        
                        # Force saving the empty state, ensuring old data is cleared
                        save_session(session_id, session_state)
                        
                        # Then set the new data
                        session_state['dataframe'] = df.copy()  # Use deep copy, ensuring data is not shared
                        session_state['generation_file'] = updated_filename  # Use the newly generated file name
                        
                        # Record the successful completion
                        print(f"Session {session_id} - Generation completed successfully. New file: {updated_filename}, Stimuli count: {len(df)}")
                        websocket_send(session_id, 'all', f"Generation completed. Generated {len(df)} stimuli.")
                        
                        # Save the updated session state
                        save_session(session_id, session_state)
                    else:
                        print(f"Session {session_id} - Warning: Session no longer active, cannot update state")
                        return
            except Exception as e:
                session_state['error_message'] = str(e)  # Record the error message
                print(f"Session {session_id} - Error during generation:", str(e))
                # Send the error message through WebSocket
                websocket_send(session_id, 'error', str(e))
                # Save the updated session state
                save_session(session_id, session_state)

        # Create and start the generation thread
        session_state['generation_thread'] = Thread(target=run_generation)
        session_state['generation_thread'].daemon = True  # Set as a daemon thread
        session_state['generation_thread'].start()

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
                print(f"Session {session_id} - Generation stopped by user (in-memory check).")
                # Send additional WebSocket notification
                websocket_send(session_id, 'all', "Generation stopped by user.")
                # Clear the generation file field, ensuring that the previous file is not returned
                session_state['generation_file'] = None
                save_session(session_id, session_state)
                return jsonify({'status': 'stopped'})
                
            if session_state['error_message']:
                return jsonify({'status': 'error', 'error_message': session_state['error_message']})
            
            with session_state['current_iteration'].get_lock(), session_state['total_iterations'].get_lock():
                # Check if the thread is still running
                thread_running = session_state['generation_thread'] and session_state['generation_thread'].is_alive()
                
                # Get the current progress
                progress = (session_state['current_iteration'].value / session_state['total_iterations'].value) * 100
                progress = min(100, max(0, progress))  # Ensure the progress is within 0-100 range
                print(f"Session {session_id} - Progress: {progress:.2f}%, Current: {session_state['current_iteration'].value}, Total: {session_state['total_iterations'].value}, Thread running: {thread_running}")
                
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
                        print(f"Warning: File {filename} does not match session {session_id}")
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
        # If the stop signal is already set, ensure the frontend knows it has stopped
        print(f"Session {session_id} - Generation stopped by user.")
        # Send additional WebSocket notification
        websocket_send(session_id, 'all', "Generation stopped by user.")
        # Clear the generation file field, ensuring that the previous file is not returned
        session_state['generation_file'] = None
        save_session(session_id, session_state)
        return jsonify({'status': 'stopped'})
        
    if session_state['error_message']:
        return jsonify({'status': 'error', 'error_message': session_state['error_message']})
    
    with session_state['current_iteration'].get_lock(), session_state['total_iterations'].get_lock():
        progress = (session_state['current_iteration'].value / session_state['total_iterations'].value) * 100
        progress = min(100, max(0, progress))  # Ensure the progress is within 0-100 range
        print(f"Session {session_id} - Progress: {progress:.2f}%, Current: {session_state['current_iteration'].value}, Total: {session_state['total_iterations'].value}")
        
        # When loading from a file, there is no thread information, so only based on progress and file situation to judge
        if session_state['current_iteration'].value == session_state['total_iterations'].value and session_state['generation_file']:
            # Check if the file name contains the current session ID
            filename = session_state['generation_file'] 
            if session_id in filename:
                print(f"Returning completed file (from disk): {filename}")
                return jsonify({'status': 'completed', 'file': filename})
            else:
                print(f"Warning: File {filename} does not match session {session_id}")
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
            # Clear the previous file information, preventing the return of old files
            session_state['generation_file'] = None
            print(f"Session {session_id} - Stop signal set directly in memory. Generation will be stopped immediately.")
            save_session(session_id, session_state)  # Still save to file for persistence
            return jsonify({'message': 'Stimulus generation successfully stopped.'})
    
    # If there is no active session in the global dictionary, fall back to loading from the file
    session_state = load_session(session_id)
    # Set the stop signal
    session_state['stop_event'].set()
    # Clear the previous file information, preventing the return of old files
    session_state['generation_file'] = None
    # Send the stop message through WebSocket
    websocket_send(session_id, 'all', "Stopping... Please wait.")
    print(f"Session {session_id} - Stop signal set. Generation will be stopped.")
    # Save the updated state
    save_session(session_id, session_state)
    return jsonify({'message': 'Stimulus generation successfully stopped.'})


@app.route('/<session_id>/download/<filename>', methods=['GET'])
def download_file(session_id, filename):
    # Load the session state
    session_state = load_session(session_id)
    
    # Check if there is a dataframe available
    if session_state.get('dataframe') is None:
        print(f"Error: No dataframe available for session {session_id}")
        return jsonify({'message': 'No data available for download.'}), 404
    
    # Compare the requested file name with the file name in the current session state
    stored_filename = session_state.get('generation_file')
    if stored_filename != filename:
        print(f"Warning: Requested file {filename} does not match current session file {stored_filename}")
        # Force verification: if the file name does not match, reject the request instead of continuing
        return jsonify({'message': 'Requested file does not match current session file'}), 400
    
    try:
        # Check if the requested filename contains a session ID
        if session_id not in filename:
            print(f"Error: Requested file {filename} does not contain session ID {session_id}")
            return jsonify({'message': 'Invalid file request: session ID mismatch'}), 400
        
        # Get or create a dataframe copy with timestamp, ensuring data uniqueness
        df_to_download = session_state['dataframe'].copy()
        
        # Add download time column, ensuring different content each time
        current_timestamp = int(time.time())
        df_to_download['download_timestamp'] = current_timestamp
        
        # Create a temporary memory file object
        buffer = io.StringIO()
        
        # Write the dataframe to the buffer
        df_to_download.to_csv(buffer, index=False)
        buffer.seek(0)  # Move the pointer back to the beginning
        
        print(f"Serving file {filename} with {len(df_to_download)} rows for session {session_id}")
        
        # After download, clear the dataframe and file name in the session to avoid repeated download of old data
        # Create a delayed cleanup function
        def delayed_cleanup():
            time.sleep(2)  # Wait 2 seconds to ensure the file has been fully downloaded
            with sessions_lock:
                if session_id in active_sessions:
                    session_state = active_sessions[session_id]
                    old_filename = session_state.get('generation_file')
                    if old_filename == filename:  # Ensure we do not clear the new generation results
                        print(f"Cleaning up dataframe and filename for session {session_id} after download")
                        session_state['dataframe'] = None
                        session_state['generation_file'] = None
                        save_session(session_id, session_state)
        
        # Execute cleanup in the background thread, not blocking the current request
        cleanup_thread = Thread(target=delayed_cleanup)
        cleanup_thread.daemon = True
        cleanup_thread.start()
        
        # Return the CSV file from memory
        try:
            # Try using the newer version of Flask's parameter name
            return send_file(
                io.BytesIO(buffer.getvalue().encode()),
                as_attachment=True,
                download_name=filename,
                mimetype='text/csv'
            )
        except TypeError:
            # If failed, try using the older version of Flask's parameter name
            return send_file(
                io.BytesIO(buffer.getvalue().encode()),
                as_attachment=True,
                attachment_filename=filename,
                mimetype='text/csv'
            )
    except Exception as e:
        print(f"Error generating download file: {str(e)}")
        return jsonify({'message': f'Error generating file: {str(e)}'}), 500


# WebSocket initialization event
@socketio.on('connect')
def handle_connect():
    # use exception handling to wrap the entire connection processing process
    try:
        # Get the client's session ID
        client_sid = request.sid
        if not client_sid:
            print("Warning: Client connected but no SID available")
            return
            
        # safely get session_id, avoid attribute error
        session_id = None
        try:
            if request and hasattr(request, 'args'):
                session_id = request.args.get('session_id')
        except Exception as args_error:
            print(f"Error getting session_id from args: {args_error}")
            
        print(f'Client connected: {client_sid}, Session ID: {session_id}')
        
        # if session_id is provided, join the corresponding room
        if session_id:
            # use a safer way to join the room
            try:
                # delay a short time before joining the room to avoid write() error
                socketio.sleep(0.1)
                
                # join room
                socketio.server.enter_room(client_sid, session_id, namespace='/')
                print(f'Client {client_sid} joined room {session_id}')
                
                # try to send a simplified confirmation message
                socketio.sleep(0.1)
                
                # send connection confirmation message
                status_data = {
                    'status': 'connected', 
                    'message': f'Connection established and joined room {session_id}',
                    'room_joined': True,
                    'session_id': session_id
                }
                
                # first try to send to the specific room
                try:
                    socketio.emit('server_status', status_data, room=session_id, namespace='/')
                    print(f'Sent confirmation to room {session_id}')
                except Exception as room_emit_error:
                    print(f"Error sending to room: {room_emit_error}")
                    # if sending to room fails, try to send directly to the client
                    socketio.emit('server_status', status_data, room=client_sid, namespace='/')
            except Exception as room_error:
                print(f"Error with room operations: {room_error}")
                # if room joining fails, send a failure status message
                socketio.emit('server_status', {
                    'status': 'connected', 
                    'message': 'Connection established but room joining failed',
                    'room_joined': False,
                    'session_id': session_id
                }, room=client_sid, namespace='/')
        else:
            # no session_id situation
            print(f"Warning: Client {client_sid} connected without a session_id")
            socketio.emit('server_status', {
                'status': 'connected', 
                'message': 'Connection established without session ID',
                'room_joined': False
            }, room=client_sid, namespace='/')
    except Exception as e:
        print(f"Error in connection handler: {str(e)}")
        # try to send a simplified confirmation message
        try:
            if 'client_sid' in locals():
                socketio.emit('server_status', {'status': 'error', 'error': str(e)}, room=client_sid, namespace='/')
        except:
            print("Failed to send error message to client")


@socketio.on('disconnect')
def handle_disconnect():
    print(f'Client disconnected: {request.sid}')


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
                    print(f"Error joining thread for session {session_id}: {str(e)}")
            
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
                print(f"Removed expired session file: {session_file}")
            except Exception as e:
                print(f"Failed to remove session file {session_file}: {str(e)}")
    
    # Additional check, clean up all sessions in the global dictionary that do not exist in the file
    with sessions_lock:
        active_session_ids = list(active_sessions.keys())
    
    for session_id in active_session_ids:
        session_file = get_session_file(session_id)
        if not os.path.exists(session_file):
            cleanup_session(session_id)
            print(f"Cleaned up orphaned session {session_id} from memory.")


# Add a new API endpoint for handling Hugging Face API call requests
@app.route('/api/huggingface_inference', methods=['POST'])
def huggingface_inference():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'Missing request data'}), 400
        
        # Get the parameters from the request
        prompt = data.get('prompt')
        model = data.get('model')
        session_id = data.get('session_id')
        
        if not prompt or not model:
            return jsonify({'status': 'error', 'message': 'Missing required parameters'}), 400
        
        # import HuggingFace client
        from huggingface_hub import InferenceClient
        
        # Import the API key from backend.py
        from .backend import HF_API_KEY
        
        # Create the client
        client = InferenceClient(
            model, 
            token=HF_API_KEY,
            headers={"x-use-cache": "false"}  # Disable cache, ensure new responses
        )
        
        # Build the message
        messages = [{"role": "user", "content": prompt}]
        
        # Call the API
        response = client.chat_completion(
            messages=messages,
            max_tokens=2000,
            temperature=0.7
        )
        
        # Extract the response content
        content = response.choices[0].message.content
        
        return jsonify({
            'status': 'success',
            'response': content
        })
    except ImportError as e:
        return jsonify({'status': 'error', 'message': f'Import error: {str(e)}'}), 500
    except Exception as e:
        print(f"Error in huggingface_inference API: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500


# Clean up expired sessions at startup
cleanup_sessions()

if __name__ == '__main__':
    print("Starting Stimulus Generator server...")
    print("WebSocket server configured with:")
    print(f"  - Async mode: {socketio.async_mode}")
    print(f"  - Ping interval: 25s")
    print(f"  - Ping timeout: 60s")
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
