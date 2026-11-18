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

for (const name of ['exampleRows', 'collectExampleStimuli', 'collectItemsData', 'collectGeneratorConfiguration', 'validateExampleItems']) {
  const start = source.indexOf(`function ${name}(`);
  const end = source.indexOf('\n}', start) + 2;
  vm.runInContext(source.slice(start, end), context);
}
const exampleRow = (name, value) => ({querySelector: selector => ({value: selector === '.example-name' ? name : value, focus() {}})});
const exampleItem = (elements, conditions) => ({querySelectorAll: selector => selector.includes('"element"') ? elements : conditions});
context.alert = () => {};
context.itemsContainer = {
  children: [
    exampleItem([exampleRow('目标词', '花园'), exampleRow('', '')], [exampleRow('条件甲', '她走进花园。'), exampleRow('条件乙', '花园里开满了花。')]),
    exampleItem([exampleRow('目标词', '学校'), exampleRow('', '')], [exampleRow('条件甲', '他走进学校。'), exampleRow('条件乙', '学校里有很多学生。')])
  ],
  get firstElementChild() { return this.children[0]; }
};
assert.equal(context.validateExampleItems(), true);
const examples = JSON.parse(JSON.stringify(context.collectItemsData()));
assert.deepEqual(Object.keys(examples[0]), ['目标词', '条件甲', '条件乙']);
assert.equal(examples[1]['目标词'], '学校');
const configuration = context.collectGeneratorConfiguration();
assert.deepEqual(Object.keys(configuration.properties), ['目标词', '条件甲', '条件乙']);
assert.deepEqual(Array.from(configuration.avoidDuplicationFields), ['目标词']);
assert(configuration.properties['目标词'].description.includes('unique'));
context.itemsContainer.children = [
  exampleItem([exampleRow('目标词', '花园')], [exampleRow('条件甲', '第一份')]),
  exampleItem([exampleRow('名字', '小乙')], [exampleRow('条件乙', '第二份')])
];
assert.equal(context.validateExampleItems(), true);
const independentConfiguration = context.collectGeneratorConfiguration();
assert.deepEqual(Object.keys(independentConfiguration.properties), ['目标词', '名字', '条件甲', '条件乙']);
assert.deepEqual(Array.from(independentConfiguration.avoidDuplicationFields), ['目标词', '名字']);
assert.deepEqual(Object.keys(context.collectItemsData()[0]), ['目标词', '条件甲']);
assert.deepEqual(Object.keys(context.collectItemsData()[1]), ['名字', '条件乙']);
context.itemsContainer.children = [exampleItem([], [exampleRow('__proto__', 'Chinese 中文')])];
assert.equal(context.validateExampleItems(), true);
assert.equal(Object.hasOwn(context.collectItemsData()[0], '__proto__'), true);
context.itemsContainer.children = [exampleItem([exampleRow('same', 'value')], [exampleRow('same', 'sentence')])];
assert.equal(context.validateExampleItems(), false, 'Do not silently overwrite a condition with an element');
context.itemsContainer.children = [exampleItem([exampleRow('目标词', '')], [exampleRow('条件', '内容')])];
assert.equal(context.validateExampleItems(), false, 'An optional element must be complete when used');
console.log('Example checks passed: element order, per-item values, optional rows, schema, duplicate names and safe keys');
