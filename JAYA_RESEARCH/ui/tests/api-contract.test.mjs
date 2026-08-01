import assert from 'node:assert/strict';
import test from 'node:test';

import {
    buildIngestTextRequest,
    buildRecursiveResearchRequest,
} from '../src/services/contracts.js';
import api, {
    ApiError,
    clearApiAccessToken,
    setApiAccessToken,
} from '../src/services/api.js';

test('recursive research builder matches the FastAPI request model', () => {
    assert.deepEqual(
        buildRecursiveResearchRequest({
            query: '  dampak RAG terhadap sitasi  ',
            workspaceId: 'riset_01',
            depth: 4,
            maxSourcesPerLevel: 7,
        }),
        {
            query: 'dampak RAG terhadap sitasi',
            depth: 4,
            workspace_id: 'riset_01',
            max_sources_per_level: 7,
        }
    );
});

test('recursive research builder fails before sending invalid requests', () => {
    assert.throws(
        () => buildRecursiveResearchRequest({ query: ' ', depth: 3 }),
        /query must contain non-whitespace text/
    );
    assert.throws(
        () => buildRecursiveResearchRequest({ query: 'valid', depth: 6 }),
        /depth must be an integer from 1 to 5/
    );
    assert.throws(
        () => buildRecursiveResearchRequest({ query: 'valid', workspaceId: '../escape' }),
        /workspaceId must start/
    );
});

test('inline ingest builder matches the FastAPI request model', () => {
    assert.deepEqual(
        buildIngestTextRequest({
            text: '  sumber primer  ',
            metadata: { title: 'Catatan eksperimen' },
            workspaceId: 'lab-a',
            licenseId: 'CC-BY-4.0',
        }),
        {
            text: 'sumber primer',
            metadata: { title: 'Catatan eksperimen' },
            workspace_id: 'lab-a',
            license_id: 'CC-BY-4.0',
        }
    );
});

test('inline ingest builder rejects invalid text, metadata, and license', () => {
    assert.throws(
        () => buildIngestTextRequest({ text: '' }),
        /text must contain non-whitespace text/
    );
    assert.throws(
        () => buildIngestTextRequest({ text: 'valid', metadata: [] }),
        /metadata must be an object/
    );
    assert.throws(
        () => buildIngestTextRequest({ text: 'valid', licenseId: ' ' }),
        /licenseId must contain non-whitespace text/
    );
    const circular = {};
    circular.self = circular;
    assert.throws(
        () => buildIngestTextRequest({ text: 'valid', metadata: circular }),
        /metadata must be JSON serializable/
    );
});

test('API transport sends memory-only auth and the recursive contract', async (context) => {
    const originalFetch = globalThis.fetch;
    context.after(() => {
        globalThis.fetch = originalFetch;
        clearApiAccessToken();
    });
    const requests = [];
    globalThis.fetch = async (url, options) => {
        requests.push({ url, options });
        if (String(url).includes('/documents/view/')) {
            return new Response('authenticated document', { status: 200 });
        }
        return new Response(JSON.stringify({ status: 'ABSTAINED_NO_EVIDENCE' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
        });
    };
    const token = `phase-a-${'x'.repeat(32)}`;
    setApiAccessToken(token);

    await api.startRecursiveResearch('query', 'default', 2, 4);
    const documentText = await api.readDocumentText('default', 'evidence.md');

    assert.equal(requests.length, 2);
    assert.equal(requests[0].url, '/api/research/recursive');
    assert.equal(requests[0].options.headers.Authorization, `Bearer ${token}`);
    assert.deepEqual(JSON.parse(requests[0].options.body), {
        query: 'query',
        depth: 2,
        workspace_id: 'default',
        max_sources_per_level: 4,
    });
    assert.equal(documentText, 'authenticated document');
    assert.equal(requests[1].url, '/api/documents/view/default/evidence.md');
    assert.equal(requests[1].options.headers.Authorization, `Bearer ${token}`);
});

test('API transport preserves structured backend error codes', async (context) => {
    const originalFetch = globalThis.fetch;
    context.after(() => {
        globalThis.fetch = originalFetch;
        clearApiAccessToken();
    });
    globalThis.fetch = async () => new Response(JSON.stringify({
        error: { code: 'AUTHENTICATION_REQUIRED', message: 'Authentication is required' },
    }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
    });

    await assert.rejects(
        api.listWorkspaces(),
        (error) => error instanceof ApiError
            && error.status === 401
            && error.code === 'AUTHENTICATION_REQUIRED'
            && error.message === 'Authentication is required'
    );
});

test('autonomous research requires and sends an idempotency key', async (context) => {
    assert.throws(
        () => api.startResearch('topic', '', 'default', 5),
        /idempotencyKey must contain 8-128 characters/
    );

    const originalFetch = globalThis.fetch;
    context.after(() => {
        globalThis.fetch = originalFetch;
        clearApiAccessToken();
    });
    let captured;
    globalThis.fetch = async (url, options) => {
        captured = { url, options };
        return new Response(JSON.stringify({ created: true }), {
            status: 202,
            headers: { 'Content-Type': 'application/json' },
        });
    };

    await api.startResearch('topic', 'focus', 'default', 7, 'request-00000001');

    assert.equal(captured.options.headers['Idempotency-Key'], 'request-00000001');
    assert.equal(JSON.parse(captured.options.body).max_queries, 7);
});
