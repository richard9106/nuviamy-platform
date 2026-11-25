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
const reloads = [];
const location = {href:'https://example.test/inbox/?type=forms&therapist=7&page=2',origin:'https://example.test',pathname:'/inbox/'};
const win = {location:{assign:url => navigations.push(url),reload:() => reloads.push(location.href)},addEventListener(){}};
win.top = win.self = win;
vm.runInNewContext(fs.readFileSync('static/workspace-drawers.js','utf8'), {
  document:doc,window:win,location,URL,
  MutationObserver:class { observe(){} },
});
const remote = nodes.find(node => node.tag === 'dialog');
const frame = nodes.find(node => node.tag === 'iframe');
const button = text => nodes.find(node => node.tag === 'button' && node.textContent === text);
const open = (href, dataset = {}) => {
  const link = {href,textContent:'New template',dataset,hasAttribute:()=>false,focus(){this.focused=true;}};
  doc.handlers.click({target:{closest:()=>link},button:0,preventDefault(){this.prevented = true;},stopImmediatePropagation(){}});
  return link;
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
  remote.close();
  const review = {workspaceReview:'1',workspaceReturn:'refresh'};
  open('https://example.test/accounts/security/setup/',review);
  assert.equal(remote.open,false,'A review marker must not allow authentication framing');
  const opener = open('https://example.test/intake/42/responses/',review);
  assert.equal(remote.open,true);
  delete child.body.dataset.workspaceDrawerRedirect;
  // A review is valid even when it contains no editable controls or any forms.
  main.hasAttribute = name => name === 'data-workspace-review';
  main.querySelectorAll = () => [];
  frame.contentWindow.location.href = frame.src;
  await frame.handlers.load();
  assert.equal(frame.style.visibility,'visible','Read-only reviews must remain inside the panel');
  button('×').handlers.click();
  assert.equal(remote.open,false);
  assert.equal(opener.focused,true,'Closing returns focus to the original action');
  assert.deepEqual(reloads,[],'Closing without changes does not refresh the page');
  const actionForm = {
    action:{toString:() => '[object RadioNodeList]'},
    getAttribute:() => null, setAttribute:(name,value) => { actionForm[name+'Attribute'] = value; },
    closest:() => null, querySelector:() => null,
  };
  main.querySelectorAll = () => [actionForm];
  open('https://example.test/intake/42/responses/',review);
  frame.contentWindow.location.href = frame.src;
  await frame.handlers.load();
  assert.equal(actionForm.actionAttribute,frame.src,'Named action buttons must not clobber the form destination');
  child.body.dataset.workspaceDrawerRedirect = '/intake/';
  child.body.dataset.workspaceDrawerResult = 'retry';
  await frame.handlers.load();
  assert.equal(remote.open,true,'Validation feedback must not close the review');
  assert.equal(frame.src,'https://example.test/intake/42/responses/?_workspace_drawer=1');
  assert.deepEqual(reloads,[]);
  child.body.dataset.workspaceDrawerResult = 'complete';
  child.body.dataset.workspaceDrawerRedirect = 'https://another.test/';
  await frame.handlers.load();
  assert.deepEqual(reloads,[],'Even a completion marker cannot authorize another origin');
  child.body.dataset.workspaceDrawerRedirect = '/intake/';
  await frame.handlers.load();
  assert.equal(remote.open,false);
  assert.deepEqual(reloads,['https://example.test/inbox/?type=forms&therapist=7&page=2'],'Completion preserves the current type, therapist and page');
  open('https://example.test/inbox/portal/8/',review);
  child.body.dataset.workspaceDrawerRedirect = '/login/?next=/inbox/';
  child.body.dataset.workspaceDrawerResult = 'navigate';
  await frame.handlers.load();
  assert.equal(new URL(navigations.at(-1)).pathname,'/login/','Authentication redirects stay outside the frame');
  assert.equal(new URL(navigations.at(-1)).searchParams.get('next'),'/inbox/');
  assert.equal(reloads.length,1,'Authentication failure must not appear as completion');
  console.log('Workspace editor/review lifecycle, validation retry, inbox return and same-origin navigation passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
