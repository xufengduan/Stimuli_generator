export function serializeParameters(rows) {
    const parameters = Object.create(null);
    for (let index = 0; index < rows.length; index++) {
        const row = rows[index];
        const name = row.name.trim();
        const text = String(row.value);
        const fail = message => ({ json: '', error: message, invalidRow: index });
        if (!name && !text) continue;
        if (!name) return fail('Enter a parameter name for each value.');
        if (Object.prototype.hasOwnProperty.call(parameters, name)) return fail(`Parameter “${name}” is listed more than once.`);
        let value;
        if (row.type === 'number') {
            if (!text.trim() || !Number.isFinite(Number(text))) return fail(`Enter a valid number for “${name}”.`);
            value = Number(text);
        } else if (row.type === 'boolean') {
            if (text !== 'true' && text !== 'false') return fail(`Choose true or false for “${name}”.`);
            value = text === 'true';
        } else if (row.type === 'json') {
            try { value = JSON.parse(text); }
            catch { return fail(`Enter valid JSON for “${name}”.`); }
        } else if (row.type === 'string') {
            value = text;
        } else {
            return fail(`Choose a supported value type for “${name}”.`);
        }
        parameters[name] = value;
    }
    return { json: JSON.stringify(parameters), error: '', invalidRow: -1 };
}
