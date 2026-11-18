import io
import json
from unittest.mock import Mock

import pandas as pd
import pytest

from stimulus_generator import app as web
from stimulus_generator import backend
from stimulus_generator.csv_export import build_export_frames, export_csv_bytes, raw_csv_bytes, read_archived_csv


def test_wide_uses_names_and_schema_order_instead_of_json_position():
    data = pd.DataFrame([
        {'stimulus_id': 1, 'stimulus_content': {'Passive': '句子乙', 'Active': '句子甲', 'Verb': '读'},
         'scores': {'Fluency': 0}, 'validation_results': {'Valid': True}},
        {'stimulus_id': 2, 'stimulus_content': {'Verb': '写', 'Active': '第二句甲', 'Passive': '第二句乙'},
         'scores': {'Fluency': None}, 'validation_results': {'Valid': True}}
    ])
    config = {'element_fields': ['Verb'], 'stimulus_fields': ['Verb', 'Active', 'Passive'],
              'score_fields': ['Fluency'], 'validation_fields': ['Valid']}
    wide, detail = build_export_frames(data, config)
    assert list(wide) == ['item_id', 'Verb', 'Active', 'Passive', 'score_Fluency', 'scoring_status']
    assert wide['Active'].tolist() == ['句子甲', '第二句甲']
    assert wide.loc[0, 'score_Fluency'] == 0
    assert pd.isna(wide.loc[1, 'score_Fluency'])
    assert wide['scoring_status'].tolist() == ['complete', 'failed']
    assert detail['validation_Valid'].tolist() == [True, True]
    assert detail['validation_status'].tolist() == ['passed', 'passed']
    assert 'validation_failure_reasons' not in detail


@pytest.mark.parametrize('scores,expected', [({}, 'failed'), ({'A': None, 'B': None}, 'failed'),
    ({'A': 0, 'B': None}, 'partial'), ({'A': 0, 'B': 7}, 'complete')])
def test_rating_status_and_blanks(scores, expected):
    wide, _ = build_export_frames(pd.DataFrame([{'stimulus_content': {'text': 'test'}, 'scores': scores}]),
                                  {'score_fields': ['A', 'B']})
    assert wide.loc[0, 'scoring_status'] == expected
    if 'A' in scores and scores['A'] == 0:
        assert wide.loc[0, 'score_A'] == 0
    assert pd.isna(wide.loc[0, 'score_B']) == (scores.get('B') is None)


def test_unrated_export_and_colliding_user_labels_keep_every_value():
    row = {'stimulus_content': {'item_id': 'material id', 'scoring_status': 'material status',
                               'score_Q': 'sentence', 'validation_status': 'original label'},
           'scores': {'Q': 3}, 'validation_results': {'status': True}}
    wide, detail = build_export_frames(pd.DataFrame([row]))
    assert detail.columns.is_unique
    assert wide.loc[0, 'item_id'] == 1
    assert wide.loc[0, 'stimulus_item_id'] == 'material id'
    assert wide.loc[0, 'stimulus_scoring_status'] == 'material status'
    assert wide.loc[0, 'score_Q'] == 'sentence'
    assert wide.loc[0, 'score_Q_rating'] == 3
    assert detail.loc[0, 'validation_status'] == 'original label'
    assert detail.loc[0, 'diagnostic_validation_status'] == 'passed'
    assert detail.loc[0, 'validation_result_status'] == True
    unrated, _ = build_export_frames(pd.DataFrame([{'stimulus_content': {'text': 'NA'}}]))
    assert unrated.loc[0, 'scoring_status'] == 'not_requested'


def test_unicode_quotes_newlines_and_na_survive_raw_restore_and_bom():
    text = '中文，繁體「引號」,"quoted"\n第二行'
    data = pd.DataFrame([{'stimulus_id': 7, 'stimulus_content': {'条件': text, '目标': 'NA'},
                          'scores': {'自然度': 0}, 'validation_results': {'正确': True}}])
    restored = read_archived_csv(raw_csv_bytes(data))
    encoded = export_csv_bytes(restored, detailed=True)
    assert encoded.startswith(b'\xef\xbb\xbf')
    result = pd.read_csv(io.BytesIO(encoded), keep_default_na=False)
    assert result.loc[0, '条件'] == text
    assert result.loc[0, '目标'] == 'NA'
    assert result.loc[0, 'score_自然度'] == 0


def test_old_key_content_archives_convert_without_losing_diagnostics():
    legacy = pd.DataFrame([{'stimulus_id': 1, 'Key1': 'Verb', 'Content1': 'eat',
        'Key2': 'Active', 'Content2': 'A sentence.', 'Fluency': 0,
        'validation_failure_reasons': "{'Valid': True}", 'repetition_count': 3, 'validation_fails': 2}])
    restored = read_archived_csv(legacy.to_csv(index=False).encode())
    wide, detail = build_export_frames(restored)
    assert wide.loc[0, 'Verb'] == 'eat'
    assert wide.loc[0, 'Active'] == 'A sentence.'
    assert wide.loc[0, 'score_Fluency'] == 0
    assert detail.loc[0, 'cumulative_repetition_retries'] == 3
    assert pd.isna(detail.loc[0, 'repetition_retries'])
    assert detail.loc[0, 'validation_Valid'] == True


def test_http_two_variants_upgrade_old_history_and_survive_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'SESSION_DIR', str(tmp_path))
    web.active_sessions.clear()
    state = web.load_session('old')
    state['generation_history'] = [{'filename': 'old.csv', 'created_at': 1794974400,
                                    'rows': 1, 'partial': True}]
    directory = tmp_path / 'old'
    directory.mkdir()
    (directory / 'old.csv').write_text('stimulus_id,Key1,Content1,Fluency\n1,text,中文,0\n')
    web.save_session('old', state)
    web.active_sessions.clear()
    client = web.app.test_client()
    history = client.get('/old/generation_history').get_json()['history'][0]
    assert history['download_name'].startswith('StimMAS_2026-11-18_')
    assert history['download_name'].endswith('_1items_partial.csv')
    assert history['detailed_download_name'].endswith('_partial_detailed.csv')
    for variant in ['wide', 'detailed']:
        response = client.get('/old/download/old.csv?variant=' + variant)
        assert response.status_code == 200 and response.data.startswith(b'\xef\xbb\xbf')
        frame = pd.read_csv(io.BytesIO(response.data))
        assert frame.loc[0, 'text'] == '中文'
        assert frame.loc[0, 'score_Fluency'] == 0
        assert ('validation_status' in frame) == (variant == 'detailed')
        assert 'StimMAS_' in response.headers['Content-Disposition']
    assert client.get('/old/download/old.csv?variant=raw').status_code == 400
    assert client.get('/other/download/old.csv?variant=detailed').status_code == 404


def test_retries_are_per_item_and_cumulative(monkeypatch):
    from test_regressions import settings
    config = settings()
    config['iteration'] = 2
    config['previous_stimuli'] = [{'text': 'repeated'}]
    model = Mock()
    model.get_default_params.return_value = {}
    model.generate_completion.side_effect = [
        {'text': 'repeated'}, {'text': 'bad'}, {'ok': False},
        {'text': 'first'}, {'ok': True}, {'quality': 6},
        {'text': 'second'}, {'ok': True}, {'quality': 5}]
    monkeypatch.setattr(backend, 'create_model_client', lambda *args: model)
    dataframe, _ = backend.generate_stimuli(config)
    _, detailed = build_export_frames(dataframe)
    assert detailed['generation_attempts'].tolist() == [3, 1]
    assert detailed['repetition_retries'].tolist() == [1, 0]
    assert detailed['validation_retries'].tolist() == [1, 0]
    assert detailed['cumulative_repetition_retries'].tolist() == [1, 1]
    assert detailed['cumulative_validation_retries'].tolist() == [1, 1]
