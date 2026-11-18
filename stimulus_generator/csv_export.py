"""User-facing wide CSVs and optional generation diagnostics."""
import ast
import io
import json
import math
from datetime import datetime, timedelta, timezone

import pandas as pd

EXPORT_VERSION = 2
DIAGNOSTIC_COLUMNS = {
    'stimulus_id', 'item_id', 'stimulus_content', 'scores', 'scoring_status',
    'scoring_error', 'validation_results', 'validation_failure_reasons',
    'validation_status', 'repetition_count', 'validation_fails',
    'generation_attempts', 'repetition_retries', 'validation_retries',
    'cumulative_repetition_retries', 'cumulative_validation_retries',
    'generation_timestamp', 'batch_id', 'total_iterations', 'download_timestamp',
    'error_occurred', 'error_message', 'stopped_by_user', 'message',
    'completed_iterations',
}


def parse_object(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            try:
                parsed = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def is_missing(value):
    return value is None or value == '' or (isinstance(value, float) and math.isnan(value))


def ordered_unique(values):
    return list(dict.fromkeys(values))


def raw_csv_bytes(dataframe):
    persisted = dataframe.copy()
    for column in persisted.columns:
        persisted[column] = persisted[column].map(
            lambda value: json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value)
    return persisted.to_csv(index=False).encode('utf-8-sig')


def read_archived_csv(content):
    """Read raw batches and the paired Key/Content exports from older versions."""
    dataframe = pd.read_csv(io.BytesIO(content), keep_default_na=False)
    if 'stimulus_content' not in dataframe:
        pairs = [column for column in dataframe.columns
                 if column.startswith('Key') and column[3:].isdigit()
                 and 'Content' + column[3:] in dataframe]
        if pairs:
            dataframe['stimulus_content'] = [
                {row[key]: row['Content' + key[3:]] for key in pairs if row[key] != ''}
                for row in dataframe.to_dict('records')]
            dataframe = dataframe.drop(columns=pairs + ['Content' + key[3:] for key in pairs])
    return dataframe


def download_names(created_at, row_count, partial=False):
    # CUHK's local time makes the filenames match dates shown to the project owner.
    date = datetime.fromtimestamp(created_at, timezone(timedelta(hours=8)))
    base = f"StimMAS_{date:%Y-%m-%d_%H%M%S}_{row_count}items"
    if partial:
        base += '_partial'
    return base + '.csv', base + '_detailed.csv'


def build_export_frames(dataframe, config=None):
    """Match values by field name, never by the model's JSON key order."""
    config = config or {}
    records = dataframe.to_dict('records')
    stimuli = [parse_object(row.get('stimulus_content')) for row in records]
    materials = ordered_unique(config.get('element_fields', []) + config.get('stimulus_fields', [])
                               + [key for item in stimuli for key in item])
    score_fields = ordered_unique(config.get('score_fields', []) + [
        key for row in records for key in parse_object(row.get('scores'))])
    if 'scores' not in dataframe:
        score_fields = ordered_unique(score_fields + [
            column for column in dataframe.columns if column not in DIAGNOSTIC_COLUMNS])
    validations = [parse_object(row.get('validation_results', row.get('validation_failure_reasons')))
                   for row in records]
    validation_fields = ordered_unique(config.get('validation_fields', []) + [
        key for result in validations for key in result if key != 'error'])

    # User labels may match metadata or prefixed score names. Never overwrite a column.
    used = {'item_id', 'scoring_status'}
    def column_name(preferred, fallback):
        name = preferred if preferred not in used else fallback
        original = name
        index = 2
        while name in used:
            name = f'{original}_{index}'
            index += 1
        used.add(name)
        return name
    material_names = {key: column_name(key, 'stimulus_' + key) for key in materials}
    score_names = {key: column_name('score_' + key, 'score_' + key + '_rating') for key in score_fields}
    # Diagnostic names must also stay distinct from all user labels.
    detail_fields = ['validation_status'] + [
        'generation_attempts', 'repetition_retries', 'validation_retries',
        'cumulative_repetition_retries', 'cumulative_validation_retries',
        'scoring_error', 'validation_error', 'generated_at_utc', 'batch_id',
        'requested_items', 'completed_items', 'stopped_by_user', 'generation_error', 'generation_message']
    detail_names = {key: column_name(key, 'diagnostic_' + key) for key in detail_fields}
    validation_names = {key: column_name('validation_' + key, 'validation_result_' + key)
                        for key in validation_fields}

    wide_rows, detailed_rows = [], []
    for index, (row, stimulus, validation) in enumerate(zip(records, stimuli, validations), 1):
        wide = {'item_id': row.get('stimulus_id', row.get('item_id', index))}
        wide.update({material_names[key]: stimulus.get(key, '') for key in materials})
        source_scores = parse_object(row.get('scores')) if 'scores' in dataframe else row
        available = 0
        for key in score_fields:
            value = source_scores.get(key)
            # Pandas may restore old numeric scores as strings; keep actual zero.
            if isinstance(value, str) and value.strip():
                try:
                    value = float(value)
                except ValueError:
                    value = None
            valid = type(value) in (int, float) and math.isfinite(value)
            wide[score_names[key]] = value if valid else None
            available += bool(valid)
        wide['scoring_status'] = ('not_requested' if not score_fields else
                                  'complete' if available == len(score_fields) else
                                  'partial' if available else 'failed')
        wide_rows.append(wide)
        validation_status = ('error' if 'error' in validation else
                             'not_run' if not validation_fields else
                             'passed' if all(validation.get(key) is True for key in validation_fields) else
                             'failed' if any(validation.get(key) is False for key in validation_fields) else 'incomplete')
        details = {'validation_status': validation_status}
        for key in ['generation_attempts', 'repetition_retries', 'validation_retries']:
            details[key] = row.get(key)
        details['cumulative_repetition_retries'] = row.get('cumulative_repetition_retries', row.get('repetition_count'))
        details['cumulative_validation_retries'] = row.get('cumulative_validation_retries', row.get('validation_fails'))
        timestamp = row.get('generation_timestamp')
        details['generated_at_utc'] = (datetime.fromtimestamp(float(timestamp), timezone.utc).isoformat()
                                       if not is_missing(timestamp) else '')
        details.update({
            'scoring_error': row.get('scoring_error', ''), 'validation_error': validation.get('error', ''),
            'batch_id': row.get('batch_id', ''), 'requested_items': row.get('total_iterations'),
            'completed_items': row.get('completed_iterations', len(records)),
            'stopped_by_user': row.get('stopped_by_user', False),
            'generation_error': row.get('error_message', ''), 'generation_message': row.get('message', '')})
        detailed_rows.append({**wide,
                              **{detail_names[key]: value for key, value in details.items()},
                              **{validation_names[key]: validation.get(key) for key in validation_fields}})
    wide_columns = ['item_id'] + list(material_names.values()) + list(score_names.values()) + ['scoring_status']
    return (pd.DataFrame(wide_rows, columns=wide_columns, dtype=object),
            pd.DataFrame(detailed_rows, columns=wide_columns + [detail_names['validation_status']]
                         + list(validation_names.values()) + [detail_names[key] for key in detail_fields[1:]], dtype=object))


def export_csv_bytes(dataframe, config=None, detailed=False):
    frames = build_export_frames(dataframe, config)
    return frames[bool(detailed)].to_csv(index=False).encode('utf-8-sig')
