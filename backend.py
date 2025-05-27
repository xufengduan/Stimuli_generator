import openai
import pandas as pd
import json
from huggingface_hub import InferenceClient
import time
import random

# Set OpenAI API key
openai.api_key = ""

# Set Hugging Face API key
HF_API_KEY = "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"

# ======================
# 1. Configuration (Prompt + Schema)
# ======================
# ---- Agent 1 Prompt ----
AGENT_1_PROMPT_TEMPLATE = """\
Please help me construct one item as stimuli for a psycholinguistic experiment based on the description: 

Experimental stimuli design: {experiment_design}

Existing stimuli: {previous_stimuli}

Requirement: {generation_requirements} Please return in JSON format.
"""

# ---- Agent 2 Prompt ----
AGENT_2_PROMPT_TEMPLATE = """\
Please verify the following NEW STIMULUS with utmost precision, ensuring they meet the Experimental stimuli design and following strict criteria.

NEW STIMULUS: {new_stimulus};

Experimental stimuli design: {experiment_design}
"""

# ---- Agent 3 Prompt ----
AGENT_3_PROMPT_TEMPLATE = """\
Please rate the following STIMULUS based on the Experimental stimuli design provided for a psychological experiment:

STIMULUS: {valid_stimulus}
Experimental stimuli design: {experiment_design}

Please return in JSON format, including the score for each dimension and the total score for all dimensions.
"""

# ---- Agent 1 Stimulus Schema ----
AGENT_1_PROPERTIES = {}

# ---- Agent 2 Validation Result Schema ----
AGENT_2_PROPERTIES = {}

# ---- Agent 3 Scoring Result Schema ----
AGENT_3_PROPERTIES = {}


# ======================
# 2. Core Agent Functions
# ======================
def check_stimulus_repetition(new_stimulus_dict, previous_stimuli_list):
    """
    If the value of any key (dimension) in new_stimulus_dict is exactly the same as the corresponding value in any stimulus in previous_stimuli_list, it is considered a repetition.
    """
    for existing_stimulus in previous_stimuli_list:
        for key, new_value in new_stimulus_dict.items():
            # If the key exists in existing_stimulus and the values are the same, it is considered a repetition
            if key in existing_stimulus and existing_stimulus[key].lower() == str(new_value.lower()):
                return True

    return False


def agent_1_generate_stimulus(
        experiment_design,
        previous_stimuli,
        prompt_template=AGENT_1_PROMPT_TEMPLATE,
        properties=None,
        params=None,
        stop_event=None):
    """
    Agent 1: Generate new stimulus, return dictionary format.
    """
    if stop_event and stop_event.is_set():
        print("Generation stopped by user in agent_1_generate_stimulus.")
        return {"stimulus": "STOPPED"}
        
    if properties is None:
        properties = AGENT_1_PROPERTIES
    if params is None:
        params = {"temperature": 0.7, "max_tokens": 200, "model": "gpt-4o"}
    
    # Use fixed generation_requirements
    generation_requirements = "Please generate a new stimulus in the same format as the existing stimuli, and ensure that the new stimulus is different from those in the existing stimuli."

    prompt = prompt_template.format(
        experiment_design=experiment_design,
        previous_stimuli=previous_stimuli,
        generation_requirements=generation_requirements
    )

    response = openai.ChatCompletion.create(
        model=params["model"],
        messages=[{"role": "user", "content": prompt}],
        temperature=params["temperature"],
        max_tokens=params["max_tokens"],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "validation_schema",
                "schema": {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties.keys()),
                    "additionalProperties": False
                }}
        }
    )

    # Check stop event again
    if stop_event and stop_event.is_set():
        print("Generation stopped by user after API call in agent_1_generate_stimulus.")
        return {"stimulus": "STOPPED"}

    try:
        # response['choices'][0]['message']['content'] should be a JSON string
        new_stimulus = json.loads(response['choices'][0]['message']['content'])
    except json.JSONDecodeError:
        print("Failed to parse JSON response:", response)
        # If parsing fails, return a default object, or throw an error
        new_stimulus = {
            "stimulus": "ERROR/ERROR",
        }

    return new_stimulus


def agent_2_validate_stimulus(
        new_stimulus,
        experiment_design,
        previous_stimuli,
        prompt_template=AGENT_2_PROMPT_TEMPLATE,
        properties=None,
        params=None,
        stop_event=None):
    """
    Agent 2: Validate experimental stimulus
    """
    if stop_event and stop_event.is_set():
        print("Generation stopped by user in agent_2_validate_stimulus.")
        return {"Overall": "failed", "reason": "Stopped by user"}
        
    if properties is None:
        properties = AGENT_2_PROPERTIES
    if params is None:
        params = {"temperature": 0, "max_tokens": 100, "model": "gpt-4o"}

    # Automatically set all properties' keys as required
    required_fields = list(properties.keys())

    prompt = prompt_template.format(
        experiment_design=experiment_design,
        new_stimulus=new_stimulus
    )

    response = openai.ChatCompletion.create(
        model=params["model"],
        messages=[{"role": "user", "content": prompt}],
        temperature=params["temperature"],
        max_tokens=params["max_tokens"],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "validation_schema",
                "schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required_fields,
                    "additionalProperties": False
                }
            }
        }
    )

    # Check stop event again
    if stop_event and stop_event.is_set():
        print("Generation stopped by user after API call in agent_2_validate_stimulus.")
        return {"Overall": "failed", "reason": "Stopped by user"}

    try:
        result = json.loads(response['choices'][0]['message']['content'])
    except json.JSONDecodeError:
        print("Failed to parse JSON response:", response)
        result = {"status": "failed", "reason": "Failed to validate stimulus"}

    return result


def agent_3_score_stimulus(
        valid_stimulus,
        experiment_design,
        prompt_template=AGENT_3_PROMPT_TEMPLATE,
        properties=None,
        params=None,
        stop_event=None):
    """
    Agent 3: Score experimental stimulus
    """
    if stop_event and stop_event.is_set():
        print("Generation stopped by user in 'Validator'.")
        return {field: 0 for field in properties.keys()} if properties else {"total_score": 0}
        
    if properties is None:
        properties = AGENT_3_PROPERTIES
    if params is None:
        params = {"temperature": 0.7, "max_tokens": 200, "model": "gpt-4o"}

    required_fields = list(properties.keys())

    prompt = prompt_template.format(
        experiment_design=experiment_design,
        valid_stimulus=valid_stimulus,
    )

    response = openai.ChatCompletion.create(
        model=params["model"],
        messages=[{"role": "user", "content": prompt}],
        temperature=params["temperature"],
        max_tokens=params["max_tokens"],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "scoring_schema",
                "schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required_fields,
                    "additionalProperties": False
                }
            }
        }
    )
    
    # Check stop event again
    if stop_event and stop_event.is_set():
        print("Generation stopped by user in 'Scorer'.")
        return {field: 0 for field in properties.keys()} if properties else {"total_score": 0}

    try:
        return json.loads(response['choices'][0]['message']['content'])
    except json.JSONDecodeError:
        print("Failed to parse JSON response:", response)
        # If parsing fails, return a default/empty scoring object
        return {field: 0 for field in required_fields}


def agent_1_generate_stimulus_hf(
        experiment_design,
        previous_stimuli,
        prompt_template=AGENT_1_PROMPT_TEMPLATE,
        properties=None,
        params=None,
        stop_event=None):
    """
    Agent 1: Use Hugging Face API to generate new stimulus, return dictionary format.
    """
    if stop_event and stop_event.is_set():
        print("Generation stopped by user in agent_1_generate_stimulus_hf.")
        return {"stimulus": "STOPPED"}
        
    if properties is None:
        properties = AGENT_1_PROPERTIES
    if params is None:
        params = {"temperature": 0.7, "max_tokens": 200, "model": "meta-llama/Llama-3.3-70B-Instruct"}
    
    # Use fixed generation_requirements
    generation_requirements = "Please generate a new stimulus in the same format as the existing stimuli, and ensure that the new stimulus is different from those in the existing stimuli."

    prompt = prompt_template.format(
        experiment_design=experiment_design,
        previous_stimuli=previous_stimuli,
        generation_requirements=generation_requirements
    )
    
    # Create HF InferenceClient, set headers
    client = InferenceClient(
        params["model"], 
        token=HF_API_KEY,
        headers={"x-use-cache": "false"}  # Disable cache, ensure new results every time
    )
    
    # Prepare JSON Schema
    response_format = {
        "type": "json",
        "value": {
            "properties": properties,
            "required": list(properties.keys()),
        }
    }
    
    # Build messages
    messages = [{"role": "user", "content": prompt}]
    
    # Call API
    response = client.chat_completion(
        messages=messages,
        response_format=response_format,
        max_tokens=params["max_tokens"],
        temperature=params["temperature"]
    )
    
    # Check stop event again
    if stop_event and stop_event.is_set():
        print("Generation stopped by user after API call in agent_1_generate_stimulus_hf.")
        return {"stimulus": "STOPPED"}
    
    try:
        # Parse response
        content = response.choices[0].message.content
        new_stimulus = json.loads(content)
    except (json.JSONDecodeError, AttributeError, IndexError) as e:
        print(f"Failed to parse HF JSON response: {e}")
        # If parsing fails, return a default object
        new_stimulus = {
            "stimulus": "ERROR/ERROR",
        }

    return new_stimulus


def agent_2_validate_stimulus_hf(
        new_stimulus,
        experiment_design,
        previous_stimuli,
        prompt_template=AGENT_2_PROMPT_TEMPLATE,
        properties=None,
        params=None,
        stop_event=None):
    """
    Agent 2: Use Hugging Face API to validate experimental stimulus
    """
    if stop_event and stop_event.is_set():
        print("Generation stopped by user in agent_2_validate_stimulus_hf.")
        return {"Overall": "failed", "reason": "Stopped by user"}
        
    if properties is None:
        properties = AGENT_2_PROPERTIES
    if params is None:
        params = {"temperature": 0, "max_tokens": 100, "model": "meta-llama/Llama-3.3-70B-Instruct"}

    # Automatically set all properties' keys as required
    required_fields = list(properties.keys())

    prompt = prompt_template.format(
        experiment_design=experiment_design,
        new_stimulus=new_stimulus
    )
    
    # Create HF InferenceClient, set headers
    client = InferenceClient(
        params["model"], 
        token=HF_API_KEY,
        headers={"x-use-cache": "false"}  # Disable cache, ensure new results every time
    )
    
    # Prepare JSON Schema
    response_format = {
        "type": "json",
        "value": {
            "properties": properties,
            "required": required_fields,
        }
    }
    
    # Build messages
    messages = [{"role": "user", "content": prompt}]
    
    # Call API
    response = client.chat_completion(
        messages=messages,
        response_format=response_format,
        max_tokens=params["max_tokens"],
        temperature=params["temperature"]
    )
    
    # Check stop event again
    if stop_event and stop_event.is_set():
        print("Generation stopped by user after API call in agent_2_validate_stimulus_hf.")
        return {"Overall": "failed", "reason": "Stopped by user"}
    
    try:
        # Parse response
        content = response.choices[0].message.content
        result = json.loads(content)
    except (json.JSONDecodeError, AttributeError, IndexError) as e:
        print(f"Failed to parse HF JSON response: {e}")
        result = {"status": "failed", "reason": "Failed to validate stimulus"}

    return result


def agent_3_score_stimulus_hf(
        valid_stimulus,
        experiment_design,
        prompt_template=AGENT_3_PROMPT_TEMPLATE,
        properties=None,
        params=None,
        stop_event=None):
    """
    Agent 3: Use Hugging Face API to score experimental stimulus
    """
    if stop_event and stop_event.is_set():
        print("Generation stopped by user in 'Scorer'.")
        return {field: 0 for field in properties.keys()} if properties else {"total_score": 0}
        
    if properties is None:
        properties = AGENT_3_PROPERTIES
    if params is None:
        params = {"temperature": 0.7, "max_tokens": 200, "model": "meta-llama/Llama-3.3-70B-Instruct"}

    required_fields = list(properties.keys())

    prompt = prompt_template.format(
        experiment_design=experiment_design,
        valid_stimulus=valid_stimulus
    )
    
    # Create HF InferenceClient, set headers
    client = InferenceClient(
        params["model"], 
        token=HF_API_KEY,
        headers={"x-use-cache": "false"}  # Disable cache, ensure new results every time
    )
    
    # Prepare JSON Schema
    response_format = {
        "type": "json",
        "value": {
            "properties": properties,
            "required": required_fields,
        }
    }
    
    # Build messages
    messages = [{"role": "user", "content": prompt}]
    
    # Call API
    response = client.chat_completion(
        messages=messages,
        response_format=response_format,
        max_tokens=params["max_tokens"],
        temperature=params["temperature"]
    )
    
    # Check stop event again
    if stop_event and stop_event.is_set():
        print("Generation stopped by user in 'Scorer'.")
        return {field: 0 for field in properties.keys()} if properties else {"total_score": 0}
    
    try:
        # Parse response
        content = response.choices[0].message.content
        return json.loads(content)
    except (json.JSONDecodeError, AttributeError, IndexError) as e:
        print(f"Failed to parse HF JSON response: {e}")
        # If parsing fails, return a default/empty scoring object
        return {field: 0 for field in required_fields}


# ======================
# 3. Main Flow Function
# ======================
def generate_stimuli(settings):
    openai.api_key = settings.get('api_key', "")
    stop_event = settings['stop_event']
    current_iteration = settings['current_iteration']
    total_iterations = settings['total_iterations']
    experiment_design = settings['experiment_design']
    previous_stimuli = settings['previous_stimuli'] if settings['previous_stimuli'] else []
    model_choice = settings.get('model_choice', 'GPT-4o')  # Default to use GPT-4o
    # Get session_update_callback function and websocket_callback function
    session_update_callback = settings.get('session_update_callback')
    websocket_callback = settings.get('websocket_callback')  # Get websocket callback

    # Ensure progress value is correctly initialized
    with current_iteration.get_lock(), total_iterations.get_lock():
        current_iteration.value = 0
        total_iterations.value = settings['iteration']
        # Immediately send correct initial progress
        if session_update_callback:
            session_update_callback()

    # Check stop event at each critical point
    def check_stop(message="Generation stopped by user."):
        if stop_event.is_set():
            print(message)
            if websocket_callback:
                websocket_callback("all", message)
            return True
        return False
    
    # Immediately check if stopped
    if check_stop("Generation stopped before starting."):
        return None, None

    record_list = []
    agent_1_properties = settings.get('agent_1_properties', {})
    print("Agent 1 Properties:", agent_1_properties)
    # Use websocket to send message to frontend
    if websocket_callback:
        websocket_callback("setup", f"Agent 1 Properties: {agent_1_properties}")

    # Check again if stopped
    if check_stop():
        return None, None

    agent_2_properties = settings.get('agent_2_properties', {})
    print("Agent 2 Properties:", agent_2_properties)
    if websocket_callback:
        websocket_callback("setup", f"Agent 2 Properties: {agent_2_properties}")

    # Check again if stopped
    if check_stop():
        return None, None

    agent_3_properties = settings.get('agent_3_properties', {})
    print("Agent 3 Properties:", agent_3_properties)
    if websocket_callback:
        websocket_callback("setup", f"Agent 3 Properties: {agent_3_properties}")

    # Check again if stopped
    if check_stop():
        return None, None

    # Select appropriate Agent function
    if model_choice == 'GPT-4o':
        agent_1_func = lambda **kwargs: agent_1_generate_stimulus(stop_event=stop_event, **kwargs)
        agent_2_func = lambda **kwargs: agent_2_validate_stimulus(stop_event=stop_event, **kwargs)
        agent_3_func = lambda **kwargs: agent_3_score_stimulus(stop_event=stop_event, **kwargs)
        print("Using OpenAI GPT-4o for generation")
        if websocket_callback:
            websocket_callback("setup", "Using OpenAI GPT-4o for generation")
    else:  # Use Hugging Face model
        agent_1_func = lambda **kwargs: agent_1_generate_stimulus_hf(stop_event=stop_event, **kwargs)
        agent_2_func = lambda **kwargs: agent_2_validate_stimulus_hf(stop_event=stop_event, **kwargs)
        agent_3_func = lambda **kwargs: agent_3_score_stimulus_hf(stop_event=stop_event, **kwargs)
        print(f"Using Hugging Face model: {model_choice}")
        if websocket_callback:
            websocket_callback("setup", f"Using Hugging Face model: {model_choice}")

    # Check again if stopped before last start
    if check_stop():
        return None, None

    # Create a function specifically for updating progress
    def update_progress(completed_iterations):
        if check_stop():
            return
            
        with current_iteration.get_lock(), total_iterations.get_lock():
            # Ensure completed iterations do not exceed total iterations
            current_value = min(completed_iterations, total_iterations.value)
            # Only update if new value is greater than current value
            if current_value > current_iteration.value:
                current_iteration.value = current_value
                # If there is a callback function, call it immediately
                if session_update_callback:
                    session_update_callback()

    # Get actual total iterations
    total_iter_value = total_iterations.value
    for iteration_num in range(total_iter_value):
        # Check if there is a stop signal
        if check_stop():
            return None, None  # Return None instead of filename when user stops

        round_message = f"=== No. {iteration_num + 1} Round ==="
        print(round_message)
        if websocket_callback:
            websocket_callback("all", round_message)  # Send to all areas

        # Step 1: Generate stimulus
        while True:
            # Check if there is a stop signal
            if check_stop():
                return None, None  # Return None instead of filename when user stops

            try:
                stimuli = agent_1_func(
                    experiment_design=experiment_design,
                    previous_stimuli=previous_stimuli,
                    prompt_template=AGENT_1_PROMPT_TEMPLATE,
                    properties=settings['agent_1_properties']
                )
                
                # Check if agent_1 returned a stop marker
                if isinstance(stimuli, dict) and stimuli.get('stimulus') == 'STOPPED':
                    if check_stop("Generation stopped after 'Generator'."):
                        return None, None
                
                print("Agent 1 Output:", stimuli)
                if websocket_callback:
                    websocket_callback("generator", f"Generator's Output: {json.dumps(stimuli, indent=2)}")

                # Check again if stopped
                if check_stop("Generation stopped after 'Generator'."):
                    return None, None

                # Step 1.5: Check if stimulus already exists
                if check_stimulus_repetition(stimuli, previous_stimuli):
                    print("Detected repeated stimulus, regenerating...")
                    if websocket_callback:
                        websocket_callback("generator", "Detected repeated stimulus, regenerating...")
                    continue  # Regenerate

                # Check again if stopped
                if check_stop():
                    return None, None

                # Step 2: Validate stimulus
                validation_result = agent_2_func(
                    new_stimulus=stimuli,
                    experiment_design=experiment_design,
                    previous_stimuli=previous_stimuli,
                    prompt_template=AGENT_2_PROMPT_TEMPLATE,
                    properties=settings['agent_2_properties']
                )
                
                # Check if agent_2 returned a stop marker
                if isinstance(validation_result, dict) and validation_result.get('reason') == 'Stopped by user':
                    if check_stop("Generation stopped after 'Validator'."):
                        return None, None
                
                print("Agent 2 Output:", validation_result)
                if websocket_callback:
                    websocket_callback("validator", f"Validator's Output: {json.dumps(validation_result, indent=2)}")

                # Check again if stopped
                if check_stop("Generation stopped after 'Validator'."):
                    return None, None

                # Check if validation passed
                if validation_result.get('Overall') == 'failed':
                    print("Failed to validate, regenerating...")
                    if websocket_callback:
                        websocket_callback("validator", "Failed to validate, regenerating...")
                    continue
                else:
                    # Use a dedicated progress update function to update progress
                    update_progress(iteration_num + 1)
                    break
            except Exception as e:
                error_msg = f"Error in generation/validation step: {str(e)}"
                print(error_msg)
                if websocket_callback:
                    websocket_callback("all", error_msg)
                # If an error occurs and generation is interrupted, return the current generated records
                if len(record_list) > 0:
                    df = pd.DataFrame(record_list)
                    session_id = settings.get('session_id', 'default')
                    timestamp = int(time.time())
                    # Add extra unique identifier to avoid filename conflicts within the same second
                    unique_id = ''.join(random.choice('0123456789abcdef') for _ in range(6))
                    suggested_filename = f"experiment_stimuli_results_{session_id}_{timestamp}_{unique_id}_error.csv"
                    
                    # Add metadata columns to identify generation time and iteration count
                    df['generation_timestamp'] = timestamp
                    df['batch_id'] = unique_id
                    df['total_iterations'] = total_iter_value
                    df['error_occurred'] = True
                    df['error_message'] = str(e)
                    
                    return df, suggested_filename
                else:
                    # If no records are generated, return an error
                    raise e

        # Check again if stopped
        if check_stop("Generation stopped after 'Validator'."):
            return None, None

        try:
            # Check again if stopped
            if check_stop("Generation stopped before Scorer."):
                return None, None
                
            # Step 3: Score
            scores = agent_3_func(
                valid_stimulus=stimuli,
                experiment_design=experiment_design,
                prompt_template=AGENT_3_PROMPT_TEMPLATE,
                properties=settings['agent_3_properties']
            )
            
            # Check if agent_3 returned a stop marker
            if isinstance(scores, dict) and all(v == 0 for v in scores.values()):
                if stop_event.is_set():  # Additional check to confirm that the stop caused all 0 scores
                    if check_stop("Generation stopped after 'Scorer'."):
                        return None, None
            
            print("Agent 3 Output:", scores)
            if websocket_callback:
                websocket_callback("scorer", f"Scorer's Output: {json.dumps(scores, indent=2)}")

            # Check again if stopped
            if check_stop("Generation stopped after 'Scorer'."):
                return None, None

            # Save results
            record = {
                "stimulus_id": iteration_num + 1,  # Use loop count as ID
                "stimulus_content": stimuli
            }
            record.update(scores or {})
            record_list.append(record)

            # Update previous_stimuli
            previous_stimuli.append(stimuli)
            
            # If some records have been generated, create intermediate results
            if (iteration_num + 1) % 5 == 0 or iteration_num + 1 == total_iter_value:
                # Create temporary DataFrame, for restoring during interruption
                temp_df = pd.DataFrame(record_list)
                session_id = settings.get('session_id', 'default')
                # Add timestamp to filename, ensure different filenames each time
                timestamp = int(time.time())
                # Add extra unique identifier to avoid filename conflicts within the same second
                unique_id = ''.join(random.choice('0123456789abcdef') for _ in range(6))
                suggested_filename = f"experiment_stimuli_results_{session_id}_{timestamp}_{unique_id}.csv"
                
                # Add metadata columns to identify generation time and iteration count
                temp_df['generation_timestamp'] = timestamp
                temp_df['batch_id'] = unique_id
                temp_df['total_iterations'] = total_iter_value
                
                # Check if stopped
                if check_stop():
                    return temp_df, suggested_filename
                
                # Here we don't save the file, but return the current df and filename, so that the external function can save session state
                if iteration_num + 1 == total_iter_value:
                    # Check again if progress has been updated to 100%
                    update_progress(total_iter_value)
                    return temp_df, suggested_filename
        except Exception as e:
            error_msg = f"Error in scoring step: {str(e)}"
            print(error_msg)
            if websocket_callback:
                websocket_callback("all", error_msg)
            # If an error occurs and some records have been generated, return them
            if len(record_list) > 0:
                df = pd.DataFrame(record_list)
                session_id = settings.get('session_id', 'default')
                timestamp = int(time.time())
                # Add extra unique identifier to avoid filename conflicts within the same second
                unique_id = ''.join(random.choice('0123456789abcdef') for _ in range(6))
                suggested_filename = f"experiment_stimuli_results_{session_id}_{timestamp}_{unique_id}_error.csv"
                
                # Add metadata columns to identify generation time and iteration count
                df['generation_timestamp'] = timestamp
                df['batch_id'] = unique_id
                df['total_iterations'] = total_iter_value
                df['error_occurred'] = True
                df['error_message'] = str(e)
                
                return df, suggested_filename
            else:
                # If no records are generated, return an error
                raise e

    # Check again if stopped at final step
    if check_stop("Generation stopped at final step."):
        # If some records have been generated, return them
        if len(record_list) > 0:
            df = pd.DataFrame(record_list)
            session_id = settings.get('session_id', 'default')
            timestamp = int(time.time())
            # Add extra unique identifier to avoid filename conflicts within the same second
            unique_id = ''.join(random.choice('0123456789abcdef') for _ in range(6))
            suggested_filename = f"experiment_stimuli_results_{session_id}_{timestamp}_{unique_id}.csv"
            
            # Add metadata columns to identify generation time and iteration count
            df['generation_timestamp'] = timestamp
            df['batch_id'] = unique_id
            df['total_iterations'] = total_iter_value
            # Normal completion should not be marked as error
            df['error_occurred'] = False
            df['error_message'] = ""
            
            completion_msg = f"Data generation completed for session {session_id}"
            print(completion_msg)
            if websocket_callback:
                websocket_callback("all", completion_msg)
            # Return DataFrame and suggested filename, instead of saving file
            return df, suggested_filename
        return None, None

    # Only generate DataFrame and return results after all iterations
    if len(record_list) > 0:
        # Ensure final progress is 100%
        update_progress(total_iter_value)
        
        df = pd.DataFrame(record_list)
        # Use session ID to create unique filename (only return as suggested filename)
        session_id = settings.get('session_id', 'default')
        timestamp = int(time.time())
        # Add extra unique identifier to avoid filename conflicts within the same second
        unique_id = ''.join(random.choice('0123456789abcdef') for _ in range(6))
        # Remove _error suffix, this is normal completion
        suggested_filename = f"experiment_stimuli_results_{session_id}_{timestamp}_{unique_id}.csv"
        
        # Add metadata columns to identify generation time and iteration count
        df['generation_timestamp'] = timestamp
        df['batch_id'] = unique_id
        df['total_iterations'] = total_iter_value
        # Normal completion should not be marked as error
        df['error_occurred'] = False
        df['error_message'] = ""
        
        completion_msg = f"Data generation completed for session {session_id}"
        print(completion_msg)
        if websocket_callback:
            websocket_callback("all", completion_msg)
        # Return DataFrame and suggested filename, instead of saving file
        return df, suggested_filename
    else:
        print("No records generated.")
        if websocket_callback:
            websocket_callback("all", "No records generated.")
        return None, None
