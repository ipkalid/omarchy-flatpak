const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const actions = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../Actions.js'), 'utf8'), actions);
const script = '/home/with spaces/$(literal)/flatpak-store';
for (const action of ['install', 'remove', 'update']) {
  assert.equal(actions.actionFromPayload(JSON.stringify({action})), action);
  const argv = ['xdg-terminal-exec', '--app-id=org.omarchy.terminal', 'bash', script];
  if (action !== 'install') argv.push(action);
  assert.deepEqual(Array.from(actions.commandFor(action, script)), argv);
}
for (const payload of ['', '{}', 'broken', 'null', '[]', '"update"', '{"action":"install; rm"}', '{"action":{}}']) {
  assert.equal(actions.actionFromPayload(payload), '');
}
assert.equal(actions.commandFor('unknown', script).length, 0);
assert.equal(actions.commandFor('update', 'relative/path').length, 0);

for (const flatpak of [true, false]) {
  for (const fzf of [true, false]) {
    for (const python3 of [true, false]) {
      const dependencies = {flatpak, fzf, python3};
      assert.equal(actions.canLaunch('install', dependencies), flatpak && fzf);
      assert.equal(actions.canLaunch('remove', dependencies), flatpak && fzf);
      assert.equal(actions.canLaunch('update', dependencies), flatpak);
      assert.equal(actions.canLaunch('invalid', dependencies), false);
      const message = actions.dependencyMessage(dependencies);
      assert.equal(message.includes('omarchy pkg add flatpak'), !flatpak);
      assert.equal(message.includes('omarchy pkg add fzf'), !fzf);
      assert.equal(message.includes('omarchy pkg add python'), !python3);
    }
  }
}
assert.equal(actions.canLaunch('update', null), false);
assert.equal(actions.isCurrent(2, 2, true), true);
assert.equal(actions.isCurrent(2, 2, false), false);
assert.equal(actions.isCurrent(2, 3, true), false);
