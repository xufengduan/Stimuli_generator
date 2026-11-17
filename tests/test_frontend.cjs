const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const source = fs.readFileSync('static/script.js', 'utf8');
const context = {};
vm.createContext(context);
for (const name of ['escapeLogHtml', 'formatJsonHorizontal']) {
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
assert(source.includes('${escapeLogHtml(message)}'));
console.log('Frontend HTML escaping regression checks passed');
