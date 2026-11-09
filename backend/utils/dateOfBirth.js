const DATE_OF_BIRTH = /^\d{4}-\d{2}-\d{2}$/;

// Returns a client-safe error message, or null when the optional value is acceptable.
function validateDateOfBirth(value) {
    if (typeof value !== 'string' || (value && !DATE_OF_BIRTH.test(value))) {
        return 'Date of birth must use YYYY-MM-DD.';
    }
    if (!value) return null;
    const date = new Date(`${value}T00:00:00.000Z`);
    if (Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== value || date > new Date()) {
        return 'Enter a valid date of birth that is not in the future.';
    }
    return null;
}

module.exports = { validateDateOfBirth };
