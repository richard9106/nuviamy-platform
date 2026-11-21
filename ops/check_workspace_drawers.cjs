// Exercise editor opening, change protection and redirect handling without network access.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.style = {}; this.handlers = {}; this.className = ''; this.hidden = false; }
  append(...nodes) { this.children.push(...nodes); }
  setAttribute(name, value) { this[name] = value; }
  removeAttribute(name) { delete this[name]; }
  addEventListener(name, handler) { this.handlers[name] = handler; }
  focus() { this.focused = true; }
  showModal() { this.open = true; }
  close() { this.open = false; this.handlers.close?.(); }
}
const nodes = [];
const doc = new Element('document');
doc.body = new Element('body');
doc.currentScript = {dataset: {baseStyle:'/static/dashboard.css',drawerStyle:'/static/workspace-drawers.css'}};
doc.querySelectorAll = () => [];
doc.createElement = tag => { const node = new Element(tag); nodes.push(node); return node; };
const navigations = [];
const win = {location:{assign:url => navigations.push(url)},addEventListener(){}};
win.top = win.self = win;
vm.runInNewContext(fs.readFileSync('static/workspace-drawers.js','utf8'), {
  document:doc,window:win,location:{href:'https://example.test/clients/',origin:'https://example.test'},URL,
  MutationObserver:class { observe(){} },
});
const remote = nodes.find(node => node.tag === 'dialog');
const frame = nodes.find(node => node.tag === 'iframe');
const button = text => nodes.find(node => node.tag === 'button' && node.textContent === text);
const open = href => {
  const link = {href,textContent:'New template',dataset:{},hasAttribute:()=>false,focus(){}};
  doc.handlers.click({target:{closest:()=>link},button:0,preventDefault(){this.prevented = true;},stopImmediatePropagation(){}});
};
open('https://another.test/intake/templates/new/');
assert.equal(remote.open,undefined,'Never embed another origin');
open('https://example.test/accounts/security/setup/');
assert.equal(remote.open,undefined,'Authentication must stay a full page');
open('https://example.test/intake/templates/new/');
assert.equal(remote.open,true);
assert.match(frame.src,/_workspace_drawer=1/);
const main = {querySelectorAll:()=>[{}],querySelector:()=>null,contains:()=>true};
const child = new Element('document');
child.body = new Element('body');
child.documentElement = {classList:{add(){}}};
// No matching controls keeps wrapForm out of this lifecycle test.
main.querySelectorAll = () => [{closest:()=>null,querySelector:selector => selector.startsWith('input') ? {} : null,classList:{contains:()=>true}}];
child.querySelector = selector => selector === 'main.app-main' ? main : null;
child.createElement = tag => new Element(tag);
child.head = {append:node => node.onload()};
frame.contentDocument = child;
frame.contentWindow = {location:{href:frame.src}};
(async () => {
  await frame.handlers.load();
  assert.equal(frame.style.visibility,'visible');
  child.handlers.input();
  button('×').handlers.click();
  const warning = nodes.find(node => node.className === 'workspace-unsaved');
  assert.equal(warning.hidden,false);
  assert.equal(remote.open,true,'Dirty form must remain open');
  button('Keep editing').handlers.click();
  assert.equal(warning.hidden,true);
  button('×').handlers.click();
  button('Discard changes').handlers.click();
  assert.equal(remote.open,false);
  open('https://example.test/intake/templates/new/');
  child.body.dataset.workspaceDrawerRedirect = 'https://another.test/';
  await frame.handlers.load();
  assert.deepEqual(navigations,[],'Never follow an external redirect');
  child.body.dataset.workspaceDrawerRedirect = '/intake/';
  await frame.handlers.load();
  assert.deepEqual(navigations,['https://example.test/intake/']);
  console.log('Workspace editor lifecycle, unsaved changes and same-origin navigation passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
