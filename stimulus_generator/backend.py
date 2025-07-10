import openai
import pandas as pd
import json

import time
import random
import requests
from flask import request, jsonify
from abc import ABC, abstractmethod
import threading
import multiprocessing
from multiprocessing import Process, Queue
import queue
import traceback

# Set OpenAI API key
# openai.api_key = ""

# Set Chutes AI API key (commented out)

# 使用multiprocessing实现真正的超时机制


def _timeout_target(queue, func, args, kwargs):
    """multiprocessing target function, must be defined at module level to be pickled"""
    try:
        result = func(*args, **kwargs)
        queue.put(('success', result))
    except Exception as e:
        tb = traceback.format_exc()
        print(f"Exception in subprocess:\n{tb}")
        queue.put(('error', f"{type(e).__name__}: {str(e)}\n{tb}"))


def call_with_timeout(func, args, kwargs, timeout_seconds=60):
    """use multiprocessing to implement API call timeout, can force terminate"""
    queue = Queue()
    process = Process(target=_timeout_target, args=(queue, func, args, kwargs))
    process.start()
    process.join(timeout_seconds)

    if process.is_alive():
        # force terminate process
        process.terminate()
        process.join()
        print(
            f"API call timed out after {timeout_seconds} seconds and process was terminated")
        return {"error": f"API call timed out after {timeout_seconds} seconds"}

    try:
        result_type, result = queue.get_nowait()
        if result_type == 'success':
            return result
        else:
            return {"error": result}
    except queue.Empty:
        return {"error": "Process completed but no result returned"}


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

Please return in JSON format.
"""

# ---- Agent 3 Prompt ----
AGENT_3_PROMPT_TEMPLATE = """\
Please rate the following STIMULUS based on the Experimental stimuli design provided for a psychological experiment:

STIMULUS: {valid_stimulus}
Experimental stimuli design: {experiment_design}

Please return in JSON format including the score for each dimension.
"""

# ---- Agent 1 Stimulus Schema ----
AGENT_1_PROPERTIES = {}

# ---- Agent 2 Validation Result Schema ----
AGENT_2_PROPERTIES = {}

# ---- Agent 3 Scoring Result Schema ----
AGENT_3_PROPERTIES = {}


# ======================
# 2. Abstract Model Client Interface
# ======================
class ModelClient(ABC):
    """Abstract base class for model clients"""

    @abstractmethod
    def generate_completion(self, prompt, properties, params=None):
        """Generate a completion with JSON schema response format"""
        pass

    @abstractmethod
    def get_default_params(self):
        """Get default parameters for this model"""
        pass


# ======================
# 3. Concrete Model Client Implementations
# ======================
class OpenAIClient(ModelClient):
    """OpenAI GPT model client"""

    def __init__(self, api_key=None):
        self.api_key = api_key
        if api_key:
            openai.api_key = api_key
            print(f"OpenAI API key set successfully, length: {len(api_key)}")
        else:
            print("Warning: No OpenAI API key provided!")

    def _api_call(self, prompt, properties, params, api_key):
        """API call function, will be called by multiprocessing"""
        # set API key in subprocess
        openai.api_key = api_key
        print(
            f"OpenAI API key in subprocess: {api_key[:10]}..." if api_key else "None")

        return openai.ChatCompletion.create(
            model=params["model"],
            messages=[{"role": "user", "content": prompt}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "response_schema",
                    "schema": {
                        "type": "object",
                        "properties": properties,
                        "required": list(properties.keys()),
                        "additionalProperties": False
                    }
                }
            }
        )

    def generate_completion(self, prompt, properties, params=None):
        """Generate completion using OpenAI API"""
        if params is None:
            params = self.get_default_params()

        # retry mechanism
        for attempt in range(3):
            try:
                response = call_with_timeout(
                    self._api_call, (prompt, properties, params, self.api_key), {}, 60)

                if isinstance(response, dict) and "error" in response:
                    print(f"OpenAI API timeout attempt {attempt + 1}/3")
                    if attempt == 2:  # last attempt
                        return {"error": "API timeout after 3 attempts"}
                    time.sleep(2 ** attempt)  # exponential backoff
                    continue

                return json.loads(response['choices'][0]['message']['content'])
            except json.JSONDecodeError as e:
                print(f"Failed to parse OpenAI JSON response: {e}")
                return {"error": "Failed to parse response"}
            except Exception as e:
                print(f"OpenAI API error attempt {attempt + 1}/3: {e}")
                if attempt == 2:
                    return {"error": f"API error after 3 attempts: {str(e)}"}
                time.sleep(2 ** attempt)

    def get_default_params(self):
        return {"model": "gpt-4o"}


# class HuggingFaceClient(ModelClient):
#     """Hugging Face model client"""

#     def __init__(self, api_key):
#         self.api_key = api_key

#     def _api_call(self, messages, response_format, params):
#         """API调用函数，会被multiprocessing调用"""
#         client = InferenceClient(
#             params["model"],
#             token=self.api_key,
#             headers={"x-use-cache": "false"}
#         )

#         return client.chat_completion(
#             messages=messages,
#             response_format=response_format,
#             max_tokens=params.get("max_tokens", 1000),
#             temperature=params.get("temperature", 0.7)
#         )

#     def generate_completion(self, prompt, properties, params=None):
#         """Generate completion using Hugging Face API"""
#         if params is None:
#             params = self.get_default_params()

#         response_format = {
#             "type": "json_schema",
#             "json_schema": {
#                 "name": "response_schema",
#                 "schema": {
#                     "type": "object",
#                     "properties": properties,
#                     "required": list(properties.keys()),
#                     "additionalProperties": False
#                 }
#             }
#         }

#         messages = [{"role": "user", "content": prompt}]

#         # 重试机制
#         for attempt in range(3):
#             try:
#                 response = call_with_timeout(
#                     self._api_call, (messages, response_format, params), {}, 60)

#                 if isinstance(response, dict) and "error" in response:
#                     print(f"HuggingFace API timeout attempt {attempt + 1}/3")
#                     if attempt == 2:
#                         return {"error": "API timeout after 3 attempts"}
#                     time.sleep(2 ** attempt)
#                     continue

#                 content = response.choices[0].message.content
#                 return json.loads(content)
#             except (json.JSONDecodeError, AttributeError, IndexError) as e:
#                 print(f"Failed to parse HuggingFace JSON response: {e}")
#                 return {"error": "Failed to parse response"}
#             except Exception as e:
#                 print(f"HuggingFace API error attempt {attempt + 1}/3: {e}")
#                 if attempt == 2:
#                     return {"error": f"API error after 3 attempts: {str(e)}"}
#                 time.sleep(2 ** attempt)

#     def get_default_params(self):
#         return {
#             "model": "meta-llama/Llama-3.3-70B-Instruct",
#         }


class CustomModelClient(ModelClient):
    """Custom model client for user-defined APIs"""

    def __init__(self, api_url, api_key, model_name):
        self.api_url = api_url
        self.api_key = api_key
        self.model_name = model_name

    def _api_call(self, request_data, headers):
        """API call function, will be called by multiprocessing"""
        response = requests.post(
            self.api_url,
            headers=headers,
            json=request_data,
            timeout=60  # timeout for requests
        )
        response.raise_for_status()
        return response.json()

    def generate_completion(self, prompt, properties, params=None):

        is_deepseek = self.api_url.strip().startswith("https://api.deepseek.com")

        if is_deepseek:
            import time
            rand_stamp = int(time.time())
            # 生成字段列表
            field_list = ', '.join([f'"{k}"' for k in properties.keys()])
            # 判断agent的类型
            # 如果以"Please verify the following NEW STIMULUS " 开头，则在prompt最后返回，每个字段只能返回布尔值
            if prompt.strip().startswith("Please verify the following NEW STIMULUS"):
                prompt = prompt.rstrip() + \
                    f"\n请以严格的JSON格式返回，字段必须包括：{field_list}，每个字段的要求如下：{properties}，每个字段只能返回布尔值（True/False）"
            elif prompt.strip().startswith("Please rate the following STIMULUS"):
                prompt = prompt.rstrip() + \
                    f"\n请以严格的JSON格式返回，字段必须包括：{field_list}，每个字段的要求如下：{properties}，每个字段只能返回数字"
            else:
                prompt = prompt.rstrip() + \
                    f"\n请以严格的JSON格式返回，字段必须包括：{field_list}，每个字段的要求如下：{properties}"

            request_data = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": f"RAND:{rand_stamp}"},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "response_format": {"type": "json_object"}
            }
        else:
            # build base request
            request_data = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "response_schema",
                        "schema": {
                            "type": "object",
                            "properties": properties,
                            "required": list(properties.keys()),
                            "additionalProperties": False
                        }
                    }
                }
            }

        if params is not None:
            request_data.update(params)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # retry mechanism
        for attempt in range(3):
            try:
                print("Sending request to Custom API with:",
                      json.dumps(request_data, indent=2))

                result = call_with_timeout(
                    self._api_call, (request_data, headers), {}, 60)

                if isinstance(result, dict) and "error" in result:
                    print(f"Custom API timeout attempt {attempt + 1}/3")
                    if attempt == 2:
                        return {"error": "API timeout after 3 attempts"}
                    time.sleep(2 ** attempt)
                    continue

                print("Response from Custom API:",
                      json.dumps(result, indent=2))
                content = result["choices"][0]["message"]["content"]
                return json.loads(content)

            except (json.JSONDecodeError, KeyError) as e:
                print(f"Custom API parsing error attempt {attempt + 1}/3: {e}")
                if attempt == 2:
                    return {"error": f"API parsing error after 3 attempts: {str(e)}"}
                time.sleep(2 ** attempt)
            except Exception as e:
                print(f"Custom API error attempt {attempt + 1}/3: {e}")
                if attempt == 2:
                    return {"error": f"API error after 3 attempts: {str(e)}"}
                time.sleep(2 ** attempt)

    def get_default_params(self):
        return {
        }


# ======================
# 4. Model Client Factory
# ======================
def create_model_client(model_choice, settings=None):
    """Factory function to create appropriate model client"""
    if model_choice == 'GPT-4o':
        api_key = settings.get('api_key') if settings else None
        print(f"OpenAI API key length: {len(api_key) if api_key else 0}")
        return OpenAIClient(api_key)
    elif model_choice == 'custom':
        if not settings:
            raise ValueError("Settings required for custom model")
        return CustomModelClient(
            api_url=settings.get('apiUrl'),
            api_key=settings.get('api_key'),
            model_name=settings.get('modelName')
        )
    # elif model_choice == 'HuggingFace':
    #     api_key = settings.get('api_key')
    #     return HuggingFaceClient(api_key)
    else:
        raise ValueError(f"Unsupported model choice: {model_choice}")


# ======================
# 5. Unified Agent Functions
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
        model_client,
        experiment_design,
        previous_stimuli,
        properties,
        prompt_template=AGENT_1_PROMPT_TEMPLATE,
        params=None,
        stop_event=None):
    """
    Agent 1: Generate new stimulus using the provided model client
    """
    if stop_event and stop_event.is_set():
        print("Generation stopped by user in agent_1_generate_stimulus.")
        return {"stimulus": "STOPPED"}

    # Use fixed generation_requirements
    generation_requirements = "Please generate a new stimulus in the same format as the existing stimuli, and ensure that the new stimulus is different from those in the existing stimuli."

    prompt = prompt_template.format(
        experiment_design=experiment_design,
        previous_stimuli=previous_stimuli,
        generation_requirements=generation_requirements
    )

    try:
        result = model_client.generate_completion(prompt, properties, params)

        # Check stop event again
        if stop_event and stop_event.is_set():
            print(
                "Generation stopped by user after API call in agent_1_generate_stimulus.")
            return {"stimulus": "STOPPED"}

        if "error" in result:
            return {"stimulus": "ERROR/ERROR"}

        return result
    except Exception as e:
        print(f"Error in agent_1_generate_stimulus: {e}")
        return {"stimulus": "ERROR/ERROR"}


def agent_2_validate_stimulus(
        model_client,
        new_stimulus,
        experiment_design,
        properties,
        prompt_template=AGENT_2_PROMPT_TEMPLATE,
        stop_event=None):
    """
    Agent 2: Validate experimental stimulus using the provided model client
    """
    if stop_event and stop_event.is_set():
        print("Generation stopped by user in agent_2_validate_stimulus.")
        return {"error": "Stopped by user"}

    prompt = prompt_template.format(
        experiment_design=experiment_design,
        new_stimulus=new_stimulus
    )

    try:
        # use temperature=0 parameter, get model-specific default params and override temperature
        fixed_params = model_client.get_default_params()
        fixed_params["temperature"] = 0
        result = model_client.generate_completion(
            prompt, properties, fixed_params)

        print("Agent 2 Output:", result)

        # Check stop event again
        if stop_event and stop_event.is_set():
            print(
                "Generation stopped by user after API call in agent_2_validate_stimulus.")
            return {"error": "Stopped by user"}

        if "error" in result:
            print(f"Agent 2 API error: {result}")
            return {"error": f"Failed to validate stimulus: {result.get('error', 'Unknown error')}"}

        return result
    except Exception as e:
        print(f"Error in agent_2_validate_stimulus: {e}")
        return {"error": "Failed to validate stimulus"}


def agent_3_score_stimulus(
        model_client,
        valid_stimulus,
        experiment_design,
        properties,
        prompt_template=AGENT_3_PROMPT_TEMPLATE,
        stop_event=None):
    """
    Agent 3: Score experimental stimulus using the provided model client
    """
    if stop_event and stop_event.is_set():
        print("Generation stopped by user after API call in agent_3_score_stimulus.")
        return {field: 0 for field in properties.keys()} if properties else {}

    prompt = prompt_template.format(
        experiment_design=experiment_design,
        valid_stimulus=valid_stimulus
    )

    try:
        # use temperature=0 parameter, get model-specific default params and override temperature
        fixed_params = model_client.get_default_params()
        fixed_params["temperature"] = 0
        result = model_client.generate_completion(
            prompt, properties, fixed_params)

        if stop_event and stop_event.is_set():
            print("Generation stopped by user after API call in agent_3_score_stimulus.")
            return {field: 0 for field in properties.keys()} if properties else {}

        if "error" in result:
            print(f"Agent 3 API error: {result}")
            return {field: 0 for field in properties.keys()}

        return result
    except Exception as e:
        print(f"Error in agent_3_score_stimulus: {e}")
        return {field: 0 for field in properties.keys()}


# ======================
# 6. Main Flow Function
# ======================
def generate_stimuli(settings):

    stop_event = settings['stop_event']
    current_iteration = settings['current_iteration']
    total_iterations = settings['total_iterations']
    experiment_design = settings['experiment_design']
    previous_stimuli = settings['previous_stimuli'] if settings['previous_stimuli'] else [
    ]
    model_choice = settings.get('model_choice', 'GPT-4o')

    ablation = settings.get('ablation', {
        "use_agent_2": True,
        "use_agent_3": True
    })

    repetition_count = 0
    validation_fails = 0

    # Get custom parameters for custom model
    custom_params = settings.get('params', None)

    # Get session_update_callback function and websocket_callback function
    session_update_callback = settings.get('session_update_callback')
    websocket_callback = settings.get('websocket_callback')

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
    if websocket_callback:
        websocket_callback(
            "setup", f"Agent 1 Properties: {agent_1_properties}")

    if check_stop():
        return None, None

    agent_2_properties = settings.get('agent_2_properties', {})
    print("Agent 2 Properties:", agent_2_properties)
    if websocket_callback:
        websocket_callback(
            "setup", f"Agent 2 Properties: {agent_2_properties}")

    if check_stop():
        return None, None

    agent_3_properties = settings.get('agent_3_properties', {})
    print("Agent 3 Properties:", agent_3_properties)
    if websocket_callback:
        websocket_callback(
            "setup", f"Agent 3 Properties: {agent_3_properties}")

    if check_stop():
        return None, None

    # Create model client using factory
    try:
        model_client = create_model_client(model_choice, settings)
        print(f"Using model: {model_choice}")
        if websocket_callback:
            websocket_callback("setup", f"Using model: {model_choice}")
    except Exception as e:
        error_msg = f"Failed to create model client: {str(e)}"
        print(error_msg)
        if websocket_callback:
            websocket_callback("setup", error_msg)
        return None, None

    if check_stop():
        return None, None

    # Create a function specifically for updating progress
    def update_progress(completed_iterations):
        if check_stop():
            return

        with current_iteration.get_lock(), total_iterations.get_lock():
            current_value = min(completed_iterations, total_iterations.value)
            if current_value > current_iteration.value:
                current_iteration.value = current_value
                if session_update_callback:
                    session_update_callback()

    # Get actual total iterations
    total_iter_value = total_iterations.value
    for iteration_num in range(total_iter_value):
        if check_stop():
            return None, None

        round_message = f"=== No. {iteration_num + 1} Round ==="
        print(round_message)
        if websocket_callback:
            websocket_callback("all", round_message)

        # Step 1: Generate stimulus
        while True:
            if check_stop():
                return None, None

            try:
                stimuli = agent_1_generate_stimulus(
                    model_client=model_client,
                    experiment_design=experiment_design,
                    previous_stimuli=previous_stimuli,
                    properties=agent_1_properties,
                    prompt_template=AGENT_1_PROMPT_TEMPLATE,
                    params=custom_params,
                    stop_event=stop_event
                )

                if isinstance(stimuli, dict) and stimuli.get('stimulus') == 'STOPPED':
                    if check_stop("Generation stopped after 'Generator'."):
                        return None, None

                print("Agent 1 Output:", stimuli)
                if websocket_callback:
                    websocket_callback(
                        "generator", f"Generator's Output: {json.dumps(stimuli, indent=2)}")

                if check_stop("Generation stopped after 'Generator'."):
                    return None, None

                # Step 1.5: Check if stimulus already exists

                if check_stimulus_repetition(stimuli, previous_stimuli):
                    repetition_count += 1
                    if ablation["use_agent_2"]:
                        print("Detected repeated stimulus, regenerating...")

                        if websocket_callback:
                            websocket_callback(
                                "generator", "Detected repeated stimulus, regenerating...")
                        continue
                    else:
                        print(
                            "Ablation: Skipping Agent 2 (Repetition Check)")
                        if websocket_callback:
                            websocket_callback(
                                "generator", "Ablation: Skipping Agent 2 (Repetition Check)")

                if check_stop():
                    return None, None

                # Step 2: Validate stimulus
                validation_result = agent_2_validate_stimulus(
                    model_client=model_client,
                    new_stimulus=stimuli,
                    experiment_design=experiment_design,
                    properties=agent_2_properties,
                    prompt_template=AGENT_2_PROMPT_TEMPLATE,
                    stop_event=stop_event
                )

                if isinstance(validation_result, dict) and validation_result.get('error') == 'Stopped by user':
                    if check_stop("Generation stopped after 'Validator'."):
                        return None, None

                print("Agent 2 Output:", validation_result)
                if websocket_callback:
                    websocket_callback(
                        "validator", f"Validator's Output: {json.dumps(validation_result, indent=2)}")

                if check_stop("Generation stopped after 'Validator'."):
                    return None, None

                # Check if there was an error first
                if 'error' in validation_result:
                    print(f"Validation error: {validation_result['error']}")
                    if websocket_callback:
                        websocket_callback(
                            "validator", f"Validation error: {validation_result['error']}")
                    continue  # Skip to next iteration
                
                # Check validation fields
                failed_fields = [
                    key for key, value in validation_result.items() if not value]

                if failed_fields:
                    # Some fields failed validation
                    validation_fails += 1
                    print(
                        f"Failed validation for fields: {failed_fields}, regenerating...")
                    if websocket_callback:
                        websocket_callback(
                            "validator", f"Failed validation for fields: {failed_fields}, regenerating...")

                    if ablation["use_agent_2"]:
                        continue  # Regenerate
                    else:
                        print("Ablation: Skipping Agent 2 (Validation)")
                        if websocket_callback:
                            websocket_callback(
                                "validator", "Ablation: Skipping Agent 2 (Validation)")
                        update_progress(iteration_num + 1)
                        break
                else:
                    # All validations passed
                    print("All validations passed, proceeding to next step...")
                    if websocket_callback:
                        websocket_callback(
                            "validator", "All validations passed, proceeding to next step...")
                    update_progress(iteration_num + 1)
                    break

            except Exception as e:
                error_msg = f"Error in generation/validation step: {str(e)}"
                print(error_msg)
                if websocket_callback:
                    websocket_callback("all", error_msg)
                if len(record_list) > 0:
                    df = pd.DataFrame(record_list)
                    session_id = settings.get('session_id', 'default')
                    timestamp = int(time.time())
                    unique_id = ''.join(random.choice(
                        '0123456789abcdef') for _ in range(6))
                    suggested_filename = f"experiment_stimuli_results_{session_id}_{timestamp}_{unique_id}_error.csv"

                    df['generation_timestamp'] = timestamp
                    df['batch_id'] = unique_id
                    df['total_iterations'] = total_iter_value
                    df['error_occurred'] = True
                    df['error_message'] = str(e)

                    import os

                    os.makedirs("outputs", exist_ok=True)
                    suggested_filename = os.path.join(
                        "outputs", f"experiment_stimuli_results_{session_id}_{timestamp}_{unique_id}.csv")

                    return df, suggested_filename
                else:
                    raise e

        if check_stop("Generation stopped after 'Validator'."):
            return None, None

        try:
            if check_stop("Generation stopped before Scorer."):
                return None, None

            # Step 3: Score
            if ablation["use_agent_3"]:
                scores = agent_3_score_stimulus(
                    model_client=model_client,
                    valid_stimulus=stimuli,
                    experiment_design=experiment_design,
                    properties=agent_3_properties,
                    prompt_template=AGENT_3_PROMPT_TEMPLATE,
                    stop_event=stop_event
                )

                if isinstance(scores, dict) and all(v == 0 for v in scores.values()):
                    if stop_event.is_set():
                        if check_stop("Generation stopped after 'Scorer'."):
                            return None, None

                print("Agent 3 Output:", scores)
                if websocket_callback:
                    websocket_callback(
                        "scorer", f"Scorer's Output: {json.dumps(scores, indent=2)}")

                if check_stop("Generation stopped after 'Scorer'."):
                    return None, None
            else:
                print("Ablation: Skipping Agent 3 (Scoring)")
                if websocket_callback:
                    websocket_callback("scorer", "Ablation: Skipping Agent 3")

            # Save results
            record = {
                "stimulus_id": iteration_num + 1,
                "stimulus_content": stimuli,
                "repetition_count": repetition_count,
                "validation_fails": validation_fails,
                "validation_failure_reasons": validation_result
            }
            if ablation["use_agent_3"]:
                record.update(scores or {})
            record_list.append(record)

            # Update previous_stimuli
            previous_stimuli.append(stimuli)

            # If some records have been generated, create intermediate results
            if (iteration_num + 1) % 5 == 0 or iteration_num + 1 == total_iter_value:
                temp_df = pd.DataFrame(record_list)
                session_id = settings.get('session_id', 'default')
                timestamp = int(time.time())
                unique_id = ''.join(random.choice('0123456789abcdef')
                                    for _ in range(6))
                suggested_filename = f"experiment_stimuli_results_{session_id}_{timestamp}_{unique_id}.csv"

                temp_df['generation_timestamp'] = timestamp
                temp_df['batch_id'] = unique_id
                temp_df['total_iterations'] = total_iter_value

                if check_stop():
                    return temp_df, suggested_filename

                if iteration_num + 1 == total_iter_value:
                    update_progress(total_iter_value)
                    return temp_df, suggested_filename

        except Exception as e:
            error_msg = f"Error in scoring step: {str(e)}"
            print(error_msg)
            if websocket_callback:
                websocket_callback("all", error_msg)
            if len(record_list) > 0:
                df = pd.DataFrame(record_list)
                session_id = settings.get('session_id', 'default')
                timestamp = int(time.time())
                unique_id = ''.join(random.choice('0123456789abcdef')
                                    for _ in range(6))
                suggested_filename = f"experiment_stimuli_results_{session_id}_{timestamp}_{unique_id}_error.csv"

                df['generation_timestamp'] = timestamp
                df['batch_id'] = unique_id
                df['total_iterations'] = total_iter_value
                df['error_occurred'] = True
                df['error_message'] = str(e)

                return df, suggested_filename
            else:
                raise e

    # Check again if stopped at final step
    if check_stop("Generation stopped at final step."):
        if len(record_list) > 0:
            df = pd.DataFrame(record_list)
            session_id = settings.get('session_id', 'default')
            timestamp = int(time.time())
            unique_id = ''.join(random.choice('0123456789abcdef')
                                for _ in range(6))
            suggested_filename = f"experiment_stimuli_results_{session_id}_{timestamp}_{unique_id}.csv"

            df['generation_timestamp'] = timestamp
            df['batch_id'] = unique_id
            df['total_iterations'] = total_iter_value
            df['error_occurred'] = False
            df['error_message'] = ""

            completion_msg = f"Data generation completed for session {session_id}"
            print(completion_msg)
            if websocket_callback:
                websocket_callback("all", completion_msg)
            return df, suggested_filename
        return None, None

    # Only generate DataFrame and return results after all iterations
    if len(record_list) > 0:
        update_progress(total_iter_value)

        df = pd.DataFrame(record_list)
        session_id = settings.get('session_id', 'default')
        timestamp = int(time.time())
        unique_id = ''.join(random.choice('0123456789abcdef')
                            for _ in range(6))
        suggested_filename = f"experiment_stimuli_results_{session_id}_{timestamp}_{unique_id}.csv"

        df['generation_timestamp'] = timestamp
        df['batch_id'] = unique_id
        df['total_iterations'] = total_iter_value
        df['error_occurred'] = False
        df['error_message'] = ""

        completion_msg = f"Data generation completed for session {session_id}"
        print(completion_msg)
        if websocket_callback:
            websocket_callback("all", completion_msg)
        return df, suggested_filename
    else:
        print("No records generated.")
        if websocket_callback:
            websocket_callback("all", "No records generated.")
        return None, None


# ======================
# 7. Legacy Support Function (保持向后兼容)
# ======================
def custom_model_inference_handler(session_id, prompt, model, api_url, api_key, params=None):
    """Legacy function for backward compatibility"""
    try:
        client = CustomModelClient(api_url, api_key, model)
        result = client.generate_completion(prompt, {}, params)

        if "error" in result:
            return {'error': result["error"]}, 500

        return {'response': json.dumps(result)}, 200
    except Exception as e:
        return {'error': f'Unexpected error: {str(e)}'}, 500
