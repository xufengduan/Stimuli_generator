import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { serializeParameters } from './parameters.mjs';

function rowsFromJSON(json, makeId) {
    try {
        const parameters = JSON.parse(json || '{}');
        if (!parameters || Array.isArray(parameters) || typeof parameters !== 'object') return [];
        return Object.entries(parameters).map(([name, value]) => ({
            id: makeId(), name,
            type: typeof value === 'number' ? 'number' : typeof value === 'boolean' ? 'boolean' : typeof value === 'string' ? 'string' : 'json',
            value: typeof value === 'object' ? JSON.stringify(value) : String(value)
        }));
    } catch { return []; }
}

export function AdvancedParameters() {
    const nextId = useRef(0);
    const makeId = () => `api-parameter-${nextId.current++}`;
    const [rows, setRows] = useState(() => rowsFromJSON(document.getElementById('custom_params').value, makeId));
    const [disabled, setDisabled] = useState(() => Boolean(document.getElementById('model_choice').disabled));
    const result = serializeParameters(rows);

    useLayoutEffect(() => {
        const field = document.getElementById('custom_params');
        field.value = result.json;
        field.dataset.error = result.error;
    }, [result.json, result.error]);

    useEffect(() => {
        const reset = () => setRows(rowsFromJSON(document.getElementById('custom_params').defaultValue, makeId));
        const changeDisabled = event => setDisabled(event.detail.disabled);
        window.addEventListener('stimmas:parameters-reset', reset);
        window.addEventListener('stimmas:controls-disabled', changeDisabled);
        return () => {
            window.removeEventListener('stimmas:parameters-reset', reset);
            window.removeEventListener('stimmas:controls-disabled', changeDisabled);
        };
    }, []);

    const update = (id, key, value) => setRows(current => current.map(row => {
        if (row.id !== id) return row;
        if (key === 'type' && value === 'boolean') return { ...row, type: value, value: row.value === 'true' ? 'true' : 'false' };
        if (key === 'type' && value === 'json' && !row.value) return { ...row, type: value, value: '{}' };
        return { ...row, [key]: value };
    }));

    return (
        <div className="parameters-editor" role="group" aria-label="Advanced API parameters">
            <div className="parameter-grid-heading" aria-hidden="true"><span>Parameter</span><span>Type</span><span>Value</span><span /></div>
            <div className="parameter-rows">
                {rows.map((row, index) => {
                    const invalid = result.invalidRow === index;
                    const inputId = row.id;
                    return <div className={`parameter-row${invalid ? ' is-invalid' : ''}`} key={row.id}>
                        <label className="parameter-name"><span>Parameter</span>
                            <input id={`${inputId}-name`} type="text" value={row.name} aria-label={`Parameter ${index + 1} name`}
                                aria-invalid={invalid || undefined} aria-describedby={invalid ? 'parameter-error' : undefined}
                                spellCheck="false" autoComplete="off" disabled={disabled} data-parameter-control="true"
                                onChange={event => update(row.id, 'name', event.target.value)} />
                        </label>
                        <label className="parameter-type"><span>Type</span>
                            <select value={row.type} aria-label={`Parameter ${index + 1} type`} disabled={disabled} data-parameter-control="true"
                                onChange={event => update(row.id, 'type', event.target.value)}>
                                <option value="number">Number</option><option value="string">Text</option>
                                <option value="boolean">Boolean</option><option value="json">JSON</option>
                            </select>
                        </label>
                        <label className="parameter-value"><span>Value</span>
                            {row.type === 'boolean' ?
                                <select value={row.value} aria-label={`Parameter ${index + 1} value`} disabled={disabled} data-parameter-control="true"
                                    onChange={event => update(row.id, 'value', event.target.value)}>
                                    <option value="true">true</option><option value="false">false</option>
                                </select> :
                                <input type={row.type === 'number' ? 'number' : 'text'} step={row.type === 'number' ? 'any' : undefined}
                                    value={row.value} aria-label={`Parameter ${index + 1} value`}
                                    aria-invalid={invalid || undefined} aria-describedby={invalid ? 'parameter-error' : undefined}
                                    spellCheck="false" autoComplete="off" disabled={disabled} data-parameter-control="true"
                                    onChange={event => update(row.id, 'value', event.target.value)} />}
                        </label>
                        <button type="button" className="remove-parameter" aria-label={`Remove parameter ${index + 1}`} disabled={disabled} data-parameter-control="true"
                            onClick={() => setRows(current => current.filter(parameter => parameter.id !== row.id))}>
                            <i className="far fa-trash-can" aria-hidden="true" />
                        </button>
                    </div>;
                })}
            </div>
            {result.error && <p className="parameter-error" id="parameter-error" role="alert">{result.error}</p>}
            <div className="parameter-actions">
                <button type="button" className="add-parameter" disabled={disabled} data-parameter-control="true"
                    onClick={() => setRows(current => [...current, { id: makeId(), name: '', type: 'number', value: '' }])}>
                    <span aria-hidden="true">+</span> Add parameter
                </button>
                <span className="parameter-note">Parameters are converted to JSON automatically.</span>
            </div>
            <details className="parameter-preview"><summary>JSON preview</summary>
                <pre>{result.json ? JSON.stringify(JSON.parse(result.json), null, 2) : 'Complete the parameter fields to preview JSON.'}</pre>
            </details>
        </div>
    );
}
