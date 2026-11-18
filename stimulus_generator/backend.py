import json
import ipaddress
import socket
from urllib.parse import urlsplit
import urllib3
import os
import queue
import random
import time
import traceback
from abc import ABC, abstractmethod
from multiprocessing import Process, Queue

import openai
import pandas as pd
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError as RequestsConnectionError

# Set OpenAI API key
# openai.api_key = ""

# Set Chutes AI API key (commented out)

# Use multiprocessing to implement real timeout mechanism


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
    result_queue = Queue()
    process = Process(target=_timeout_target, args=(result_queue, func, args, kwargs))
    deadline = time.monotonic() + timeout_seconds
    try:
        process.start()
        # Drain the pipe before joining: large results can otherwise block the child.
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {"error": f"API call timed out after {timeout_seconds} seconds"}
            try:
                result_type, result = result_queue.get(timeout=min(0.1, remaining))
                return result if result_type == 'success' else {"error": result}
            except queue.Empty:
                if not process.is_alive():
                    return {"error": "Process completed but no result returned"}
    finally:
        if process.pid is not None:
            process.join(timeout=0.2)
            if process.is_alive():
                process.terminate()
                process.join()
        result_queue.close()
        result_queue.join_thread()


def resolve_public_api(api_url):
    """Resolve once and pin the connection to an inspected public IP."""
    if not isinstance(api_url, str):
        raise ValueError("API URL must be a string")
    parsed = urlsplit(api_url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("API URL must be an HTTP(S) URL without credentials or fragments")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("API URL must resolve only to public addresses")
    return parsed, addresses[0][4][0]


def post_public_json(api_url, headers, data):
    parsed, address = resolve_public_api(api_url)
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    kwargs = {'host': address, 'port': port, 'timeout': urllib3.Timeout(connect=10, read=60)}
    if parsed.scheme == 'https':
        # Keep certificate verification and SNI tied to the original hostname.
        pool = urllib3.HTTPSConnectionPool(**kwargs, server_hostname=parsed.hostname,
                                          assert_hostname=parsed.hostname, cert_reqs='CERT_REQUIRED')
    else:
        pool = urllib3.HTTPConnectionPool(**kwargs)
    response = None
    try:
        target = parsed.path or '/'
        if parsed.query:
            target += '?' + parsed.query
        response = pool.request('POST', target, body=json.dumps(data).encode('utf-8'),
                                headers={**headers, 'Host': parsed.netloc},
                                redirect=False, retries=False, preload_content=False)
        if not 200 <= response.status < 300:
            raise RequestException(f"API returned HTTP {response.status}; redirects are not permitted")
        body = response.read(8 * 1024 * 1024 + 1)
        if len(body) > 8 * 1024 * 1024:
            raise RequestException("API response exceeds 8 MiB")
        return json.loads(body)
    except urllib3.exceptions.HTTPError as exc:
        raise RequestException(f"API connection failed: {exc}") from exc
    finally:
        if response is not None:
            response.close()
        pool.close()


def validate_boolean_result(result, properties):
    if not isinstance(result, dict) or 'error' in result:
        return {"error": "Invalid validation response"}
    if set(result) != set(properties) or any(type(v) is not bool for v in result.values()):
        return {"error": "Validation response must contain every criterion as a boolean"}
    return result


def validate_scores(result, properties):
    # Missing/error values stay missing rather than masquerading as actual zero scores.
    if not isinstance(result, dict) or 'error' in result:
        return {field: None for field in properties}
    checked = {}
    for field, spec in properties.items():
        value = result.get(field)
        valid = type(value) in (int, float)
        if spec.get('type') == 'integer':
            valid = type(value) is int
        if valid:
            valid = spec.get('minimum', float('-inf')) <= value <= spec.get('maximum', float('inf'))
        checked[field] = value if valid else None
    return checked


# ======================
# 1. Configuration (Prompt + Schema)
# ======================
# ---- Agent 1 Prompt ----
AGENT_1_PROMPT_TEMPLATE = """\
Generate one stimulus item for a psycholinguistic experiment according to the experimental design below.
Include all condition variants specified in the experimental design.

Experimental design: {experiment_design}

Existing stimuli (DO NOT repeat any of these): {previous_stimuli}

Previously rejected stimuli with validation feedback (learn from these failures and avoid similar issues):
{rejected_stimuli}

CRITICAL REQUIREMENTS:
1. Generate a COMPLETELY NEW and UNIQUE stimulus that is DIFFERENT from ALL existing stimuli above.
2. Do NOT repeat or slightly modify any existing stimulus - create something entirely original.
3. Avoid any content that overlaps with existing or rejected stimuli.
4. Learn from the rejected stimuli above - understand why they failed validation and avoid making similar mistakes.
{generation_requirements}

Return only a single JSON object that conforms to the supplied response schema, without Markdown code fences or explanatory text.
"""

# ---- Agent 2 Prompt ----
AGENT_2_PROMPT_TEMPLATE = """\
Evaluate the following stimulus against the experimental design and each validation criterion defined in the supplied response schema.
For each criterion, return true if the stimulus satisfies it and false otherwise.

NEW STIMULUS: {new_stimulus}

Experimental design: {experiment_design}

Return only a single JSON object containing every required criterion and no additional fields.
Use JSON booleans true and false, not strings. Do not include Markdown code fences or explanatory text.
"""

# ---- Agent 3 Prompt ----
AGENT_3_PROMPT_TEMPLATE = """\
Rate the following stimulus on each scoring dimension specified below, using the experimental design as context.

STIMULUS: {valid_stimulus}
Experimental design: {experiment_design}

SCORING REQUIREMENTS:
{scoring_requirements}

Follow the description and any scale anchors specified for each dimension. Do not assume that a higher score indicates better quality or greater suitability.
Return only a single JSON object containing one integer score for every required dimension, within its specified inclusive range.
Do not include additional fields, Markdown code fences, or explanatory text.
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
            print("OpenAI API key configured successfully")
        else:
            print("Warning: No OpenAI API key provided!")

    def _api_call(self, prompt, properties, params, api_key):
        """API call function, will be called by multiprocessing"""
        # set API key in subprocess
        openai.api_key = api_key

        return openai.ChatCompletion.create(
            model=params["model"],
            **{key: params[key] for key in ("temperature", "seed", "top_p", "max_tokens") if key in params},
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
                return {"error": f"Failed to parse response: {str(e)}"}
            except (openai.error.APIError, openai.error.RateLimitError) as e:
                print(f"OpenAI API error attempt {attempt + 1}/3: {e}")
                if attempt == 2:
                    return {"error": f"OpenAI API error after 3 attempts: {str(e)}"}
                time.sleep(2 ** attempt)
            except openai.error.AuthenticationError as e:
                print(f"OpenAI authentication error: {e}")
                return {"error": f"Authentication failed: {str(e)}"}
            except openai.error.InvalidRequestError as e:
                print(f"OpenAI invalid request: {e}")
                return {"error": f"Invalid request: {str(e)}"}

    def get_default_params(self):
        return {"model": "gpt-4o"}


# class HuggingFaceClient(ModelClient):
#     """Hugging Face model client"""

#     def __init__(self, api_key):
#         self.api_key = api_key

#     def _api_call(self, messages, response_format, params):
#         """API call function that will be called by multiprocessing"""
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

#         # Retry mechanism
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
        try:
            return post_public_json(self.api_url, headers, request_data)
        except Timeout:
            raise Timeout(
                f"Request to {self.api_url} timed out after 60 seconds")
        except RequestsConnectionError as e:
            raise RequestsConnectionError(
                f"Failed to connect to {self.api_url}: {str(e)}")
        except RequestException as e:
            raise RequestException(f"Request failed: {str(e)}")

    def generate_completion(self, prompt, properties, params=None):

        provider_host = urlsplit(self.api_url.strip()).hostname
        is_deepseek = provider_host == "api.deepseek.com"
        is_openai = provider_host == "api.openai.com"

        if not is_openai:
            rand_stamp = int(time.time())
            # Generate field list
            field_list = ', '.join([f'"{k}"' for k in properties.keys()])
            # Recognize revised and legacy prompts, including individual modes.
            # Keep legacy prefixes for callers that supply their own templates.
            if prompt.strip().startswith(("Evaluate the following stimulus", "Please verify the following NEW STIMULUS")):
                value_instruction = "Use JSON booleans true and false, not strings."
            elif prompt.strip().startswith(("Rate the following stimulus", "Please rate the following STIMULUS")):
                value_instruction = "Use integer scores within the specified inclusive ranges. Follow each dimension's description and scale direction."
            else:
                value_instruction = "Use the field types specified in the response schema."
            if properties:
                prompt = prompt.rstrip() + (
                    f"\nReturn only a single JSON object with exactly these fields: {field_list}. "
                    f"Response schema properties: {json.dumps(properties, ensure_ascii=False)}. "
                    f"{value_instruction} Do not include Markdown code fences or explanatory text."
                )
            else:
                # Property drafting defines its own nested JSON structure in the prompt.
                prompt = prompt.rstrip() + (
                    "\nReturn only a single JSON object following the structure requested above. "
                    f"{value_instruction} "
                    "Do not include Markdown code fences or explanatory text."
                )

            request_data = {
                "model": self.model_name,
                "messages": ([{"role": "system", "content": f"RAND:{rand_stamp}"}] if is_deepseek else [])
                            + [{"role": "user", "content": prompt}],
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

        # GPT-5.4 accepts sampling parameters only with reasoning disabled.
        # Use the provider's native spelling, without overriding explicit effort.
        if request_data.get('model') in ('gpt-5.4', 'openai/gpt-5.4'):
            is_openrouter = urlsplit(self.api_url).hostname == 'openrouter.ai'
            if is_openrouter:
                if 'reasoning_effort' not in request_data:
                    request_data.setdefault('reasoning', {'effort': 'none'})
                effort = request_data.get('reasoning_effort', request_data.get('reasoning', {}).get('effort', 'none'))
            else:
                # Current OpenAI chat models use max_completion_tokens; the UI
                # keeps the familiar max_tokens setting for other providers.
                if 'max_tokens' in request_data:
                    request_data.setdefault('max_completion_tokens', request_data.pop('max_tokens'))
                request_data.setdefault('reasoning_effort', 'none')
                effort = request_data['reasoning_effort']
            if effort != 'none':
                for key in ('temperature', 'top_p', 'logprobs'):
                    request_data.pop(key, None)

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
                    self._api_call, (request_data, headers), {}, 600)

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

            except json.JSONDecodeError as e:
                print(
                    f"Custom API JSON parsing error attempt {attempt + 1}/3: {e}")
                if attempt == 2:
                    return {"error": f"API JSON parsing error after 3 attempts: {str(e)}"}
                time.sleep(2 ** attempt)
            except KeyError as e:
                print(
                    f"Custom API response missing expected key attempt {attempt + 1}/3: {e}")
                if attempt == 2:
                    return {"error": f"API response missing expected key after 3 attempts: {str(e)}"}
                time.sleep(2 ** attempt)
            except (Timeout, RequestsConnectionError) as e:
                print(
                    f"Custom API connection error attempt {attempt + 1}/3: {e}")
                if attempt == 2:
                    return {"error": f"API connection error after 3 attempts: {str(e)}"}
                time.sleep(2 ** attempt)
            except RequestException as e:
                print(f"Custom API request error attempt {attempt + 1}/3: {e}")
                if attempt == 2:
                    return {"error": f"API request error after 3 attempts: {str(e)}"}
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
            if key in existing_stimulus:
                try:
                    existing_val = str(existing_stimulus[key]).lower()
                    new_val = str(new_value).lower()
                    if existing_val == new_val:
                        return True
                except (AttributeError, TypeError):
                    # Skip comparison if values can't be converted to string
                    continue

    return False


def agent_1_generate_stimulus(
        model_client,
        experiment_design,
        previous_stimuli,
        properties,
        rejected_stimuli=None,
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
    generation_requirements = "5. Follow the supplied response schema. Include every required field and no additional fields, even when no existing stimuli are provided."

    if rejected_stimuli is None:
        rejected_stimuli = []

    prompt = prompt_template.format(
        experiment_design=experiment_design,
        previous_stimuli=previous_stimuli,
        rejected_stimuli=rejected_stimuli,
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
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Error parsing response in agent_1_generate_stimulus: {e}")
        return {"stimulus": "ERROR/ERROR"}
    except (RequestException, Timeout) as e:
        print(f"Network error in agent_1_generate_stimulus: {e}")
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

        return validate_boolean_result(result, properties)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Error parsing validation response: {e}")
        return {"error": f"Failed to parse validation response: {str(e)}"}
    except (RequestException, Timeout) as e:
        print(f"Network error in validation: {e}")
        return {"error": f"Network error during validation: {str(e)}"}


def agent_2_validate_stimulus_individual(
        model_client,
        new_stimulus,
        experiment_design,
        properties,
        prompt_template=AGENT_2_PROMPT_TEMPLATE,
        stop_event=None,
        websocket_callback=None):
    """
    Agent 2: Validate experimental stimulus by checking each criterion individually
    """
    if stop_event and stop_event.is_set():
        print("Generation stopped by user in agent_2_validate_stimulus_individual.")
        return {"error": "Stopped by user"}

    validation_results = {}

    # Create individual prompt template for each criterion
    individual_prompt_template = """\
Evaluate the following stimulus against the specific validation criterion below, using the experimental design as context.

NEW STIMULUS: {new_stimulus}

Experimental design: {experiment_design}

SPECIFIC CRITERION TO VALIDATE:
Property: {property_name}
Criterion specification: {property_description}

Return only a single JSON object with exactly one field: "{property_name}".
Use the JSON boolean true if the criterion is satisfied and false otherwise, not a string.
Do not include Markdown code fences or explanatory text.
"""

    try:
        total_criteria = len(properties)
        current_criterion = 0

        for property_name, property_description in properties.items():
            current_criterion += 1

            if stop_event and stop_event.is_set():
                print(
                    f"Generation stopped by user while validating {property_name}.")
                return {"error": "Stopped by user"}

            if websocket_callback:
                websocket_callback(
                    "validator", f"Validating criterion {current_criterion}/{total_criteria}: {property_name}")

            # Create prompt for individual criterion
            prompt = individual_prompt_template.format(
                new_stimulus=new_stimulus,
                experiment_design=experiment_design,
                property_name=property_name,
                property_description=json.dumps(property_description, ensure_ascii=False)
            )

            # Create properties dict with single criterion
            single_property = {property_name: property_description}

            # Get model-specific default params and override temperature
            fixed_params = model_client.get_default_params()
            fixed_params["temperature"] = 0

            result = model_client.generate_completion(
                prompt, single_property, fixed_params)

            print(f"Agent 2 Individual Validation - {property_name}: {result}")

            if "error" in result:
                print(
                    f"Agent 2 Individual API error for {property_name}: {result}")
                if websocket_callback:
                    websocket_callback(
                        "validator", f"Error validating criterion {property_name}: {result.get('error', 'Unknown error')}")
                return {"error": f"Failed to validate criterion {property_name}: {result.get('error', 'Unknown error')}"}

            result = validate_boolean_result(result, single_property)
            if "error" in result:
                return result

            # Extract the validation result for this criterion
            if property_name in result:
                validation_results[property_name] = result[property_name]
                status = "PASSED" if result[property_name] else "FAILED"
                if websocket_callback:
                    websocket_callback(
                        "validator", f"Criterion {property_name}: {status}")

                # Early stop: if any criterion fails, immediately reject
                if not result[property_name]:
                    if websocket_callback:
                        websocket_callback(
                            "validator", f"Early rejection: Criterion {property_name} failed. Stopping validation.")
                    print(
                        f"Agent 2 Individual Validation - Early stop: {property_name} failed")
                    return validation_results
            else:
                print(
                    f"Warning: {property_name} not found in result, assuming False")
                validation_results[property_name] = False
                if websocket_callback:
                    websocket_callback(
                        "validator", f"Criterion {property_name}: FAILED (parsing error)")
                    websocket_callback(
                        "validator", f"Early rejection: Criterion {property_name} failed. Stopping validation.")
                print(
                    f"Agent 2 Individual Validation - Early stop: {property_name} failed (parsing error)")
                return validation_results

        print("Agent 2 Individual Validation - All Results:", validation_results)
        if websocket_callback:
            websocket_callback(
                "validator", "All criteria passed successfully!")
        return validation_results

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Error parsing individual validation response: {e}")
        return {"error": f"Failed to parse validation response: {str(e)}"}
    except (RequestException, Timeout) as e:
        print(f"Network error in individual validation: {e}")
        return {"error": f"Network error during validation: {str(e)}"}


def generate_scoring_requirements(properties):
    """
    Generate scoring requirements text from properties dictionary
    """
    if not properties:
        return "No specific scoring requirements provided."

    requirements = []
    for aspect_name, aspect_details in properties.items():
        min_score = aspect_details.get('minimum', 0)
        max_score = aspect_details.get('maximum', 10)
        description = aspect_details.get('description', aspect_name)

        requirements.append(
            f"- {aspect_name}: {description} (Score range: {min_score} to {max_score})")

    return "\n".join(requirements)


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
        return {field: None for field in properties.keys()} if properties else {}

    # Generate scoring requirements text
    scoring_requirements = generate_scoring_requirements(properties)

    prompt = prompt_template.format(
        experiment_design=experiment_design,
        valid_stimulus=valid_stimulus,
        scoring_requirements=scoring_requirements
    )

    try:
        # use temperature=0 parameter, get model-specific default params and override temperature
        fixed_params = model_client.get_default_params()
        fixed_params["temperature"] = 0
        result = model_client.generate_completion(
            prompt, properties, fixed_params)

        if stop_event and stop_event.is_set():
            print("Generation stopped by user after API call in agent_3_score_stimulus.")
            return {field: None for field in properties.keys()} if properties else {}

        if "error" in result:
            print(f"Agent 3 API error: {result}")
            return {field: None for field in properties.keys()}

        return validate_scores(result, properties)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Error parsing scoring response: {e}")
        return {field: None for field in properties.keys()}
    except (RequestException, Timeout) as e:
        print(f"Network error in scoring: {e}")
        return {field: None for field in properties.keys()}


def agent_3_score_stimulus_individual(
        model_client,
        valid_stimulus,
        experiment_design,
        properties,
        prompt_template=AGENT_3_PROMPT_TEMPLATE,
        stop_event=None,
        websocket_callback=None):
    """
    Agent 3: Score experimental stimulus by evaluating each aspect individually
    """
    if stop_event and stop_event.is_set():
        print("Generation stopped by user in agent_3_score_stimulus_individual.")
        return {field: None for field in properties.keys()} if properties else {}

    scoring_results = {}

    # Create individual prompt template for each aspect
    individual_prompt_template = """\
Rate the following stimulus on the specific scoring dimension below, using the experimental design as context.

STIMULUS: {valid_stimulus}
Experimental design: {experiment_design}

SPECIFIC ASPECT TO SCORE:
- Aspect Name: {aspect_name}
- Description: {aspect_description}
- Minimum Score: {min_score}
- Maximum Score: {max_score}
- Score Range: You must provide an integer score between {min_score} and {max_score} (inclusive)

SCORING INSTRUCTIONS:
Rate this stimulus on the "{aspect_name}" dimension according to its description and any specified scale anchors.
Follow the scale direction specified for this dimension. Do not assume that a higher score indicates better quality or greater suitability.

Return only a single JSON object with exactly one field: "{aspect_name}".
Its value must be an integer between {min_score} and {max_score}, inclusive.
Do not include Markdown code fences or explanatory text.
"""

    try:
        total_aspects = len(properties)
        current_aspect = 0

        for aspect_name, aspect_details in properties.items():
            current_aspect += 1

            if stop_event and stop_event.is_set():
                print(
                    f"Generation stopped by user while scoring {aspect_name}.")
                return {field: None for field in properties.keys()}

            if websocket_callback:
                websocket_callback(
                    "scorer", f"Evaluating aspect {current_aspect}/{total_aspects}: {aspect_name}")

            # Extract min and max scores from aspect details
            min_score = aspect_details.get('minimum', 0)
            max_score = aspect_details.get('maximum', 10)
            description = aspect_details.get('description', aspect_name)

            # Create prompt for individual aspect
            prompt = individual_prompt_template.format(
                valid_stimulus=valid_stimulus,
                experiment_design=experiment_design,
                aspect_name=aspect_name,
                aspect_description=description,
                min_score=min_score,
                max_score=max_score
            )

            # Create properties dict with single aspect (include all details for JSON schema)
            single_aspect = {aspect_name: {
                'type': 'integer',
                'description': description,
                'minimum': min_score,
                'maximum': max_score
            }}

            # Get model-specific default params and override temperature
            fixed_params = model_client.get_default_params()
            fixed_params["temperature"] = 0

            result = model_client.generate_completion(
                prompt, single_aspect, fixed_params)

            print(f"Agent 3 Individual Scoring - {aspect_name}: {result}")

            if "error" in result:
                print(
                    f"Agent 3 Individual API error for {aspect_name}: {result}")
                if websocket_callback:
                    websocket_callback(
                        "scorer", f"Error scoring aspect {aspect_name}: {result.get('error', 'Unknown error')}")
                scoring_results[aspect_name] = None
                continue

            # Extract the scoring result for this aspect
            if aspect_name in result:
                scoring_results[aspect_name] = validate_scores(result, single_aspect)[aspect_name]
            else:
                print(
                    f"Warning: {aspect_name} not found in result, recording a missing score")
                scoring_results[aspect_name] = None
                if websocket_callback:
                    websocket_callback(
                        "scorer", f"Aspect {aspect_name}: missing/{max_score} (parsing error)")

        print("Agent 3 Individual Scoring - All Results:", scoring_results)
        if websocket_callback:
            total_score = sum(v for v in scoring_results.values() if v is not None)
            max_possible = sum(aspect_details.get('maximum', 10)
                               for aspect_details in properties.values())
            websocket_callback(
                "scorer", f"Individual scoring completed! Total: {total_score}/{max_possible}")
        return scoring_results

    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"Error parsing individual scoring response: {e}")
        return {field: None for field in properties.keys()}
    except (RequestException, Timeout) as e:
        print(f"Network error in individual scoring: {e}")
        return {field: None for field in properties.keys()}


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

    # Helper function to create partial result when error or stop occurs
    def create_partial_result(record_list, message, is_error=True):
        nonlocal total_iterations
        if len(record_list) > 0:
            df = pd.DataFrame(record_list)
            session_id = settings.get('session_id', 'default')
            timestamp = int(time.time())
            unique_id = ''.join(random.choice('0123456789abcdef')
                                for _ in range(6))
            suffix = "_partial" if is_error else "_stopped"
            suggested_filename = f"experiment_stimuli_results_{session_id}_{timestamp}_{unique_id}{suffix}.csv"

            df['generation_timestamp'] = timestamp
            df['batch_id'] = unique_id
            df['total_iterations'] = total_iterations.value
            df['stopped_by_user'] = not is_error
            df['error_occurred'] = is_error
            df['message'] = message
            df['completed_iterations'] = len(record_list)

            os.makedirs("outputs", exist_ok=True)
            suggested_filename = os.path.join("outputs", suggested_filename)

            return df, suggested_filename
        return None, None

    # Helper function to check stop and return partial data if available
    def check_stop_and_return(message="Generation stopped by user."):
        if stop_event.is_set():
            print(message)
            if websocket_callback:
                websocket_callback("all", message)
            return True, create_partial_result(record_list, message, is_error=False)
        return False, (None, None)

    # Immediately check if stopped
    if check_stop("Generation stopped before starting."):
        return None, None

    record_list = []
    rejected_stimuli_memory = []
    agent_1_properties = settings.get('agent_1_properties', {})
    avoid_duplication_fields = set(settings.get('avoid_duplication_fields', []))
    visible_properties = {key: value for key, value in agent_1_properties.items()
                          if key not in avoid_duplication_fields}
    print("Agent 1 Properties:", visible_properties)
    if websocket_callback:
        websocket_callback(
            "setup", f"Agent 1 Properties: {visible_properties}")

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
        stopped, partial_result = check_stop_and_return()
        if stopped:
            return partial_result

        round_message = f"=== No. {iteration_num + 1} Round ==="
        print(round_message)
        if websocket_callback:
            websocket_callback("all", round_message)

        # Step 1: Generate stimulus
        current_retry_count = 0  # Retry counter for this iteration
        attempt_count = 0
        repetition_start = repetition_count
        validation_start = validation_fails
        while True:
            attempt_count += 1
            if attempt_count > 50:
                return create_partial_result(record_list, "Generation failed after 50 attempts; check model credentials and responses.")
            stopped, partial_result = check_stop_and_return()
            if stopped:
                return partial_result

            try:
                stimuli = agent_1_generate_stimulus(
                    model_client=model_client,
                    experiment_design=experiment_design,
                    previous_stimuli=previous_stimuli,
                    properties=agent_1_properties,
                    rejected_stimuli=rejected_stimuli_memory,
                    prompt_template=AGENT_1_PROMPT_TEMPLATE,
                    params=custom_params,
                    stop_event=stop_event
                )

                if isinstance(stimuli, dict) and stimuli.get('stimulus') == 'STOPPED':
                    stopped, partial_result = check_stop_and_return(
                        "Generation stopped after 'Generator'.")
                    if stopped:
                        return partial_result

                # Skip validation if Agent 1 returned an error
                if isinstance(stimuli, dict) and stimuli.get('stimulus') == 'ERROR/ERROR':
                    print("Agent 1 returned ERROR, regenerating...")
                    if websocket_callback:
                        websocket_callback(
                            "generator", "Generator returned ERROR, regenerating...")
                    continue

                visible_stimuli = {key: value for key, value in stimuli.items()
                                   if key not in avoid_duplication_fields}
                print("Agent 1 Output:", visible_stimuli)
                if websocket_callback:
                    websocket_callback(
                        "generator", f"Generator's Output: {json.dumps(visible_stimuli, ensure_ascii=False, indent=2)}")

                stopped, partial_result = check_stop_and_return(
                    "Generation stopped after 'Generator'.")
                if stopped:
                    return partial_result

                # Step 1.5: Check if stimulus already exists

                if check_stimulus_repetition(stimuli, previous_stimuli):
                    repetition_count += 1
                    current_retry_count += 1

                    # Add retry limit to avoid infinite loops (but never accept duplicates)
                    max_repetition_retries = 50
                    if current_retry_count > max_repetition_retries:
                        error_msg = f"Failed to generate unique stimulus after {max_repetition_retries} attempts. Consider adjusting experiment design or reducing target count."
                        print(error_msg)
                        if websocket_callback:
                            websocket_callback("generator", error_msg)
                        # Return partial results instead of raising exception
                        return create_partial_result(record_list, error_msg)

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

                stopped, partial_result = check_stop_and_return()
                if stopped:
                    return partial_result

                # Step 2: Validate stimulus
                # Check if individual validation is enabled
                individual_validation = settings.get(
                    'agent_2_individual_validation', False)

                if individual_validation:
                    if websocket_callback:
                        websocket_callback(
                            "validator", f"Using individual validation mode - checking {len(agent_2_properties)} criteria...")
                    validation_result = agent_2_validate_stimulus_individual(
                        model_client=model_client,
                        new_stimulus=stimuli,
                        experiment_design=experiment_design,
                        properties=agent_2_properties,
                        stop_event=stop_event,
                        websocket_callback=websocket_callback
                    )
                else:
                    if websocket_callback:
                        websocket_callback(
                            "validator", "Using batch validation mode...")
                    validation_result = agent_2_validate_stimulus(
                        model_client=model_client,
                        new_stimulus=stimuli,
                        experiment_design=experiment_design,
                        properties=agent_2_properties,
                        prompt_template=AGENT_2_PROMPT_TEMPLATE,
                        stop_event=stop_event
                    )

                if isinstance(validation_result, dict) and validation_result.get('error') == 'Stopped by user':
                    stopped, partial_result = check_stop_and_return(
                        "Generation stopped after 'Validator'.")
                    if stopped:
                        return partial_result

                print("Agent 2 Output:", validation_result)
                if websocket_callback:
                    websocket_callback(
                        "validator", f"Validator's Output: {json.dumps(validation_result, indent=2)}")

                stopped, partial_result = check_stop_and_return(
                    "Generation stopped after 'Validator'.")
                if stopped:
                    return partial_result

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
                    current_retry_count += 1

                    # Add to rejected memory (only if it's a valid stimulus, not an error)
                    is_error_stimulus = (
                        isinstance(stimuli, dict) and
                        stimuli.get('stimulus') in ['ERROR/ERROR', 'STOPPED']
                    )
                    if not is_error_stimulus:
                        rejected_item = {
                            "stimulus": stimuli,
                            "validation_result": validation_result,
                            "failed_fields": failed_fields
                        }
                        rejected_stimuli_memory.append(rejected_item)
                        # Limit memory size to prevent unbounded growth
                        MAX_REJECTED_MEMORY = 20
                        if len(rejected_stimuli_memory) > MAX_REJECTED_MEMORY:
                            rejected_stimuli_memory = rejected_stimuli_memory[-MAX_REJECTED_MEMORY:]

                    print(
                        f"Failed validation for fields: {failed_fields}, regenerating...")
                    if websocket_callback:
                        websocket_callback(
                            "validator", f"Failed validation for fields: {failed_fields}, regenerating...")

                    # Check retry limit to avoid infinite loops
                    max_retries = 50
                    if current_retry_count > max_retries:
                        error_msg = f"Failed to generate valid stimulus after {max_retries} attempts. Consider adjusting validation criteria."
                        print(error_msg)
                        if websocket_callback:
                            websocket_callback("validator", error_msg)
                        # Return partial results instead of raising exception
                        return create_partial_result(record_list, error_msg)

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

                    os.makedirs("outputs", exist_ok=True)
                    suggested_filename = os.path.join(
                        "outputs", f"experiment_stimuli_results_{session_id}_{timestamp}_{unique_id}.csv")

                    return df, suggested_filename
                else:
                    raise e

        stopped, partial_result = check_stop_and_return(
            "Generation stopped after 'Validator'.")
        if stopped:
            return partial_result

        try:
            stopped, partial_result = check_stop_and_return(
                "Generation stopped before Scorer.")
            if stopped:
                return partial_result

            # Step 3: Score
            if ablation["use_agent_3"]:
                # Check if individual scoring is enabled
                individual_scoring = settings.get(
                    'agent_3_individual_scoring', False)

                if individual_scoring:
                    if websocket_callback:
                        websocket_callback(
                            "scorer", f"Using individual scoring mode - evaluating {len(agent_3_properties)} aspects...")
                    scores = agent_3_score_stimulus_individual(
                        model_client=model_client,
                        valid_stimulus=stimuli,
                        experiment_design=experiment_design,
                        properties=agent_3_properties,
                        stop_event=stop_event,
                        websocket_callback=websocket_callback
                    )
                else:
                    if websocket_callback:
                        websocket_callback(
                            "scorer", "Using batch scoring mode...")
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
                        stopped, partial_result = check_stop_and_return(
                            "Generation stopped after 'Scorer'.")
                        if stopped:
                            return partial_result

                print("Agent 3 Output:", scores)
                if websocket_callback:
                    websocket_callback(
                        "scorer", f"Scorer's Output: {json.dumps(scores, indent=2)}")

                stopped, partial_result = check_stop_and_return(
                    "Generation stopped after 'Scorer'.")
                if stopped:
                    return partial_result
            else:
                print("Ablation: Skipping Agent 3 (Scoring)")
                if websocket_callback:
                    websocket_callback("scorer", "Ablation: Skipping Agent 3")

            # Save results
            record = {
                "stimulus_id": iteration_num + 1,
                "stimulus_content": stimuli,
                "generation_attempts": attempt_count,
                "repetition_retries": repetition_count - repetition_start,
                "validation_retries": validation_fails - validation_start,
                "cumulative_repetition_retries": repetition_count,
                "cumulative_validation_retries": validation_fails,
                "validation_results": validation_result if ablation["use_agent_2"] else {}
            }
            if ablation["use_agent_3"]:
                record["scores"] = scores or {}
                if any(value is None for value in scores.values()):
                    record["scoring_error"] = "One or more scores could not be obtained or failed schema validation"
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
# 7. Legacy Support Function (maintain backward compatibility)
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
