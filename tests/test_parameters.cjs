const assert = require('node:assert/strict');

(async () => {
    const { serializeParameters } = await import('../frontend/parameters.mjs');
    const rows = [
        { name: 'max_tokens', type: 'number', value: '2000' },
        { name: 'temperature', type: 'number', value: '0' },
        { name: 'stream', type: 'boolean', value: 'false' },
        { name: 'label', type: 'string', value: '' },
        { name: 'stop', type: 'json', value: '["END", "STOP"]' },
        { name: 'response_format', type: 'json', value: '{"type":"json_object"}' },
        { name: 'nullable', type: 'json', value: 'null' }
    ];
    const result = serializeParameters(rows);
    assert.equal(result.error, '');
    assert.deepEqual(JSON.parse(result.json), {
        max_tokens: 2000, temperature: 0, stream: false, label: '',
        stop: ['END', 'STOP'], response_format: { type: 'json_object' }, nullable: null
    });
    assert.equal(serializeParameters([]).json, '{}');
    assert.equal(serializeParameters([{ name: '', type: 'number', value: '' }]).json, '{}');
    assert.equal(serializeParameters([{ name: '  seed  ', type: 'number', value: '0' }]).json, '{"seed":0}');
    for (const row of [
        { name: 'temperature', type: 'number', value: '' },
        { name: 'temperature', type: 'number', value: 'Infinity' },
        { name: 'temperature', type: 'number', value: 'NaN' },
        { name: '', type: 'string', value: 'missing name' },
        { name: 'stop', type: 'json', value: '[broken' },
        { name: 'stream', type: 'boolean', value: 'not-a-boolean' }
    ]) {
        const invalid = serializeParameters([row]);
        assert(invalid.error);
        assert.equal(invalid.json, '');
        assert.equal(invalid.invalidRow, 0);
    }
    const duplicate = serializeParameters([{ name: 'seed', type: 'number', value: '0' }, { name: ' seed ', type: 'number', value: '1' }]);
    assert(duplicate.error.includes('more than once'));
    assert.equal(duplicate.json, '');
    const special = serializeParameters([{ name: '__proto__', type: 'json', value: '{"enabled":true}' }]);
    assert(Object.hasOwn(JSON.parse(special.json), '__proto__'));
    assert.equal({}.enabled, undefined);
    console.log('Parameter form checks passed: typed JSON, zero/false, empty rows, invalid input, duplicates and safe keys');
})().catch(error => { console.error(error); process.exitCode = 1; });
