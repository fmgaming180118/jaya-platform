import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const researchPage = await readFile(
    new URL('../src/pages/ResearchPage.jsx', import.meta.url),
    'utf8'
);
const credentialGate = await readFile(
    new URL('../src/components/ApiCredentialGate.jsx', import.meta.url),
    'utf8'
);
const evolutionPage = await readFile(
    new URL('../src/pages/EvolutionPage.jsx', import.meta.url),
    'utf8'
);
const electronMain = await readFile(
    new URL('../electron/main.cjs', import.meta.url),
    'utf8'
);
const chatPage = await readFile(
    new URL('../src/pages/ChatPage.jsx', import.meta.url),
    'utf8'
);

test('Deep Research UI uses the Phase A client without direct legacy transport', () => {
    assert.match(researchPage, /api\.startRecursiveResearch\(/u);
    assert.doesNotMatch(researchPage, /fetch\s*\(/u);
    assert.doesNotMatch(researchPage, /localhost/u);
    assert.doesNotMatch(researchPage, /\/evolution\//u);
});

test('Deep Research UI cannot regress to automatic Core-application claims', () => {
    assert.doesNotMatch(researchPage, /APPLIED/u);
    assert.doesNotMatch(researchPage, /Berhasil Diinjeksi/u);
    assert.doesNotMatch(researchPage, /diinjeksi langsung/u);
    assert.match(researchPage, /Candidate non-promotable/u);
    assert.doesNotMatch(evolutionPage, /fetch\s*\(/u);
    assert.doesNotMatch(evolutionPage, /api\./u);
    assert.match(evolutionPage, /Status: BLOCKED/u);
    assert.match(evolutionPage, /Tidak ada request evolusi/u);
});

test('credential gate keeps the API key out of browser persistence', () => {
    assert.doesNotMatch(credentialGate, /localStorage|sessionStorage|indexedDB/u);
    assert.match(credentialGate, /setApiAccessToken\(token\)/u);
    assert.match(credentialGate, /clearApiAccessToken\(\)/u);
    assert.match(electronMain, /nodeIntegration:\s*false/u);
    assert.match(electronMain, /contextIsolation:\s*true/u);
    assert.match(electronMain, /sandbox:\s*true/u);
    assert.match(electronMain, /ELECTRON_START_URL is required/u);
    assert.match(electronMain, /loopbackHosts/u);
    assert.doesNotMatch(electronMain, /loadFile\(/u);
    assert.doesNotMatch(chatPage, /localStorage|sessionStorage|indexedDB/u);
});
