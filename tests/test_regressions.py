import io
import json
import time
from multiprocessing import Value
from threading import Event
from unittest.mock import Mock

import pandas as pd
import pytest
from stimulus_generator import backend
from stimulus_generator import app as web


def large_result():
    return 'x' * 1_000_000


def slow_result():
    time.sleep(5)


def failed_result():
    raise ValueError('provider failed')


@pytest.mark.parametrize('func,timeout,expected', [(large_result, 5, None), (slow_result, .1, 'timed out'), (failed_result, 5, 'provider failed')])
def test_process_result(func, timeout, expected):
    result = backend.call_with_timeout(func, (), {}, timeout)
    if expected:
        assert expected in result['error']
    else:
        assert result == 'x' * 1_000_000


@pytest.mark.parametrize('result', [{}, {'criterion': 'false'}, {'criterion': 1}, {'criterion': None}, [], {'criterion': True, 'extra': True}])
def test_validation_fails_closed(result):
    assert 'error' in backend.validate_boolean_result(result, {'criterion': {'type': 'boolean'}})


def test_validation_retains_real_false():
    assert backend.validate_boolean_result({'criterion': False}, {'criterion': {}}) == {'criterion': False}


@pytest.mark.parametrize('result', [{'error': 'outage'}, {}, {'quality': '7'}, {'quality': True}, {'quality': 8}, {'quality': 2.5}])
def test_invalid_scores_are_missing(result):
    assert backend.validate_scores(result, {'quality': {'type': 'integer', 'minimum': 1, 'maximum': 7}}) == {'quality': None}


def test_real_zero_is_preserved():
    assert backend.validate_scores({'quality': 0}, {'quality': {'type': 'integer', 'minimum': 0}}) == {'quality': 0}


def test_openai_parameters(monkeypatch):
    create = Mock(return_value={})
    monkeypatch.setattr(backend.openai.ChatCompletion, 'create', create)
    backend.OpenAIClient('dummy')._api_call('prompt', {}, {'model': 'gpt-4o', 'temperature': 0}, 'dummy')
    assert create.call_args.kwargs['temperature'] == 0


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', '::ffff:127.0.0.1'])
def test_private_api_blocked(monkeypatch, address):
    monkeypatch.setattr(backend.socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', (address, 443))])
    with pytest.raises(ValueError):
        backend.resolve_public_api('https://example.com/chat')


def test_https_pinned_and_redirect_blocked(monkeypatch):
    monkeypatch.setattr(backend.socket, 'getaddrinfo', lambda *a, **k: [(2, 1, 6, '', ('8.8.8.8', 443))])
    pool = Mock()
    pool.request.return_value.status = 302
    factory = Mock(return_value=pool)
    monkeypatch.setattr(backend.urllib3, 'HTTPSConnectionPool', factory)
    with pytest.raises(backend.RequestException):
        backend.post_public_json('https://example.com/chat', {}, {})
    assert factory.call_args.kwargs['host'] == '8.8.8.8'
    assert factory.call_args.kwargs['server_hostname'] == 'example.com'
    assert factory.call_args.kwargs['cert_reqs'] == 'CERT_REQUIRED'
    assert pool.request.call_args.kwargs['redirect'] is False
    pool.close.assert_called_once()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'SESSION_DIR', str(tmp_path))
    web.active_sessions.clear()
    return web.app.test_client()


def test_duplicate_submission_does_not_mutate_worker(client):
    state = web.load_session('test')
    state['generation_thread'] = Mock(is_alive=Mock(return_value=True))
    state['generation_file'] = 'old.csv'
    response = client.post('/test/generate_stimulus', json={'iteration': 1, 'experimentDesign': 'design'})
    assert response.status_code == 409
    assert not state['stop_event'].is_set()
    assert state['generation_file'] == 'old.csv'


def test_invalid_input_keeps_results(client):
    state = web.load_session('test')
    state['generation_file'] = 'old.csv'
    response = client.post('/test/generate_stimulus', json={'iteration': None, 'experimentDesign': 'design'})
    assert response.status_code == 400
    assert state['generation_file'] == 'old.csv'


def test_repeat_download_and_disk_restore(client):
    state = web.load_session('test')
    state['generation_file'] = 'test.csv'
    state['dataframe'] = pd.DataFrame([{'stimulus_content': {'text': 'hello'}, 'quality': None, 'scoring_error': 'API error'}])
    web.save_session('test', state)
    web.active_sessions.clear()
    for _ in range(2):
        response = client.get('/test/download/test.csv')
        assert response.status_code == 200
        df = pd.read_csv(io.BytesIO(response.data))
        assert df.loc[0, 'Content1'] == 'hello'
        assert pd.isna(df.loc[0, 'quality'])
        assert df.loc[0, 'scoring_error'] == 'API error'
    assert web.active_sessions['test']['dataframe'] is not None


def settings():
    return dict(stop_event=Event(), current_iteration=Value('i', 0), total_iterations=Value('i', 1),
                experiment_design='design', previous_stimuli=[], model_choice='GPT-4o', iteration=1,
                agent_1_properties={'text': {'type': 'string'}},
                agent_2_properties={'ok': {'type': 'boolean'}},
                agent_3_properties={'quality': {'type': 'integer', 'minimum': 1, 'maximum': 7}})


def test_full_flow(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    client = Mock()
    client.get_default_params.return_value = {'model': 'gpt-4o'}
    client.generate_completion.side_effect = [{'text': 'hello'}, {'ok': True}, {'quality': 6}]
    monkeypatch.setattr(backend, 'create_model_client', lambda *a: client)
    df, filename = backend.generate_stimuli(settings())
    assert len(df) == 1 and df.loc[0, 'quality'] == 6
    assert df.loc[0, 'stimulus_content'] == {'text': 'hello'}
    assert client.generate_completion.call_count == 3
    assert filename.endswith('.csv')


def test_provider_failure_is_bounded(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    client = Mock()
    client.generate_completion.return_value = {'error': 'bad key'}
    monkeypatch.setattr(backend, 'create_model_client', lambda *a: client)
    assert backend.generate_stimuli(settings()) == (None, None)
    assert client.generate_completion.call_count == 50


def test_failed_score_still_exports_missing_value(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    client = Mock()
    client.get_default_params.return_value = {}
    client.generate_completion.side_effect = [{'text': 'hello'}, {'ok': True}, {'error': 'outage'}]
    monkeypatch.setattr(backend, 'create_model_client', lambda *a: client)
    df, _ = backend.generate_stimuli(settings())
    assert pd.isna(df.loc[0, 'quality'])
    assert df.loc[0, 'scoring_error']


def test_legacy_stimulus_and_nonzero_index():
    df = pd.DataFrame([{'stimulus_content': "{'text': 'legacy'}"}], index=[5])
    result = web.expand_stimulus_content_to_columns(df)
    assert len(result) == 1 and result.loc[5, 'Content1'] == 'legacy'


def test_session_path_is_confined():
    with pytest.raises(ValueError):
        web.get_session_file('../outside')


def test_individual_validation_and_scoring():
    client = Mock()
    client.get_default_params.return_value = {}
    client.generate_completion.return_value = {'ok': 'false'}
    assert 'error' in backend.agent_2_validate_stimulus_individual(client, {}, 'design', {'ok': {'type': 'boolean'}})
    client.generate_completion.return_value = {'quality': 99}
    assert backend.agent_3_score_stimulus_individual(client, {}, 'design', {'quality': {'minimum': 1, 'maximum': 7}}) == {'quality': None}


def test_http_generate_status_download_and_websocket(client, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    model = Mock()
    model.get_default_params.return_value = {'model': 'gpt-4o'}
    model.generate_completion.side_effect = [{'text': 'hello'}, {'ok': True}, {'quality': 6}]
    monkeypatch.setattr(backend, 'create_model_client', lambda *a: model)
    ws = web.socketio.test_client(web.app)
    ws.emit('join_session', {'session_id': 'integration'})
    response = client.post('/integration/generate_stimulus', json={
        'iteration': 1, 'experimentDesign': 'design', 'modelChoice': 'GPT-4o',
        'agent1Properties': json.dumps({'text': {'type': 'string'}}),
        'agent2Properties': json.dumps({'ok': {'type': 'boolean'}}),
        'agent3Properties': json.dumps({'quality': {'type': 'integer', 'minimum': 1, 'maximum': 7}})})
    assert response.status_code == 200
    web.active_sessions['integration']['generation_thread'].join(5)
    assert not web.active_sessions['integration']['generation_thread'].is_alive()
    status = client.get('/integration/generation_status').get_json()
    assert status['status'] == 'completed'
    download = client.get('/integration/download/' + status['file'])
    assert download.status_code == 200
    assert b'hello' in download.data
    assert any(event['name'] == 'stimulus_update' for event in ws.get_received())
    ws.disconnect()


def test_stop_retains_partial_results(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    config = settings()
    config['iteration'] = 2
    client = Mock()
    client.get_default_params.return_value = {}
    responses = iter([{'text': 'first'}, {'ok': True}, {'quality': 5}, {'text': 'second'}])
    def completion(*args):
        value = next(responses)
        if value == {'text': 'second'}:
            config['stop_event'].set()
        return value
    client.generate_completion.side_effect = completion
    monkeypatch.setattr(backend, 'create_model_client', lambda *a: client)
    df, filename = backend.generate_stimuli(config)
    assert len(df) == 1 and df.loc[0, 'quality'] == 5
    assert df.loc[0, 'stopped_by_user']
    assert '_stopped' in filename


def test_custom_api_payload_and_response(monkeypatch):
    response = {'choices': [{'message': {'content': '{"ok": true}'}}]}
    post = Mock(return_value=response)
    monkeypatch.setattr(backend, 'post_public_json', post)
    monkeypatch.setattr(backend, 'call_with_timeout', lambda func, args, kwargs, timeout: func(*args, **kwargs))
    client = backend.CustomModelClient('https://example.com/chat', 'dummy', 'custom-model')
    assert client.generate_completion('prompt', {'ok': {'type': 'boolean'}}, {'temperature': 0}) == {'ok': True}
    url, headers, payload = post.call_args.args
    assert url == 'https://example.com/chat'
    assert headers['Authorization'] == 'Bearer dummy'
    assert payload['model'] == 'custom-model' and payload['temperature'] == 0


def test_empty_worker_queue(monkeypatch):
    import queue
    result_queue = Mock()
    result_queue.get.side_effect = queue.Empty
    process = Mock()
    process.is_alive.return_value = False
    monkeypatch.setattr(backend, 'Queue', lambda: result_queue)
    monkeypatch.setattr(backend, 'Process', lambda **kwargs: process)
    assert 'no result' in backend.call_with_timeout(None, (), {}, 1)['error']
    result_queue.close.assert_called_once()


@pytest.mark.parametrize('url,expected', [
    ('https://api.openai.com/v1/chat/completions', 'json_schema'),
    ('https://api.deepseek.com/chat/completions', 'json_object'),
    ('https://openrouter.ai/api/v1/chat/completions', 'json_object'),
    ('https://example.com/v1/chat/completions', 'json_object'),
    ('https://api.openai.com.example.com/chat/completions', 'json_object'),
])
@pytest.mark.parametrize('prompt,properties,instruction', [
    ('Generate one item', {'Text': {'type': 'string'}}, 'field types'),
    ('Evaluate the following stimulus', {'Valid': {'type': 'boolean'}}, 'JSON booleans'),
    ('Rate the following stimulus', {'Fluency': {'type': 'integer', 'minimum': 0, 'maximum': 10}}, 'inclusive ranges'),
])
def test_response_format_matches_provider(monkeypatch, url, expected, prompt, properties, instruction):
    post = Mock(return_value={'choices': [{'message': {'content': '{}'}}]})
    monkeypatch.setattr(backend, 'post_public_json', post)
    monkeypatch.setattr(backend, 'call_with_timeout', lambda func, args, kwargs, timeout: func(*args, **kwargs))
    backend.CustomModelClient(url, 'dummy', 'test-model').generate_completion(prompt, properties, {'max_tokens': 2000, 'temperature': 0.7})
    payload = post.call_args.args[2]
    assert payload['response_format']['type'] == expected
    assert payload['max_tokens'] == 2000
    assert payload['temperature'] == 0.7
    if expected == 'json_object':
        message = payload['messages'][-1]['content']
        assert json.dumps(properties, ensure_ascii=False) in message
        assert instruction in message
        assert 'exactly these fields' in message
    else:
        assert payload['response_format']['json_schema']['schema']['properties'] == properties


def test_existing_repetition_rule_is_preserved():
    assert backend.check_stimulus_repetition({'text': 'new', 'condition': 'A'}, [{'text': 'old', 'condition': 'A'}])
    assert not backend.check_stimulus_repetition({'text': 'new'}, [{'text': 'old'}])


@pytest.mark.parametrize('url,model,params,effort_key', [
    ('https://api.openai.com/v1/chat/completions', 'gpt-5.4', {'temperature': 0}, 'reasoning_effort'),
    ('https://openrouter.ai/api/v1/chat/completions', 'openai/gpt-5.4', {'temperature': 0}, 'reasoning'),
    ('https://api.openai.com/v1/chat/completions', 'gpt-5.4', {'temperature': 0, 'reasoning_effort': 'high'}, 'reasoning_effort'),
    ('https://openrouter.ai/api/v1/chat/completions', 'openai/gpt-5.4', {'temperature': 0, 'reasoning': {'effort': 'high'}}, 'reasoning'),
])
def test_gpt54_sampling_compatibility(monkeypatch, url, model, params, effort_key):
    post = Mock(return_value={'choices': [{'message': {'content': '{"ok": true}'}}]})
    monkeypatch.setattr(backend, 'post_public_json', post)
    monkeypatch.setattr(backend, 'call_with_timeout', lambda func, args, kwargs, timeout: func(*args, **kwargs))
    assert backend.CustomModelClient(url, 'dummy', model).generate_completion('prompt', {}, params) == {'ok': True}
    payload = post.call_args.args[2]
    effort = payload[effort_key]
    effort = effort['effort'] if isinstance(effort, dict) else effort
    assert effort == ('high' if 'reasoning' in params or 'reasoning_effort' in params else 'none')
    assert ('temperature' in payload) == (effort == 'none')


def test_packaged_web_assets(client):
    response = client.get('/package-smoke')
    assert response.status_code == 200
    assert b'google/gemma-4-31b-it:free' in response.data
    assert b'component-example-table' in response.data
    assert client.get('/static/script.js').status_code == 200
    assert client.get('/static/styles.css').status_code == 200


@pytest.mark.parametrize('url,model,token_key', [
    ('https://api.openai.com/v1/chat/completions', 'gpt-5.4', 'max_completion_tokens'),
    ('https://openrouter.ai/api/v1/chat/completions', 'openai/gpt-5.4', 'max_tokens'),
])
def test_prefilled_params_work_with_reference_models(monkeypatch, url, model, token_key):
    post = Mock(return_value={'choices': [{'message': {'content': '{"text": "item"}'}}]})
    monkeypatch.setattr(backend, 'post_public_json', post)
    monkeypatch.setattr(backend, 'call_with_timeout', lambda func, args, kwargs, timeout: func(*args, **kwargs))
    params = {'max_tokens': 2000, 'temperature': 0.7}
    backend.CustomModelClient(url, 'dummy', model).generate_completion('prompt', {}, params)
    payload = post.call_args.args[2]
    assert payload[token_key] == 2000
    assert payload['temperature'] == 0.7
    if token_key == 'max_completion_tokens':
        assert 'max_tokens' not in payload
    assert params == {'max_tokens': 2000, 'temperature': 0.7}



def test_dimension_heavy_websocket_output_stays_parseable(client):
    ws = web.socketio.test_client(web.app)
    ws.emit('join_session', {'session_id': 'many-dimensions'})
    ws.get_received()
    dimensions = {f'Validation criterion {i}': True for i in range(80)}
    message = "Validator's Output: " + json.dumps(dimensions)
    assert len(message) > 1000
    web.websocket_send('many-dimensions', 'validator', message)
    events = [event for event in ws.get_received() if event['name'] == 'stimulus_update']
    assert events[0]['args'][0]['message'] == message
    ws.disconnect()


def test_json_object_property_drafting_preserves_requested_structure(monkeypatch):
    post = Mock(return_value={'choices': [{'message': {'content': '{"criteria": {"Valid": "Requirement"}}'}}]})
    monkeypatch.setattr(backend, 'post_public_json', post)
    monkeypatch.setattr(backend, 'call_with_timeout', lambda func, args, kwargs, timeout: func(*args, **kwargs))
    client = backend.CustomModelClient('https://openrouter.ai/api/v1/chat/completions', 'dummy', 'test-model')
    result = client.generate_completion('Draft criteria and aspects as JSON', {})
    message = post.call_args.args[2]['messages'][-1]['content']
    assert 'exactly these fields' not in message
    assert 'structure requested above' in message
    assert result['criteria']['Valid'] == 'Requirement'
