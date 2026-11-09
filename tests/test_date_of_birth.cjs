const test = require('node:test');
const assert = require('node:assert/strict');
const { validateDateOfBirth } = require('../backend/utils/dateOfBirth');

const FORMAT = 'Date of birth must use YYYY-MM-DD.';
const INVALID = 'Enter a valid date of birth that is not in the future.';

function utcDay(offset) {
    const now = new Date();
    return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + offset))
        .toISOString()
        .slice(0, 10);
}

function futureLeapDay() {
    const start = new Date().getUTCFullYear() + 1;
    for (let year = start; year < start + 8; year += 1) {
        const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
        if (leap) return `${year}-02-29`;
    }
    throw new Error('expected a leap day within the next eight years');
}

test('accepts an empty date of birth and real past or current calendar dates', () => {
    for (const value of ['', '1990-01-31', '2024-02-29', '2000-02-29', utcDay(0), utcDay(-1)]) {
        assert.equal(validateDateOfBirth(value), null, value);
    }
});

test('rejects non-leap days, impossible dates, malformed strings, and future dates', () => {
    for (const value of ['2023-02-29', '1900-02-29', '2021-02-31', '2021-04-31', '2021-11-31', '2021-13-01', '2021-00-10', utcDay(1), futureLeapDay()]) {
        assert.equal(validateDateOfBirth(value), INVALID, value);
        assert.equal(validateDateOfBirth(value).includes(value), false);
    }
    for (const value of ['2023/02/28', '02-28-2023', '2023-2-28', '20230228', 'not-a-date', '2023-02-28T00:00:00.000Z', ' 2020-01-01', '2020-01-01 ', null, 20200101]) {
        assert.equal(validateDateOfBirth(value), FORMAT, String(value));
        assert.equal(validateDateOfBirth(value).includes(String(value)), false);
    }
});
