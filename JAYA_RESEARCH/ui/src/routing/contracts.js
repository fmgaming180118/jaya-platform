const WORKSPACE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;
const PROJECT_MODULES = new Set(['chat', 'research', 'graph', 'thesis', 'evolution']);

export const normalizeInternalTarget = (target, origin) => {
    if (
        typeof target !== 'string'
        || !target.startsWith('/')
        || target.startsWith('//')
        || Array.from(target).some((character) => character.charCodeAt(0) < 32)
    ) {
        throw new TypeError('Navigation target must be an internal absolute path');
    }
    const parsed = new URL(target, origin);
    if (parsed.origin !== origin) {
        throw new TypeError('Navigation target must remain on the current origin');
    }
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
};

export const parseAppPath = (pathname) => {
    if (pathname === '/' || pathname === '') {
        return { kind: 'project-list' };
    }

    const match = /^\/project\/([^/]+)(?:\/([^/]+))?\/?$/u.exec(pathname);
    if (!match) return { kind: 'not-found' };

    let workspaceId;
    try {
        workspaceId = decodeURIComponent(match[1]);
    } catch {
        return { kind: 'not-found' };
    }
    if (!WORKSPACE_PATTERN.test(workspaceId)) return { kind: 'not-found' };

    const module = match[2] || 'chat';
    if (!PROJECT_MODULES.has(module)) return { kind: 'not-found' };
    return { kind: 'project', workspaceId, module };
};
