use std::slice;

const OK: i32 = 0;
const NULL_POINTER: i32 = -1;
const INVALID_SIZE: i32 = -2;
const INVALID_VALUE: i32 = -3;
const RESOURCE_LIMIT: i32 = -4;
const CAPABILITY_POLICY_EVALUATION: u64 = 1 << 0;
const CAPABILITY_PRIVACY_SCOPE: u64 = 1 << 1;
const CAPABILITY_ZERO_TRUST_AUTHORIZATION: u64 = 1 << 2;
const CAPABILITY_CRYPTOGRAPHIC_SKIN: u64 = 1 << 3;
const POLICY_MAGIC: &[u8; 4] = b"JPR1";
const POLICY_MAX_BYTES: usize = 1024 * 1024;
const POLICY_MAX_RULES: u32 = 4096;
const POLICY_RISK_MASK: u8 = 0b0011_1111;
const POLICY_NO_RULE: u32 = u32::MAX;
const PRIVACY_MAGIC: &[u8; 4] = b"JPV1";
const PRIVACY_MAX_BYTES: usize = 1024 * 1024;
const PRIVACY_CLASSIFICATION_MASK: u8 = 0b0000_1111;
const PRIVACY_PURPOSE_MASK: u8 = 0b0011_1111;
const ZERO_TRUST_MAGIC: &[u8; 4] = b"JZT1";
const ZERO_TRUST_MAX_BYTES: usize = 1024 * 1024;
const CRYPTOGRAPHIC_SKIN_MAGIC: &[u8; 4] = b"JCS1";
const CRYPTOGRAPHIC_SKIN_MAX_BYTES: usize = 4 * 1024;
const CRYPTOGRAPHIC_SKIN_MAX_PAYLOAD_BYTES: u32 = 64 * 1024 * 1024;

#[no_mangle]
pub extern "C" fn jaya_trusted_abi_version() -> u32 {
    1
}

#[no_mangle]
pub extern "C" fn jaya_trusted_provider_id() -> *const u8 {
    b"jaya-rust-trusted-v1\0".as_ptr()
}

#[no_mangle]
pub extern "C" fn jaya_trusted_capabilities() -> u64 {
    CAPABILITY_POLICY_EVALUATION
        | CAPABILITY_PRIVACY_SCOPE
        | CAPABILITY_ZERO_TRUST_AUTHORIZATION
        | CAPABILITY_CRYPTOGRAPHIC_SKIN
}

fn is_safe_policy_identifier(value: &[u8]) -> bool {
    (1..=192).contains(&value.len())
        && value[0].is_ascii_alphanumeric()
        && value
            .iter()
            .all(|byte| byte.is_ascii_alphanumeric() || b"._:-".contains(byte))
}

fn read_u16(value: &[u8], cursor: &mut usize) -> Option<u16> {
    let end = cursor.checked_add(2)?;
    let bytes = value.get(*cursor..end)?;
    *cursor = end;
    Some(u16::from_le_bytes([bytes[0], bytes[1]]))
}

fn read_u32(value: &[u8], cursor: &mut usize) -> Option<u32> {
    let end = cursor.checked_add(4)?;
    let bytes = value.get(*cursor..end)?;
    *cursor = end;
    Some(u32::from_le_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]))
}

fn valid_policy_effect(value: u8) -> bool {
    matches!(value, 1..=3)
}

fn is_safe_privacy_identifier(value: &[u8]) -> bool {
    (1..=256).contains(&value.len())
        && value[0].is_ascii_alphanumeric()
        && value
            .iter()
            .all(|byte| byte.is_ascii_alphanumeric() || b"._:@/-".contains(byte))
}

fn read_privacy_identifier<'a>(value: &'a [u8], cursor: &mut usize) -> Result<&'a [u8], i32> {
    let length = read_u16(value, cursor).ok_or(INVALID_SIZE)? as usize;
    if length == 0 {
        return Err(INVALID_SIZE);
    }
    let end = cursor.checked_add(length).ok_or(RESOURCE_LIMIT)?;
    let identifier = value.get(*cursor..end).ok_or(INVALID_SIZE)?;
    if !is_safe_privacy_identifier(identifier) {
        return Err(INVALID_VALUE);
    }
    *cursor = end;
    Ok(identifier)
}

fn is_safe_content_type(value: &[u8]) -> bool {
    let mut parts = value.split(|byte| *byte == b'/');
    let valid_part = |part: &[u8]| {
        (1..=64).contains(&part.len())
            && part[0].is_ascii_alphanumeric()
            && part
                .iter()
                .all(|byte| byte.is_ascii_alphanumeric() || b"!#$&^_.+-".contains(byte))
    };
    match (parts.next(), parts.next(), parts.next()) {
        (Some(kind), Some(format), None) => valid_part(kind) && valid_part(format),
        _ => false,
    }
}

fn read_content_type<'a>(value: &'a [u8], cursor: &mut usize) -> Result<&'a [u8], i32> {
    let length = read_u16(value, cursor).ok_or(INVALID_SIZE)? as usize;
    if length == 0 {
        return Err(INVALID_SIZE);
    }
    let end = cursor.checked_add(length).ok_or(RESOURCE_LIMIT)?;
    let content_type = value.get(*cursor..end).ok_or(INVALID_SIZE)?;
    if !is_safe_content_type(content_type) {
        return Err(INVALID_VALUE);
    }
    *cursor = end;
    Ok(content_type)
}

#[no_mangle]
pub unsafe extern "C" fn jaya_trusted_evaluate_policy(
    policy_table: *const u8,
    policy_table_length: usize,
    capability_id: *const u8,
    capability_id_length: usize,
    risk_code: u8,
    default_effect: u8,
    output_effect: *mut u8,
    output_rule_index: *mut u32,
) -> i32 {
    if policy_table.is_null()
        || capability_id.is_null()
        || output_effect.is_null()
        || output_rule_index.is_null()
    {
        return NULL_POINTER;
    }
    if policy_table_length < 8 || capability_id_length == 0 {
        return INVALID_SIZE;
    }
    if policy_table_length > POLICY_MAX_BYTES {
        return RESOURCE_LIMIT;
    }
    if risk_code >= 6 || !valid_policy_effect(default_effect) {
        return INVALID_VALUE;
    }

    let table = slice::from_raw_parts(policy_table, policy_table_length);
    let requested_capability = slice::from_raw_parts(capability_id, capability_id_length);
    if !is_safe_policy_identifier(requested_capability) || &table[..4] != POLICY_MAGIC {
        return INVALID_VALUE;
    }

    let mut cursor = 4usize;
    let rule_count = match read_u32(table, &mut cursor) {
        Some(value) if value > 0 => value,
        _ => return INVALID_SIZE,
    };
    if rule_count > POLICY_MAX_RULES {
        return RESOURCE_LIMIT;
    }

    let requested_risk = 1u8 << risk_code;
    let mut selected: Option<(u8, u32)> = None;
    for rule_index in 0..rule_count {
        let effect = match table.get(cursor) {
            Some(value) if valid_policy_effect(*value) => *value,
            _ => return INVALID_VALUE,
        };
        cursor += 1;
        let risk_mask = match table.get(cursor) {
            Some(value) if *value & !POLICY_RISK_MASK == 0 => *value,
            _ => return INVALID_VALUE,
        };
        cursor += 1;
        let capability_count = match read_u16(table, &mut cursor) {
            Some(value) => value,
            None => return INVALID_SIZE,
        };
        let mut capability_matches = capability_count == 0;
        for _ in 0..capability_count {
            let length = match read_u16(table, &mut cursor) {
                Some(value) if value > 0 => value as usize,
                _ => return INVALID_SIZE,
            };
            let end = match cursor.checked_add(length) {
                Some(value) => value,
                None => return RESOURCE_LIMIT,
            };
            let candidate = match table.get(cursor..end) {
                Some(value) if is_safe_policy_identifier(value) => value,
                _ => return INVALID_VALUE,
            };
            cursor = end;
            capability_matches |= candidate == requested_capability;
        }
        let risk_matches = risk_mask == 0 || risk_mask & requested_risk != 0;
        if selected.is_none() && capability_matches && risk_matches {
            selected = Some((effect, rule_index));
        }
    }
    if cursor != table.len() {
        return INVALID_SIZE;
    }

    let (effect, rule_index) = selected.unwrap_or((default_effect, POLICY_NO_RULE));
    *output_effect = effect;
    *output_rule_index = rule_index;
    OK
}

#[no_mangle]
pub unsafe extern "C" fn jaya_trusted_evaluate_privacy(
    privacy_contract: *const u8,
    privacy_contract_length: usize,
    output_effect: *mut u8,
    output_reason: *mut u8,
) -> i32 {
    if privacy_contract.is_null() || output_effect.is_null() || output_reason.is_null() {
        return NULL_POINTER;
    }
    if privacy_contract_length < 8 {
        return INVALID_SIZE;
    }
    if privacy_contract_length > PRIVACY_MAX_BYTES {
        return RESOURCE_LIMIT;
    }
    let contract = slice::from_raw_parts(privacy_contract, privacy_contract_length);
    if &contract[..4] != PRIVACY_MAGIC {
        return INVALID_VALUE;
    }
    let mut cursor = 4usize;
    let actor = match read_privacy_identifier(contract, &mut cursor) {
        Ok(value) => value,
        Err(status) => return status,
    };
    let owner = match read_privacy_identifier(contract, &mut cursor) {
        Ok(value) => value,
        Err(status) => return status,
    };
    let subject = match read_privacy_identifier(contract, &mut cursor) {
        Ok(value) => value,
        Err(status) => return status,
    };
    let provider = match read_privacy_identifier(contract, &mut cursor) {
        Ok(value) => value,
        Err(status) => return status,
    };
    let classification = match contract.get(cursor) {
        Some(value) if *value < 4 => *value,
        _ => return INVALID_VALUE,
    };
    cursor += 1;
    let purpose = match contract.get(cursor) {
        Some(value) if *value < 6 => *value,
        _ => return INVALID_VALUE,
    };
    cursor += 1;
    let destination = match contract.get(cursor) {
        Some(value) if *value < 3 => *value,
        _ => return INVALID_VALUE,
    };
    cursor += 1;
    let consent_present = match contract.get(cursor) {
        Some(0) => false,
        Some(1) => true,
        _ => return INVALID_VALUE,
    };
    cursor += 1;

    let mut consent_scope_matches = false;
    if consent_present {
        let consent_owner = match read_privacy_identifier(contract, &mut cursor) {
            Ok(value) => value,
            Err(status) => return status,
        };
        let consent_subject = match read_privacy_identifier(contract, &mut cursor) {
            Ok(value) => value,
            Err(status) => return status,
        };
        let classification_mask = match contract.get(cursor) {
            Some(value) if *value > 0 && *value & !PRIVACY_CLASSIFICATION_MASK == 0 => *value,
            _ => return INVALID_VALUE,
        };
        cursor += 1;
        let purpose_mask = match contract.get(cursor) {
            Some(value) if *value > 0 && *value & !PRIVACY_PURPOSE_MASK == 0 => *value,
            _ => return INVALID_VALUE,
        };
        cursor += 1;
        let provider_count = match read_u16(contract, &mut cursor) {
            Some(value) if value > 0 => value,
            _ => return INVALID_SIZE,
        };
        let mut provider_matches = false;
        for _ in 0..provider_count {
            let candidate = match read_privacy_identifier(contract, &mut cursor) {
                Ok(value) => value,
                Err(status) => return status,
            };
            provider_matches |= candidate == provider;
        }
        consent_scope_matches = consent_owner == owner
            && consent_subject == subject
            && classification_mask & (1 << classification) != 0
            && purpose_mask & (1 << purpose) != 0
            && provider_matches;
    }
    if cursor != contract.len() {
        return INVALID_SIZE;
    }

    let (effect, reason) = if actor != owner {
        (2, 1)
    } else if destination == 0 || destination == 2 {
        (1, 2)
    } else if classification == 0 {
        (1, 3)
    } else if !consent_present {
        (2, 5)
    } else if consent_scope_matches {
        (1, 4)
    } else {
        (2, 6)
    };
    *output_effect = effect;
    *output_reason = reason;
    OK
}

#[no_mangle]
pub unsafe extern "C" fn jaya_trusted_evaluate_zero_trust(
    authorization_contract: *const u8,
    authorization_contract_length: usize,
    output_effect: *mut u8,
    output_reason: *mut u8,
) -> i32 {
    if authorization_contract.is_null() || output_effect.is_null() || output_reason.is_null() {
        return NULL_POINTER;
    }
    if authorization_contract_length < 82 {
        return INVALID_SIZE;
    }
    if authorization_contract_length > ZERO_TRUST_MAX_BYTES {
        return RESOURCE_LIMIT;
    }
    let contract = slice::from_raw_parts(authorization_contract, authorization_contract_length);
    if &contract[..4] != ZERO_TRUST_MAGIC {
        return INVALID_VALUE;
    }
    let mut cursor = 4usize;
    let _envelope_id = match read_privacy_identifier(contract, &mut cursor) {
        Ok(value) => value,
        Err(status) => return status,
    };
    let _principal_id = match read_privacy_identifier(contract, &mut cursor) {
        Ok(value) => value,
        Err(status) => return status,
    };
    let envelope_node = match read_privacy_identifier(contract, &mut cursor) {
        Ok(value) => value,
        Err(status) => return status,
    };
    let capability = match read_privacy_identifier(contract, &mut cursor) {
        Ok(value) => value,
        Err(status) => return status,
    };
    let _nonce = match read_privacy_identifier(contract, &mut cursor) {
        Ok(value) => value,
        Err(status) => return status,
    };
    let principal_status = match contract.get(cursor) {
        Some(value) if *value <= 2 => *value,
        _ => return INVALID_VALUE,
    };
    cursor += 1;
    let principal_state = match contract.get(cursor) {
        Some(value) if *value <= 4 => *value,
        _ => return INVALID_VALUE,
    };
    cursor += 1;
    let attestation_state = match contract.get(cursor) {
        Some(value) if *value <= 3 => *value,
        _ => return INVALID_VALUE,
    };
    cursor += 1;

    let mut persisted_node: Option<&[u8]> = None;
    let mut capability_matches = false;
    if principal_status == 0 {
        if principal_state != 0 {
            return INVALID_VALUE;
        }
    } else {
        persisted_node = match read_privacy_identifier(contract, &mut cursor) {
            Ok(value) => Some(value),
            Err(status) => return status,
        };
        let capability_count = match read_u16(contract, &mut cursor) {
            Some(value) if value > 0 => value,
            _ => return INVALID_SIZE,
        };
        for _ in 0..capability_count {
            let candidate = match read_privacy_identifier(contract, &mut cursor) {
                Ok(value) => value,
                Err(status) => return status,
            };
            capability_matches |= candidate == capability;
        }
    }
    let claimed_end = match cursor.checked_add(32) {
        Some(value) => value,
        None => return RESOURCE_LIMIT,
    };
    let claimed_payload = match contract.get(cursor..claimed_end) {
        Some(value) => value,
        None => return INVALID_SIZE,
    };
    cursor = claimed_end;
    let actual_end = match cursor.checked_add(32) {
        Some(value) => value,
        None => return RESOURCE_LIMIT,
    };
    let actual_payload = match contract.get(cursor..actual_end) {
        Some(value) => value,
        None => return INVALID_SIZE,
    };
    cursor = actual_end;
    if cursor != contract.len() {
        return INVALID_SIZE;
    }

    let (effect, reason) = if principal_status == 0 || principal_state == 1 {
        (2, 1)
    } else if principal_status == 2 || principal_state == 2 {
        (2, 2)
    } else if principal_state == 3 {
        (2, 3)
    } else if principal_state == 4 {
        (2, 4)
    } else if persisted_node != Some(envelope_node) {
        (2, 5)
    } else if !capability_matches {
        (2, 6)
    } else if claimed_payload != actual_payload {
        (2, 7)
    } else if attestation_state == 0 {
        (3, 8)
    } else if attestation_state == 3 {
        (2, 10)
    } else if attestation_state == 2 {
        (2, 9)
    } else {
        (1, 11)
    };
    *output_effect = effect;
    *output_reason = reason;
    OK
}

#[no_mangle]
pub unsafe extern "C" fn jaya_trusted_evaluate_cryptographic_skin(
    envelope_contract: *const u8,
    envelope_contract_length: usize,
    output_effect: *mut u8,
    output_reason: *mut u8,
) -> i32 {
    if envelope_contract.is_null() || output_effect.is_null() || output_reason.is_null() {
        return NULL_POINTER;
    }
    if envelope_contract_length < 32 {
        return INVALID_SIZE;
    }
    if envelope_contract_length > CRYPTOGRAPHIC_SKIN_MAX_BYTES {
        return RESOURCE_LIMIT;
    }
    let contract = slice::from_raw_parts(envelope_contract, envelope_contract_length);
    if &contract[..4] != CRYPTOGRAPHIC_SKIN_MAGIC {
        return INVALID_VALUE;
    }
    let mut cursor = 4usize;
    let _envelope_id = match read_privacy_identifier(contract, &mut cursor) {
        Ok(value) => value,
        Err(status) => return status,
    };
    let _key_id = match read_privacy_identifier(contract, &mut cursor) {
        Ok(value) => value,
        Err(status) => return status,
    };
    let _purpose = match read_privacy_identifier(contract, &mut cursor) {
        Ok(value) => value,
        Err(status) => return status,
    };
    let _subject = match read_privacy_identifier(contract, &mut cursor) {
        Ok(value) => value,
        Err(status) => return status,
    };
    let _content_type = match read_content_type(contract, &mut cursor) {
        Ok(value) => value,
        Err(status) => return status,
    };
    let schema_version = match read_u16(contract, &mut cursor) {
        Some(value) => value,
        None => return INVALID_SIZE,
    };
    let algorithm_suite = match contract.get(cursor) {
        Some(value) => *value,
        None => return INVALID_SIZE,
    };
    cursor += 1;
    let operation = match contract.get(cursor) {
        Some(value) if matches!(*value, 1 | 2) => *value,
        _ => return INVALID_VALUE,
    };
    cursor += 1;
    let key_state = match contract.get(cursor) {
        Some(value) if *value <= 3 => *value,
        _ => return INVALID_VALUE,
    };
    cursor += 1;
    let attestation_state = match contract.get(cursor) {
        Some(value) if *value <= 3 => *value,
        _ => return INVALID_VALUE,
    };
    cursor += 1;
    let temporal_state = match contract.get(cursor) {
        Some(value) if *value <= 3 => *value,
        _ => return INVALID_VALUE,
    };
    cursor += 1;
    let nonce_size = match read_u16(contract, &mut cursor) {
        Some(value) => value,
        None => return INVALID_SIZE,
    };
    let ciphertext_size = match read_u32(contract, &mut cursor) {
        Some(value) => value,
        None => return INVALID_SIZE,
    };
    let max_payload_size = match read_u32(contract, &mut cursor) {
        Some(value) if (1..=CRYPTOGRAPHIC_SKIN_MAX_PAYLOAD_BYTES).contains(&value) => value,
        _ => return INVALID_VALUE,
    };
    if cursor != contract.len() {
        return INVALID_SIZE;
    }
    if attestation_state == 0
        && (key_state != 0 || temporal_state != 0 || nonce_size != 0 || ciphertext_size != 0)
    {
        return INVALID_VALUE;
    }

    let max_ciphertext_size = match max_payload_size.checked_add(16) {
        Some(value) => value,
        None => return RESOURCE_LIMIT,
    };
    let (effect, reason) = if schema_version != 1 || algorithm_suite != 1 {
        (2, 1)
    } else if attestation_state == 0 {
        (3, 2)
    } else if attestation_state == 3 {
        (2, 4)
    } else if attestation_state == 2 {
        (2, 3)
    } else if key_state == 3 {
        (2, 6)
    } else if key_state == 0 || (operation == 1 && key_state != 1) {
        (2, 5)
    } else if temporal_state == 2 {
        (2, 7)
    } else if temporal_state == 3 {
        (2, 8)
    } else if temporal_state == 0 {
        (2, 1)
    } else if nonce_size == 0 && ciphertext_size == 0 {
        (3, 9)
    } else if nonce_size != 12 {
        (2, 10)
    } else if ciphertext_size < 16 {
        (2, 11)
    } else if ciphertext_size > max_ciphertext_size {
        (2, 12)
    } else {
        (1, 13)
    };
    *output_effect = effect;
    *output_reason = reason;
    OK
}

#[no_mangle]
pub unsafe extern "C" fn jaya_trusted_validate_identifier(value: *const u8, length: usize) -> i32 {
    if value.is_null() {
        return NULL_POINTER;
    }
    if !(1..=128).contains(&length) {
        return INVALID_SIZE;
    }
    let bytes = slice::from_raw_parts(value, length);
    if !bytes[0].is_ascii_alphanumeric()
        || bytes
            .iter()
            .any(|byte| !(byte.is_ascii_alphanumeric() || b"._-".contains(byte)))
    {
        return INVALID_VALUE;
    }
    OK
}

#[no_mangle]
pub unsafe extern "C" fn jaya_trusted_validate_binary_layout(
    rows: *const u8,
    total_bytes: usize,
    input_features: usize,
    output_units: usize,
    max_features: usize,
    max_outputs: usize,
    max_total_bits: usize,
) -> i32 {
    if rows.is_null() {
        return NULL_POINTER;
    }
    if input_features == 0
        || output_units == 0
        || input_features > max_features
        || output_units > max_outputs
    {
        return INVALID_SIZE;
    }
    let total_bits = match input_features.checked_mul(output_units) {
        Some(value) if value <= max_total_bits => value,
        _ => return RESOURCE_LIMIT,
    };
    if total_bits == 0 {
        return INVALID_SIZE;
    }
    let row_bytes = match input_features.checked_add(7) {
        Some(value) => value / 8,
        None => return RESOURCE_LIMIT,
    };
    if row_bytes.checked_mul(output_units) != Some(total_bytes) {
        return INVALID_SIZE;
    }
    let bytes = slice::from_raw_parts(rows, total_bytes);
    let remainder = input_features % 8;
    if remainder != 0 {
        let padding_mask = !((1u8 << remainder) - 1);
        for row in 0..output_units {
            if bytes[row * row_bytes + row_bytes - 1] & padding_mask != 0 {
                return INVALID_VALUE;
            }
        }
    }
    OK
}

#[no_mangle]
pub unsafe extern "C" fn jaya_trusted_validate_ternary_values(
    values: *const i8,
    length: usize,
    max_length: usize,
) -> i32 {
    if values.is_null() {
        return NULL_POINTER;
    }
    if length == 0 {
        return INVALID_SIZE;
    }
    if length > max_length {
        return RESOURCE_LIMIT;
    }
    let values = slice::from_raw_parts(values, length);
    if values.iter().any(|value| *value < -1 || *value > 1) {
        return INVALID_VALUE;
    }
    OK
}

#[cfg(test)]
mod tests {
    use super::*;

    fn policy_table(rules: &[(u8, u8, &[&[u8]])]) -> Vec<u8> {
        let mut output = POLICY_MAGIC.to_vec();
        output.extend_from_slice(&(rules.len() as u32).to_le_bytes());
        for (effect, risks, capabilities) in rules {
            output.push(*effect);
            output.push(*risks);
            output.extend_from_slice(&(capabilities.len() as u16).to_le_bytes());
            for capability in *capabilities {
                output.extend_from_slice(&(capability.len() as u16).to_le_bytes());
                output.extend_from_slice(capability);
            }
        }
        output
    }

    fn append_privacy_identifier(output: &mut Vec<u8>, value: &[u8]) {
        output.extend_from_slice(&(value.len() as u16).to_le_bytes());
        output.extend_from_slice(value);
    }

    fn privacy_contract(with_consent: bool, consent_provider: &[u8]) -> Vec<u8> {
        let mut output = PRIVACY_MAGIC.to_vec();
        append_privacy_identifier(&mut output, b"owner-1");
        append_privacy_identifier(&mut output, b"owner-1");
        append_privacy_identifier(&mut output, b"subject-1");
        append_privacy_identifier(&mut output, b"provider-real");
        output.extend_from_slice(&[2, 2, 1, u8::from(with_consent)]);
        if with_consent {
            append_privacy_identifier(&mut output, b"owner-1");
            append_privacy_identifier(&mut output, b"subject-1");
            output.extend_from_slice(&[1 << 2, 1 << 2]);
            output.extend_from_slice(&1u16.to_le_bytes());
            append_privacy_identifier(&mut output, consent_provider);
        }
        output
    }

    fn zero_trust_contract(
        persisted_node: &[u8],
        capability: &[u8],
        attestation_state: u8,
        payload_matches: bool,
    ) -> Vec<u8> {
        let mut output = ZERO_TRUST_MAGIC.to_vec();
        append_privacy_identifier(&mut output, b"trust-envelope-1");
        append_privacy_identifier(&mut output, b"principal-1");
        append_privacy_identifier(&mut output, b"node-1");
        append_privacy_identifier(&mut output, capability);
        append_privacy_identifier(&mut output, b"nonce-1");
        output.extend_from_slice(&[1, 0, attestation_state]);
        append_privacy_identifier(&mut output, persisted_node);
        output.extend_from_slice(&1u16.to_le_bytes());
        append_privacy_identifier(&mut output, b"core.logic.evaluate");
        output.extend_from_slice(&[0xAA; 32]);
        output.extend_from_slice(if payload_matches {
            &[0xAA; 32]
        } else {
            &[0xBB; 32]
        });
        output
    }

    fn cryptographic_skin_contract(
        key_state: u8,
        attestation_state: u8,
        temporal_state: u8,
        nonce_size: u16,
        ciphertext_size: u32,
    ) -> Vec<u8> {
        let mut output = CRYPTOGRAPHIC_SKIN_MAGIC.to_vec();
        append_privacy_identifier(&mut output, b"env-native-1");
        append_privacy_identifier(&mut output, b"key-native-1");
        append_privacy_identifier(&mut output, b"core.artifact");
        append_privacy_identifier(&mut output, b"artifact:native-1");
        append_privacy_identifier(&mut output, b"application/jaya-artifact");
        output.extend_from_slice(&1u16.to_le_bytes());
        output.extend_from_slice(&[1, 2, key_state, attestation_state, temporal_state]);
        output.extend_from_slice(&nonce_size.to_le_bytes());
        output.extend_from_slice(&ciphertext_size.to_le_bytes());
        output.extend_from_slice(&4096u32.to_le_bytes());
        output
    }

    #[test]
    fn validates_identifier_contract() {
        let valid = b"artifact-01.alpha";
        assert_eq!(
            unsafe { jaya_trusted_validate_identifier(valid.as_ptr(), valid.len()) },
            OK
        );
        let invalid = b"../artifact";
        assert_eq!(
            unsafe { jaya_trusted_validate_identifier(invalid.as_ptr(), invalid.len()) },
            INVALID_VALUE
        );
    }

    #[test]
    fn rejects_non_zero_binary_padding() {
        let valid = [0b0000_0011u8];
        assert_eq!(
            unsafe { jaya_trusted_validate_binary_layout(valid.as_ptr(), 1, 2, 1, 64, 8, 512) },
            OK
        );
        let invalid = [0b1000_0011u8];
        assert_eq!(
            unsafe { jaya_trusted_validate_binary_layout(invalid.as_ptr(), 1, 2, 1, 64, 8, 512) },
            INVALID_VALUE
        );
    }

    #[test]
    fn validates_ternary_values() {
        let valid = [-1i8, 0, 1];
        assert_eq!(
            unsafe { jaya_trusted_validate_ternary_values(valid.as_ptr(), valid.len(), 8) },
            OK
        );
        let invalid = [-1i8, 2, 1];
        assert_eq!(
            unsafe { jaya_trusted_validate_ternary_values(invalid.as_ptr(), invalid.len(), 8) },
            INVALID_VALUE
        );
    }

    #[test]
    fn evaluates_first_matching_policy_rule() {
        let table = policy_table(&[(2, 1 << 2, &[]), (1, 1, &[b"core.logic.evaluate"])]);
        let capability = b"core.logic.evaluate";
        let mut effect = 0u8;
        let mut index = POLICY_NO_RULE;
        assert_eq!(
            unsafe {
                jaya_trusted_evaluate_policy(
                    table.as_ptr(),
                    table.len(),
                    capability.as_ptr(),
                    capability.len(),
                    0,
                    2,
                    &mut effect,
                    &mut index,
                )
            },
            OK
        );
        assert_eq!((effect, index), (1, 1));
    }

    #[test]
    fn applies_default_and_rejects_malformed_policy() {
        let table = policy_table(&[(1, 1, &[b"core.logic.evaluate"])]);
        let capability = b"device.switch";
        let mut effect = 0u8;
        let mut index = 0u32;
        assert_eq!(
            unsafe {
                jaya_trusted_evaluate_policy(
                    table.as_ptr(),
                    table.len(),
                    capability.as_ptr(),
                    capability.len(),
                    1,
                    3,
                    &mut effect,
                    &mut index,
                )
            },
            OK
        );
        assert_eq!((effect, index), (3, POLICY_NO_RULE));

        let mut malformed = table;
        malformed.push(0);
        assert_eq!(
            unsafe {
                jaya_trusted_evaluate_policy(
                    malformed.as_ptr(),
                    malformed.len(),
                    capability.as_ptr(),
                    capability.len(),
                    1,
                    3,
                    &mut effect,
                    &mut index,
                )
            },
            INVALID_SIZE
        );
    }

    #[test]
    fn evaluates_verified_privacy_scope() {
        let contract = privacy_contract(true, b"provider-real");
        let mut effect = 0u8;
        let mut reason = 0u8;
        assert_eq!(
            unsafe {
                jaya_trusted_evaluate_privacy(
                    contract.as_ptr(),
                    contract.len(),
                    &mut effect,
                    &mut reason,
                )
            },
            OK
        );
        assert_eq!((effect, reason), (1, 4));
    }

    #[test]
    fn rejects_mismatched_or_missing_privacy_consent() {
        let mismatched = privacy_contract(true, b"provider-other");
        let mut effect = 0u8;
        let mut reason = 0u8;
        assert_eq!(
            unsafe {
                jaya_trusted_evaluate_privacy(
                    mismatched.as_ptr(),
                    mismatched.len(),
                    &mut effect,
                    &mut reason,
                )
            },
            OK
        );
        assert_eq!((effect, reason), (2, 6));

        let missing = privacy_contract(false, b"provider-real");
        assert_eq!(
            unsafe {
                jaya_trusted_evaluate_privacy(
                    missing.as_ptr(),
                    missing.len(),
                    &mut effect,
                    &mut reason,
                )
            },
            OK
        );
        assert_eq!((effect, reason), (2, 5));
    }

    #[test]
    fn evaluates_verified_zero_trust_scope_in_two_stages() {
        let pending = zero_trust_contract(b"node-1", b"core.logic.evaluate", 0, true);
        let mut effect = 0u8;
        let mut reason = 0u8;
        assert_eq!(
            unsafe {
                jaya_trusted_evaluate_zero_trust(
                    pending.as_ptr(),
                    pending.len(),
                    &mut effect,
                    &mut reason,
                )
            },
            OK
        );
        assert_eq!((effect, reason), (3, 8));

        let verified = zero_trust_contract(b"node-1", b"core.logic.evaluate", 1, true);
        assert_eq!(
            unsafe {
                jaya_trusted_evaluate_zero_trust(
                    verified.as_ptr(),
                    verified.len(),
                    &mut effect,
                    &mut reason,
                )
            },
            OK
        );
        assert_eq!((effect, reason), (1, 11));
    }

    #[test]
    fn rejects_zero_trust_scope_and_malformed_contract() {
        let denied = zero_trust_contract(b"node-other", b"core.logic.evaluate", 1, true);
        let mut effect = 0u8;
        let mut reason = 0u8;
        assert_eq!(
            unsafe {
                jaya_trusted_evaluate_zero_trust(
                    denied.as_ptr(),
                    denied.len(),
                    &mut effect,
                    &mut reason,
                )
            },
            OK
        );
        assert_eq!((effect, reason), (2, 5));

        let mut malformed = zero_trust_contract(b"node-1", b"core.logic.evaluate", 1, false);
        malformed.push(0);
        assert_eq!(
            unsafe {
                jaya_trusted_evaluate_zero_trust(
                    malformed.as_ptr(),
                    malformed.len(),
                    &mut effect,
                    &mut reason,
                )
            },
            INVALID_SIZE
        );
    }

    #[test]
    fn evaluates_cryptographic_skin_admission_in_three_stages() {
        let mut effect = 0u8;
        let mut reason = 0u8;
        let pending = cryptographic_skin_contract(0, 0, 0, 0, 0);
        assert_eq!(
            unsafe {
                jaya_trusted_evaluate_cryptographic_skin(
                    pending.as_ptr(),
                    pending.len(),
                    &mut effect,
                    &mut reason,
                )
            },
            OK
        );
        assert_eq!((effect, reason), (3, 2));

        let metadata = cryptographic_skin_contract(1, 1, 1, 0, 0);
        assert_eq!(
            unsafe {
                jaya_trusted_evaluate_cryptographic_skin(
                    metadata.as_ptr(),
                    metadata.len(),
                    &mut effect,
                    &mut reason,
                )
            },
            OK
        );
        assert_eq!((effect, reason), (3, 9));

        let complete = cryptographic_skin_contract(1, 1, 1, 12, 128);
        assert_eq!(
            unsafe {
                jaya_trusted_evaluate_cryptographic_skin(
                    complete.as_ptr(),
                    complete.len(),
                    &mut effect,
                    &mut reason,
                )
            },
            OK
        );
        assert_eq!((effect, reason), (1, 13));
    }

    #[test]
    fn rejects_cryptographic_skin_lifecycle_and_malformed_contract() {
        let mut effect = 0u8;
        let mut reason = 0u8;
        let revoked = cryptographic_skin_contract(3, 1, 1, 0, 0);
        assert_eq!(
            unsafe {
                jaya_trusted_evaluate_cryptographic_skin(
                    revoked.as_ptr(),
                    revoked.len(),
                    &mut effect,
                    &mut reason,
                )
            },
            OK
        );
        assert_eq!((effect, reason), (2, 6));

        let expired = cryptographic_skin_contract(2, 1, 3, 0, 0);
        assert_eq!(
            unsafe {
                jaya_trusted_evaluate_cryptographic_skin(
                    expired.as_ptr(),
                    expired.len(),
                    &mut effect,
                    &mut reason,
                )
            },
            OK
        );
        assert_eq!((effect, reason), (2, 8));

        let mut malformed = cryptographic_skin_contract(1, 1, 1, 12, 128);
        malformed.push(0);
        assert_eq!(
            unsafe {
                jaya_trusted_evaluate_cryptographic_skin(
                    malformed.as_ptr(),
                    malformed.len(),
                    &mut effect,
                    &mut reason,
                )
            },
            INVALID_SIZE
        );
    }
}
