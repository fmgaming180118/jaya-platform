const WORKSPACE_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;

const requireText = (value, field, maxLength) => {
    if (typeof value !== 'string') {
        throw new TypeError(`${field} must be a string`);
    }

    const normalized = value.trim();
    if (!normalized) {
        throw new TypeError(`${field} must contain non-whitespace text`);
    }
    if (normalized.length > maxLength) {
        throw new RangeError(`${field} must be at most ${maxLength} characters`);
    }
    return normalized;
};

const requireBoundedInteger = (value, field, minimum, maximum) => {
    if (!Number.isInteger(value) || value < minimum || value > maximum) {
        throw new RangeError(`${field} must be an integer from ${minimum} to ${maximum}`);
    }
    return value;
};

const requireWorkspaceId = (workspaceId) => {
    if (typeof workspaceId !== 'string' || !WORKSPACE_PATTERN.test(workspaceId)) {
        throw new TypeError(
            'workspaceId must start with an alphanumeric character and contain only letters, numbers, _ or -'
        );
    }
    return workspaceId;
};

const requireMetadata = (metadata) => {
    if (metadata === null || Array.isArray(metadata) || typeof metadata !== 'object') {
        throw new TypeError('metadata must be an object');
    }
    let serialized;
    try {
        serialized = JSON.stringify(metadata);
    } catch {
        throw new TypeError('metadata must be JSON serializable');
    }
    if (new TextEncoder().encode(serialized).byteLength > 65_536) {
        throw new RangeError('metadata must be at most 65536 UTF-8 bytes');
    }
    return metadata;
};

/** Build the exact FastAPI RecursiveResearchRequest payload. */
export const buildRecursiveResearchRequest = ({
    query,
    workspaceId = 'default',
    depth = 3,
    maxSourcesPerLevel = 5,
}) => ({
    query: requireText(query, 'query', 8_000),
    depth: requireBoundedInteger(depth, 'depth', 1, 5),
    workspace_id: requireWorkspaceId(workspaceId),
    max_sources_per_level: requireBoundedInteger(
        maxSourcesPerLevel,
        'maxSourcesPerLevel',
        1,
        10
    ),
});

/** Build the exact FastAPI IngestRequest payload for an inline source. */
export const buildIngestTextRequest = ({
    text,
    metadata = {},
    workspaceId = 'default',
    licenseId = 'UNKNOWN',
}) => ({
    text: requireText(text, 'text', 2_000_000),
    metadata: requireMetadata(metadata),
    workspace_id: requireWorkspaceId(workspaceId),
    license_id: requireText(licenseId, 'licenseId', 128),
});
