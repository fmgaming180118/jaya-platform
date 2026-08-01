import assert from 'node:assert/strict';
import test from 'node:test';

import {
    normalizeInternalTarget,
    parseAppPath,
} from '../src/routing/contracts.js';

test('router accepts only same-origin absolute paths', () => {
    const origin = 'https://jaya.local';
    assert.equal(
        normalizeInternalTarget('/project/lab/research', origin),
        '/project/lab/research'
    );
    assert.throws(
        () => normalizeInternalTarget('//evil.example/path', origin),
        /internal absolute path/
    );
    assert.throws(
        () => normalizeInternalTarget('https://evil.example/path', origin),
        /internal absolute path/
    );
});

test('router validates workspace and module boundaries', () => {
    assert.deepEqual(parseAppPath('/'), { kind: 'project-list' });
    assert.deepEqual(parseAppPath('/project/lab_01/research'), {
        kind: 'project',
        workspaceId: 'lab_01',
        module: 'research',
    });
    assert.deepEqual(parseAppPath('/project/lab_01'), {
        kind: 'project',
        workspaceId: 'lab_01',
        module: 'chat',
    });
    assert.deepEqual(parseAppPath('/project/%2E%2E/research'), { kind: 'not-found' });
    assert.deepEqual(parseAppPath('/project/lab/admin'), { kind: 'not-found' });
});
