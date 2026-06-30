const SECRET_NAME_PATTERN = /(api[_-]?key|authorization|bearer|password|secret|token)/i;
export function redactText(text, env = process.env) {
    let result = String(text);
    for (const [key, value] of Object.entries(env)) {
        if (!value || value.length < 4)
            continue;
        if (SECRET_NAME_PATTERN.test(key)) {
            result = result.split(value).join("<redacted>");
        }
    }
    result = result.replace(/(authorization\s*[:=]\s*bearer\s+)[^\s'"\\]+/gi, "$1<redacted>");
    result = result.replace(/((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,'"\\]+/gi, "$1<redacted>");
    return result;
}
export function redactJson(value, env = process.env) {
    if (typeof value === "string")
        return redactText(value, env);
    if (Array.isArray(value))
        return value.map((item) => redactJson(item, env));
    if (!value || typeof value !== "object")
        return value;
    const result = {};
    for (const [key, nested] of Object.entries(value)) {
        if (SECRET_NAME_PATTERN.test(key)) {
            result[key] = "<redacted>";
        }
        else {
            result[key] = redactJson(nested, env);
        }
    }
    return result;
}
