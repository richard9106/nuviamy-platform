const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function element(extra = {}) { return { hidden: false, textContent: '', attrs: {}, events: {}, dataset: {},
  classList: {values: new Set(), toggle(name, on) { on ? this.values.add(name) : this.values.delete(name); }},
  addEventListener(name, fn) { this.events[name] = fn; }, setAttribute(key, value) { this.attrs[key] = value; }, ...extra }; }
const controls = ['first', 'confirm'].map(id => {
  const input = element({id, type: 'password', value: '', dataset: {passwordMinimum: '8'}});
  const eye = element(), off = element({hidden: true});
  const toggle = element({hidden: true, dataset: {showLabel: 'Show password', hideLabel: 'Hide password'},
    querySelector(s) { return s === '[data-password-eye]' ? eye : off; }});
  return {input, toggle, querySelector(s) {return s === 'input' ? input : toggle;}};
});
const rules = ['length', 'lowercase', 'uppercase', 'number', 'special'].map(rule => {
  const icon = element(), status = element();
  return element({dataset: {passwordRule: rule}, querySelector(s) { return s === '[data-password-rule-icon]' ? icon : status; }});
});
const summary = element();
const panel = element({dataset: {passwordInput: 'first'}, querySelectorAll() {return rules;}, querySelector() {return summary;}});
const pageEvents = {};
const sandbox = {document: {querySelectorAll(s) {return s === '[data-password-control]' ? controls : [panel];},
  getElementById(id) {return controls.find(c => c.input.id === id)?.input;}},
  window: {addEventListener(name, fn) {(pageEvents[name] ||= []).push(fn);}},
  fetch() {throw Error('Passwords must not be transmitted by this script');},
  localStorage: new Proxy({}, {get() {throw Error('Passwords must not be stored');}})};
vm.runInNewContext(fs.readFileSync('static/password-tools.js', 'utf8'), sandbox);
assert.equal(controls[0].toggle.hidden, false);
controls[0].input.value = 'ExampleUnique9!'; controls[0].input.events.input();
assert.ok(rules.every(rule => rule.classList.values.has('is-met')));
assert.match(summary.textContent, /All format requirements met/);
controls[0].toggle.events.click();
assert.equal(controls[0].input.type, 'text');
assert.equal(controls[0].input.value, 'ExampleUnique9!');
assert.equal(controls[0].toggle.attrs['aria-pressed'], 'true');
assert.equal(controls[1].input.type, 'password');
controls[0].toggle.events.click();assert.equal(controls[0].input.type, 'password');
for (const [password, missing] of [['lowercase9!', 'uppercase'], ['UPPERCASE9!', 'lowercase'], ['MissingNumber!', 'number'], ['Spaces Alone 9', 'special'], ['HiddenControl9\u200b', 'special'], ['CombiningAccent9\u0301', 'special'], ['Aa1!', 'length']]) {
  controls[0].input.value = password;controls[0].input.events.input();
  assert.equal(rules.find(r => r.dataset.passwordRule === missing).classList.values.has('is-met'), false);
}
controls[0].input.value='ÉlégantUnique9!';controls[0].input.events.change();
assert.ok(rules.every(rule => rule.classList.values.has('is-met')));
controls[0].toggle.events.click();pageEvents.pageshow.forEach(fn => fn());
assert.equal(controls[0].input.type, 'password');
assert.equal(controls[0].toggle.attrs['aria-label'], 'Show password');
controls[0].input.value='';controls[0].input.events.input();
assert.ok(rules.every(rule => !rule.classList.values.has('is-met')));
console.log('Password tools: independent accessible toggles, format feedback, Unicode, history reset and local-only handling passed.');
