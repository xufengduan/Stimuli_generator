const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const source = fs.readFileSync('static/script.js', 'utf8');
const context = {};
vm.createContext(context);
for (const name of ['escapeLogHtml', 'formatJsonHorizontal', 'parseLogEntry', 'createLogNode', 'getAgentLogState', 'getLogItemIds', 'getLogRecordStatus', 'logRecordMatches', 'createTimelineRecord']) {
  const start = source.indexOf(`function ${name}(`);
  const end = source.indexOf('\n}', start) + 2;
  vm.runInContext(source.slice(start, end), context);
}
const payload = '<img src=x onerror="alert(1)">';
for (const input of [JSON.stringify({[payload]: payload, nested: {value: payload}}), payload]) {
  const output = context.formatJsonHorizontal(input);
  assert(!output.includes('<img'));
  assert(output.includes('&lt;img'));
}
// Minimal DOM: model text must be represented as text nodes, never HTML.
class Element {
  constructor(tag) {
    this.tag = tag; this.children = []; this.textContent = ''; this.scrollTop = 0;
    this.scrollHeight = 0; this.clientHeight = 0;
    this.classList = {add: (...names) => { this.className += ' ' + names.join(' '); }};
  }
  append(...children) { this.children.push(...children); }
  setAttribute(name, value) { this[name] = value; }
}
context.document = {createElement: tag => new Element(tag)};
const render = (message, ranges = {}, raw = false) => context.createTimelineRecord({entry: context.parseLogEntry(message), item: 10, timestamp: '2026-11-17T09:00:00Z', ranges}, 'generator-log', raw);
assert.equal(context.parseLogEntry('=== No. 10 Round ===').round, '10');
assert.equal(context.parseLogEntry("Generator's Output: " + JSON.stringify({text: 'The experiment failed.'})).kind, 'output');
assert.equal(context.parseLogEntry("Generator's Output: {broken [truncated]").kind, 'message');
assert.equal(context.parseLogEntry('Failed validation, regenerating...').status, 'warning');
assert.equal(context.parseLogEntry('Generation completed.', 'error').status, 'error');
const output = render("Generator's Output: " + JSON.stringify({[payload]: payload, text: 'Includes Output: inside the sentence'}));
const fields = output.children[2].children[1];
assert.equal(fields.children[0].children[0].textContent, payload);
assert.equal(fields.children[0].children[1].textContent, payload);
assert.equal(fields.children[1].children[1].textContent, 'Includes Output: inside the sentence');
const validationEntry = context.parseLogEntry("Validator's Output: " + JSON.stringify({valid: false}));
assert.equal(context.getLogRecordStatus({entry: validationEntry}), 'warning');
const verdict = render(validationEntry.text);
assert.equal(verdict.children[2].children[1].children[0].children[0]['aria-label'], 'Not passed');
const scoreText = "Scorer's Output: " + JSON.stringify({quality: 0, missing: null, unknownScale: 5});
const scores = render(scoreText, {quality: {min: 0, max: 7}}).children[2].children[1];
assert.equal(scores.children[0].children[1].textContent, '0');
assert.equal(scores.children[0].children[1].children[0].textContent, ' /7');
assert.equal(scores.children[1].children[1].textContent, 'Not available');
assert.equal(scores.children[2].children[1].children.length, 0, 'Never invent a scale maximum');
const raw = render(scoreText, {}, true);
assert.equal(raw.children[2].children[0].textContent, scoreText);
const record = {entry: validationEntry, item: 10};
assert.equal(context.logRecordMatches(record, '1', 'all'), false);
assert.equal(context.logRecordMatches(record, '10', 'warnings'), true);
assert.equal(context.logRecordMatches(record, '10', 'outputs'), true);
assert.equal(context.logRecordMatches(record, '10', 'errors'), false);
assert.equal(context.logRecordMatches({entry: context.parseLogEntry('API error'), item: null}, '10', 'errors'), true);
context.getAgentLogState().records = {'generator-log': [{item: 10}, {item: 2}, {item: null}], 'validator-log': [{item: 2}]};
assert.deepEqual(Array.from(context.getLogItemIds()), [2, 10]);
console.log('Frontend checks passed: safe timelines, filtering, item IDs, raw messages, verdicts and real score ranges');
