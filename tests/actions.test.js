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
      const dependencies = {flatpak, fzf, python3, timeout: true, "xdg-terminal-exec": true};
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

for (const provider of ['brew', 'mise']) {
  for (const action of ['install', 'remove', 'update']) {
    const supported = provider === 'brew' || action !== 'update';
    const request = actions.requestFromPayload(JSON.stringify({provider, action}));
    assert.equal(request.provider, provider);
    assert.equal(request.action, supported ? action : '');
    for (const available of [false, true]) {
      for (const python3 of [false, true]) {
        for (const fzf of [false, true]) {
          assert.equal(actions.canLaunch(action, {[provider]: available, python3, fzf, timeout: true, "xdg-terminal-exec": true}, provider),
            supported && available && python3 && (action === 'update' || fzf));
        }
      }
    }
    const runner = '/path with spaces/' + provider + '-store';
    const expected = supported ? ['xdg-terminal-exec', '--app-id=org.omarchy.terminal', 'bash', runner,
      ...(action === 'install' ? [] : [action])] : [];
    assert.deepEqual(Array.from(actions.commandFor(action, runner, provider)), expected);
  }
}
for (const provider of ['invalid', '', null, ['brew'], {}]) {
  assert.equal(actions.requestFromPayload(JSON.stringify({provider, action: 'install'})).action, '');
  assert.equal(actions.canLaunch('install', {flatpak: true, fzf: true}, provider), false);
}
assert.equal(actions.dependencyMessage({brew: true, fzf: true, python3: true, timeout: true, "xdg-terminal-exec": true}, 'brew'), '');
assert.equal(actions.dependencyMessage({mise: true, fzf: true, python3: true, timeout: true, "xdg-terminal-exec": true}, 'mise'), '');

// Every provider blocks only the actions that need the missing command.
const complete = {flatpak: true, brew: true, mise: true, fzf: true, python3: true,
  timeout: true, 'xdg-terminal-exec': true};
assert.equal(actions.validDependencies(complete), true);
for (const missing of Object.keys(complete)) {
  const dependencies = {...complete, [missing]: false};
  assert.equal(actions.validDependencies(dependencies), true);
  assert.equal(actions.validDependencies({...complete, [missing]: 'true'}), false);
  for (const provider of ['flatpak', 'brew', 'mise']) {
    for (const action of ['install', 'remove', 'update']) {
      const supported = provider !== 'mise' || action !== 'update';
      const needed = [provider, 'xdg-terminal-exec',
        ...(provider === 'flatpak' ? [] : ['python3']),
        ...(action === 'update' ? [] : ['fzf', 'timeout'])];
      assert.equal(actions.canLaunch(action, dependencies, provider), supported && !needed.includes(missing));
    }
    const guidance = actions.dependencyMessage(dependencies, provider);
    if (missing === provider) {
      assert.ok(guidance.includes(provider === 'brew' ? 'https://brew.sh' : 'omarchy pkg add ' + provider));
    } else if (['flatpak', 'brew', 'mise'].includes(missing)) {
      assert.equal(guidance, '', 'An unavailable provider must not affect another provider');
    }
    if (missing === 'timeout') assert.ok(guidance.includes('omarchy pkg add coreutils'));
    if (missing === 'xdg-terminal-exec') assert.ok(guidance.includes('omarchy pkg add xdg-terminal-exec'));
  }
}
assert.equal(actions.validDependencies(null), false);
assert.equal(actions.validDependencies({}), false);
// A fresh successful probe enables the provider again after Check again.
for (const provider of ['brew', 'mise']) {
  assert.equal(actions.canLaunch('install', {...complete, [provider]: false}, provider), false);
  assert.equal(actions.canLaunch('install', complete, provider), true);
}
