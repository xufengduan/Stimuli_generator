"""Exercise prompt rendering and DeepSeek instructions at the API boundary."""
import json
from unittest.mock import Mock

import pytest

from stimulus_generator import backend


@pytest.mark.parametrize('agent,individual,properties,response,expected', [
    (1, False, {'text': {'type': 'string'}}, {'text': 'example'}, 'Use the field types'),
    (2, False, {'ok': {'type': 'boolean', 'description': 'Contains the target word'}}, {'ok': True}, 'Use JSON booleans true and false, not strings.'),
    (2, True, {'ok': {'type': 'boolean', 'description': 'Contains the target word'}}, {'ok': True}, 'Use JSON booleans true and false, not strings.'),
    (3, False, {'difficulty': {'type': 'integer', 'minimum': 1, 'maximum': 7, 'description': '1 = very easy; 7 = very difficult'}}, {'difficulty': 6}, 'Use integer scores'),
    (3, True, {'difficulty': {'type': 'integer', 'minimum': 1, 'maximum': 7, 'description': '1 = very easy; 7 = very difficult'}}, {'difficulty': 6}, 'Use integer scores'),
])
def test_rendered_prompts_reach_deepseek_with_correct_instructions(monkeypatch, agent, individual, properties, response, expected):
    post = Mock(return_value={'choices': [{'message': {'content': json.dumps(response)}}]})
    monkeypatch.setattr(backend, 'post_public_json', post)
    monkeypatch.setattr(backend, 'call_with_timeout', lambda func, args, kwargs, timeout: func(*args, **kwargs))
    client = backend.CustomModelClient('https://api.deepseek.com/chat/completions', 'dummy', 'deepseek-chat')
    design = 'A "quoted" design with {literal braces} and 中文.'
    if agent == 1:
        result = backend.agent_1_generate_stimulus(client, design, [], properties)
    elif agent == 2:
        func = backend.agent_2_validate_stimulus_individual if individual else backend.agent_2_validate_stimulus
        result = func(client, {'text': 'example'}, design, properties)
    else:
        func = backend.agent_3_score_stimulus_individual if individual else backend.agent_3_score_stimulus
        result = func(client, {'text': 'example'}, design, properties)
    assert result == response
    payload = post.call_args.args[2]
    assert payload['response_format'] == {'type': 'json_object'}
    prompt = payload['messages'][-1]['content']
    assert design in prompt
    assert expected in prompt
    assert 'True/False' not in prompt
    schema_text = prompt.split('Response schema properties: ', 1)[1]
    rendered_properties, _ = json.JSONDecoder().raw_decode(schema_text)
    assert rendered_properties == properties
    if agent == 1:
        assert 'Follow the same JSON format as the existing stimuli' not in prompt
        assert 'even when no existing stimuli are provided' in prompt
    elif agent == 3:
        assert '1 = very easy; 7 = very difficult' in prompt
        assert 'Do not assume that a higher score indicates better quality' in prompt


@pytest.mark.parametrize('prefix,expected', [
    ('Please verify the following NEW STIMULUS', 'Use JSON booleans true and false, not strings.'),
    ('Please rate the following STIMULUS', 'Use integer scores'),
])
def test_legacy_custom_prompt_prefixes_remain_supported(monkeypatch, prefix, expected):
    post = Mock(return_value={'choices': [{'message': {'content': '{}'}}]})
    monkeypatch.setattr(backend, 'post_public_json', post)
    monkeypatch.setattr(backend, 'call_with_timeout', lambda func, args, kwargs, timeout: func(*args, **kwargs))
    client = backend.CustomModelClient('https://api.deepseek.com/chat/completions', 'dummy', 'deepseek-chat')
    client.generate_completion(prefix + ': item', {})
    assert expected in post.call_args.args[2]['messages'][-1]['content']
